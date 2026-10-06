import asyncio
import inspect

import pytest

from app import logger as logging_boundary
from app.logger import log_exception
from app.runtime_resources import current_runtime


async def test_failure_returns_none_and_next_invocation_succeeds(caplog):
    secret = 'synthetic-decorator-adapter-credential'

    @log_exception('Safe operation')
    async def operation(value):
        if value == secret:
            raise ValueError(secret)
        return ('observed', value)

    assert await operation(secret) is None
    assert await operation('recovered') == ('observed', 'recovered')
    assert secret not in caplog.text
    assert 'Safe operation' in caplog.text and 'ValueError' in caplog.text
    assert 'operation:' in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize('result', [8, 30, 'Success!', (1, 'value'), {'items': [1, 2]}, None])
async def test_success_returns_original_value_without_failure_diagnostics(caplog, result):
    @log_exception('Safe success')
    async def succeed():
        return result

    assert await succeed() is result
    assert not caplog.records


async def test_wrong_arguments_remain_in_function_error_boundary(caplog):
    @log_exception()
    async def needs_one(value: int) -> int:
        return value

    assert await needs_one(1, 2, 3) is None  # pyright: ignore[reportCallIssue]
    assert 'TypeError' in caplog.text and 'takes' not in caplog.text


@pytest.mark.parametrize('error_type', [asyncio.CancelledError, KeyboardInterrupt, SystemExit])
async def test_base_exceptions_propagate_without_failure_logs(caplog, error_type):
    @log_exception()
    async def interrupted():
        raise error_type()

    with pytest.raises(error_type):
        await interrupted()
    assert not caplog.records


async def test_logger_acquisition_failure_precedes_function(monkeypatch):
    executed = []

    @log_exception()
    async def succeed():
        executed.append(True)

    def unavailable():
        raise RuntimeError('runtime logger unavailable')

    monkeypatch.setattr(logging_boundary, 'get_logger', unavailable)
    with pytest.raises(RuntimeError, match='runtime logger unavailable'):
        await succeed()
    assert executed == []


async def test_wrapped_metadata_and_async_result_are_preserved():
    async def original(value: int, *, tag: str = 'safe') -> tuple[int, str]:
        """Fixture operation documentation."""
        return value, tag

    wrapped = log_exception()(original)
    assert wrapped.__name__ == original.__name__
    assert wrapped.__doc__ == original.__doc__
    assert inspect.unwrap(wrapped) is original
    assert inspect.signature(wrapped) == inspect.signature(original)
    assert await wrapped(7, tag='observed') == (7, 'observed')


async def test_cancelled_operation_closes_its_resource_without_failure_logs(caplog):
    entered, closed = asyncio.Event(), asyncio.Event()

    @log_exception('Cancellation boundary')
    async def operation():
        try:
            entered.set()
            await asyncio.Event().wait()
        finally:
            closed.set()

    worker = asyncio.create_task(operation())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker
        assert closed.is_set()
        assert not caplog.records
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


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
    owner = current_runtime().app_logger

    @log_exception('Owned failure')
    async def fail():
        raise RuntimeError('synthetic-owner-error')

    assert await fail() is None
    record = next(record for record in caplog.records if 'Owned failure' in record.getMessage())
    assert record.name == owner.name
