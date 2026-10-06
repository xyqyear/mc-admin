import asyncio
from collections.abc import Callable
from typing import Any, cast

import pytest

from app import logger as logging_boundary
from app.logger import log_exception
from app.runtime_resources import current_runtime


@pytest.mark.parametrize('async_function', [False, True])
@pytest.mark.parametrize('fallback', [None, 42, 'fallback', False, []])
async def test_configured_failure_result_is_preserved(caplog, async_function, fallback):
    secret = 'synthetic-decorator-adapter-credential'

    def fail(value):
        raise ValueError(secret)

    async def fail_async(value):
        fail(value)

    operation = log_exception('Safe operation', default_return=fallback)(fail_async if async_function else fail)
    result = await operation(secret) if async_function else operation(secret)
    assert result is fallback
    assert secret not in caplog.text
    assert 'Safe operation' in caplog.text and 'ValueError' in caplog.text
    assert 'fail:' in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize('async_function', [False, True])
@pytest.mark.parametrize('result', [8, 30, 'Success!', (1, 'value'), {'items': [1, 2]}, None])
async def test_success_returns_original_value_without_failure_diagnostics(caplog, async_function, result):
    def succeed():
        return result

    async def succeed_async():
        return result

    operation = log_exception('Safe success')(succeed_async if async_function else succeed)
    actual = await operation() if async_function else operation()
    assert actual is result
    assert not caplog.records


@pytest.mark.parametrize('async_function', [False, True])
async def test_wrong_arguments_remain_in_function_error_boundary(caplog, async_function):
    def needs_one(value):
        return value

    async def needs_one_async(value):
        return value

    operation = cast(Callable[..., Any], log_exception(default_return='fallback')(needs_one_async if async_function else needs_one))
    actual = await operation(1, 2, 3) if async_function else operation(1, 2, 3)
    assert actual == 'fallback'
    assert 'TypeError' in caplog.text and 'takes' not in caplog.text


@pytest.mark.parametrize('async_function', [False, True])
@pytest.mark.parametrize('error_type', [asyncio.CancelledError, KeyboardInterrupt])
async def test_base_exceptions_propagate_without_failure_logs(caplog, async_function, error_type):
    def interrupted():
        raise error_type()

    async def interrupted_async():
        interrupted()

    with pytest.raises(error_type):
        if async_function:
            await log_exception()(interrupted_async)()
        else:
            log_exception()(interrupted)()
    assert not caplog.records


@pytest.mark.parametrize('async_function', [False, True])
async def test_logger_acquisition_failure_precedes_function(monkeypatch, async_function):
    executed = []

    def succeed():
        executed.append(True)

    async def succeed_async():
        succeed()

    def unavailable():
        raise RuntimeError('runtime logger unavailable')

    monkeypatch.setattr(logging_boundary, 'get_logger', unavailable)
    with pytest.raises(RuntimeError, match='runtime logger unavailable'):
        if async_function:
            await log_exception()(succeed_async)()
        else:
            log_exception()(succeed)()
    assert executed == []


@pytest.mark.parametrize('value', [None, '', "多行\n带引号'内容", [1, 2, 3], {'token': 'synthetic-argument-secret'}])
async def test_argument_values_are_not_logged(caplog, value):
    @log_exception('Profile {value}')
    async def fail(value, *, option='synthetic-default-secret'):
        raise RuntimeError('synthetic-exception-secret')

    assert await fail(value) is None
    assert 'RuntimeError' in caplog.text and 'Profile {value}' in caplog.text
    for secret in ('synthetic-argument-secret', 'synthetic-default-secret', 'synthetic-exception-secret'):
        assert secret not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


async def test_instance_method_and_arguments_never_render_values(caplog):
    class PrivateValue:
        def __repr__(self):
            raise AssertionError('argument repr must not be evaluated')

        def __format__(self, format_spec):
            raise AssertionError('argument formatting must not be evaluated')

        @log_exception('Owner {self}, value {value}')
        async def process(self, value):
            raise KeyError('synthetic-owner-secret')

    owner = PrivateValue()
    assert await owner.process(owner) is None
    assert 'KeyError' in caplog.text
    assert 'synthetic-owner-secret' not in caplog.text and 'AssertionError' not in caplog.text


async def test_success_and_failure_do_not_format_prefix(caplog):
    class PrivateValue:
        def __format__(self, format_spec):
            raise AssertionError('formatting must not run')

    value = PrivateValue()

    @log_exception('Missing {missing}, value {value}')
    async def operation(value, fail=False):
        if fail:
            raise RuntimeError('synthetic-prefix-error')
        return value

    assert await operation(value) is value
    assert not caplog.records
    assert await operation(value, fail=True) is None
    assert 'RuntimeError' in caplog.text
    assert 'synthetic-prefix-error' not in caplog.text and 'WARNING' not in caplog.text


async def test_failure_uses_owning_runtime_logger(caplog):
    owner = current_runtime().resource("app_logger")

    @log_exception('Owned failure')
    async def fail():
        raise RuntimeError('synthetic-owner-error')

    assert await fail() is None
    record = next(record for record in caplog.records if 'Owned failure' in record.getMessage())
    assert record.name == owner.name
