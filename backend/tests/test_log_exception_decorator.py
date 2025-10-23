"""
Comprehensive tests for the log_exception decorator.

Tests cover:
- Basic exception logging with sync and async functions
- Parameter name binding and formatting
- Prefix string formatting with parameter substitution
- Error handling for binding failures and missing parameters
- Stacklevel verification for correct log location
"""

import asyncio

import pytest

from app.logger import log_exception


class TestBasicExceptionLogging:
    """Test basic exception logging functionality."""

    @pytest.mark.asyncio
    async def test_sync_function_with_prefix(self, caplog):
        """Test sync function logs exception with prefix and returns None."""

        @log_exception("SyncOperation")
        def sync_func_with_error():
            raise ValueError("Test error from sync function")

        result = sync_func_with_error()

        # Should return None instead of raising
        assert result is None

        # Check log output
        assert "SyncOperation: ValueError: Test error from sync function" in caplog.text
        assert "ERROR" in caplog.text

    @pytest.mark.asyncio
    async def test_async_function_with_prefix(self, caplog):
        """Test async function logs exception with prefix and returns None."""

        @log_exception("AsyncOperation")
        async def async_func_with_error():
            await asyncio.sleep(0.01)
            raise ValueError("Test error from async function")

        result = await async_func_with_error()

        # Should return None instead of raising
        assert result is None

        # Check log output
        assert (
            "AsyncOperation: ValueError: Test error from async function" in caplog.text
        )
        assert "ERROR" in caplog.text

    @pytest.mark.asyncio
    async def test_function_without_prefix(self, caplog):
        """Test function without prefix still logs exception and returns None."""

        @log_exception()
        def sync_func_no_prefix():
            raise RuntimeError("Error without prefix")

        result = sync_func_no_prefix()

        # Should return None instead of raising
        assert result is None

        # Check log output - no prefix, just exception
        assert "RuntimeError: Error without prefix" in caplog.text

    @pytest.mark.asyncio
    async def test_successful_execution_no_log(self, caplog):
        """Test successful execution does not log error."""

        @log_exception("SuccessfulOp")
        async def async_func_success():
            await asyncio.sleep(0.01)
            return "Success!"

        result = await async_func_success()

        assert result == "Success!"
        # Should not have ERROR logs
        assert "ERROR" not in caplog.text


class TestParameterBinding:
    """Test parameter name binding and display."""

    @pytest.mark.asyncio
    async def test_positional_args_with_names(self, caplog):
        """Test positional arguments are bound to parameter names."""

        @log_exception("Calculator")
        def add_numbers(a: int, b: int) -> int:
            raise ValueError("Test error")

        result = add_numbers(5, 3)

        # Should return None instead of raising
        assert result is None

        # Should show parameter names, not args=
        assert "a=5" in caplog.text
        assert "b=3" in caplog.text
        assert "args=" not in caplog.text

    @pytest.mark.asyncio
    async def test_keyword_args_with_names(self, caplog):
        """Test keyword arguments are displayed correctly."""

        @log_exception()
        def process_string(text: str, uppercase: bool = False) -> str:
            raise ValueError("Test error")

        result = process_string("Hello", uppercase=True)

        # Should return None instead of raising
        assert result is None

        assert "text='Hello'" in caplog.text
        assert "uppercase=True" in caplog.text

    @pytest.mark.asyncio
    async def test_default_values_shown(self, caplog):
        """Test default parameter values are shown in logs."""

        @log_exception()
        async def async_fetch(url: str, timeout: int = 30):
            raise RuntimeError("Test error")

        result = await async_fetch("https://example.com")

        # Should return None instead of raising
        assert result is None

        # Should show default value
        assert "url='https://example.com'" in caplog.text
        assert "timeout=30" in caplog.text

    @pytest.mark.asyncio
    async def test_instance_method_with_self(self, caplog):
        """Test instance methods show self parameter."""

        class TestClass:
            def __init__(self, name: str):
                self.name = name

            @log_exception("MethodTest")
            def process(self, item_id: int):
                raise KeyError("Test error")

        obj = TestClass("MyObject")
        result = obj.process(12345)

        # Should return None instead of raising
        assert result is None

        assert "item_id=12345" in caplog.text
        assert "self=" in caplog.text  # Self is shown
        assert "TestClass" in caplog.text

    @pytest.mark.asyncio
    async def test_complex_types_in_args(self, caplog):
        """Test complex types are properly repr'd."""

        @log_exception()
        def process_data(items: list[int], config: dict[str, str]):
            raise ValueError("Test error")

        result = process_data([1, 2, 3], {"key": "value"})

        # Should return None instead of raising
        assert result is None

        assert "items=[1, 2, 3]" in caplog.text
        assert "config={'key': 'value'}" in caplog.text


class TestPrefixFormatting:
    """Test prefix formatting with parameter substitution."""

    @pytest.mark.asyncio
    async def test_single_parameter_in_prefix(self, caplog):
        """Test prefix with single parameter substitution."""

        @log_exception("Player[{player_name}]")
        def test_func(player_name: str, server_id: str):
            raise ValueError("Test error")

        result = test_func("Steve", "server1")

        # Should return None instead of raising
        assert result is None

        # Prefix should be formatted
        assert "Player[Steve]:" in caplog.text
        assert "player_name='Steve'" in caplog.text

    @pytest.mark.asyncio
    async def test_multiple_parameters_in_prefix(self, caplog):
        """Test prefix with multiple parameter substitutions."""

        @log_exception("Server[{server_id}] Action[{action}]")
        async def async_test_prefix(server_id: str, action: str):
            raise RuntimeError("Test error")

        result = await async_test_prefix("lobby", "restart")

        # Should return None instead of raising
        assert result is None

        # Both parameters in prefix
        assert "Server[lobby] Action[restart]:" in caplog.text

    @pytest.mark.asyncio
    async def test_prefix_without_braces(self, caplog):
        """Test normal prefix without parameter substitution."""

        @log_exception("StaticPrefix")
        def test_static(value: int):
            raise KeyError("Test error")

        result = test_static(42)

        # Should return None instead of raising
        assert result is None

        assert "StaticPrefix:" in caplog.text
        assert "[42]" not in caplog.text  # Should not try to format

    @pytest.mark.asyncio
    async def test_missing_parameter_in_prefix(self, caplog):
        """Test prefix with non-existent parameter shows warning."""

        @log_exception("MissingParam[{nonexistent}]")
        def test_missing(actual_param: str):
            raise ValueError("Test error")

        result = test_missing("test_value")

        # Should return None instead of raising
        assert result is None

        # Should have warning about failed formatting
        assert "Failed to format prefix" in caplog.text
        assert "nonexistent" in caplog.text
        # Should fallback to original prefix
        assert "MissingParam[{nonexistent}]:" in caplog.text


class TestBindingFailures:
    """Test handling of parameter binding failures."""

    @pytest.mark.asyncio
    async def test_too_many_arguments_warning(self, caplog):
        """Test warning when too many arguments are provided."""

        @log_exception("TooManyArgs")
        def test_func(param1: str):
            raise ValueError("Test error")

        # The decorator catches the TypeError and returns None
        result = test_func("first", "second", "third")  # type: ignore

        # Should return None instead of raising
        assert result is None

        # Should have binding failure warning
        assert "Failed to bind arguments" in caplog.text
        assert "test_func" in caplog.text
        # Should fallback to args= format
        assert "args=" in caplog.text

    @pytest.mark.asyncio
    async def test_binding_failure_shows_function_name(self, caplog):
        """Test binding failure warning shows function name."""

        @log_exception("BindTest")
        def complex_func(required: str, optional: int = 10):
            raise ValueError("Test error")

        # The decorator catches the TypeError and returns None
        result = complex_func(1, 2, 3)  # type: ignore

        # Should return None instead of raising
        assert result is None

        # Warning should mention function name
        assert "complex_func" in caplog.text
        assert "Failed to bind arguments" in caplog.text


class TestTypePreservation:
    """Test that decorator preserves function behavior and types."""

    @pytest.mark.asyncio
    async def test_sync_function_return_value(self):
        """Test sync function return values are preserved."""

        @log_exception()
        def add_numbers(a: int, b: int) -> int:
            return a + b

        result = add_numbers(5, 3)
        assert result == 8
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_async_function_return_value(self):
        """Test async function return values are preserved."""

        @log_exception()
        async def async_add(a: int, b: int) -> int:
            await asyncio.sleep(0.01)
            return a + b

        result = await async_add(10, 20)
        assert result == 30
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_complex_return_types(self):
        """Test complex return types are preserved."""

        @log_exception()
        async def fetch_data(url: str) -> dict[str, str]:
            await asyncio.sleep(0.01)
            return {"url": url, "status": "success"}

        result = await fetch_data("https://example.com")
        assert isinstance(result, dict)
        assert result["url"] == "https://example.com"

    @pytest.mark.asyncio
    async def test_none_return_type(self):
        """Test functions returning None work correctly."""

        @log_exception()
        def log_message(message: str) -> None:
            pass

        result = log_message("test")
        assert result is None


class TestStackLevel:
    """Test that log location (stacklevel) is correct."""

    @pytest.mark.asyncio
    async def test_error_log_shows_caller_location(self, caplog):
        """Test error logs show the actual caller location, not wrapper."""

        @log_exception()
        def failing_func():
            raise ValueError("Test error")

        result = failing_func()  # This line should appear in log

        # Should return None instead of raising
        assert result is None

        # Log should reference test file, not the wrapper
        assert "test_log_exception_decorator.py" in caplog.text
        # Should not be in logger.py (the wrapper)
        assert "logger.py" not in caplog.text.split("\n")[0]  # First line only

    @pytest.mark.asyncio
    async def test_binding_warning_shows_caller_location(self, caplog):
        """Test binding failure warning shows caller location."""

        @log_exception()
        def func_with_binding_issue(param: str):
            raise ValueError("Test error")

        # The decorator catches the TypeError and returns None
        result = func_with_binding_issue(1, 2, 3)  # type: ignore

        # Should return None instead of raising
        assert result is None

        # Warning should show this test function location
        assert "test_binding_warning_shows_caller_location" in caplog.text

    @pytest.mark.asyncio
    async def test_prefix_format_warning_shows_caller_location(self, caplog):
        """Test prefix format warning shows caller location."""

        @log_exception("Prefix[{missing}]")
        def func_with_bad_prefix(actual: str):
            raise ValueError("Test error")

        result = func_with_bad_prefix("value")

        # Should return None instead of raising
        assert result is None

        # Warning should show test file location
        assert "test_log_exception_decorator.py" in caplog.text
        # Check warning specifically
        warning_lines = [line for line in caplog.text.split("\n") if "WARNING" in line]
        assert len(warning_lines) > 0
        assert "test_log_exception_decorator.py" in warning_lines[0]


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    @pytest.mark.asyncio
    async def test_no_arguments_function(self, caplog):
        """Test function with no arguments."""

        @log_exception("NoArgs")
        def no_args_func():
            raise ValueError("Test error")

        result = no_args_func()

        # Should return None instead of raising
        assert result is None

        # Should not show empty brackets
        assert "NoArgs: ValueError" in caplog.text

    @pytest.mark.asyncio
    async def test_special_characters_in_string_args(self, caplog):
        """Test special characters in arguments are properly escaped."""

        @log_exception()
        def process_text(text: str):
            raise ValueError("Test error")

        result = process_text("text\nwith\nnewlines")

        # Should return None instead of raising
        assert result is None

        # Should show escaped newlines, not actual newlines
        assert r"text\n" in caplog.text or "'text\\n" in caplog.text

    @pytest.mark.asyncio
    async def test_none_as_argument(self, caplog):
        """Test None arguments are displayed correctly."""

        @log_exception()
        def process_optional(value: str | None):
            raise ValueError("Test error")

        result = process_optional(None)

        # Should return None instead of raising
        assert result is None

        assert "value=None" in caplog.text

    @pytest.mark.asyncio
    async def test_empty_string_argument(self, caplog):
        """Test empty string is shown with quotes."""

        @log_exception()
        def process_string(text: str):
            raise ValueError("Test error")

        result = process_string("")

        # Should return None instead of raising
        assert result is None

        # Empty string should be visible with quotes
        assert "text=''" in caplog.text


class TestDefaultReturnValue:
    """Test custom default return values when exceptions occur."""

    @pytest.mark.asyncio
    async def test_custom_default_return_sync(self, caplog):
        """Test sync function returns custom default value on exception."""

        @log_exception("CustomDefault", default_return=42)
        def sync_func_with_default():
            raise ValueError("Test error")

        result = sync_func_with_default()

        # Should return custom default value
        assert result == 42

        # Check log output
        assert "CustomDefault: ValueError: Test error" in caplog.text
        assert "ERROR" in caplog.text

    @pytest.mark.asyncio
    async def test_custom_default_return_async(self, caplog):
        """Test async function returns custom default value on exception."""

        @log_exception("CustomDefaultAsync", default_return="fallback")
        async def async_func_with_default() -> str:
            await asyncio.sleep(0.01)
            raise RuntimeError("Test error")

        result = await async_func_with_default()

        # Should return custom default value
        assert result == "fallback"

        # Check log output
        assert "CustomDefaultAsync: RuntimeError: Test error" in caplog.text
        assert "ERROR" in caplog.text

    @pytest.mark.asyncio
    async def test_default_return_none_explicit(self, caplog):
        """Test explicit None as default return value."""

        @log_exception("ExplicitNone", default_return=None)
        def func_with_none():
            raise ValueError("Test error")

        result = func_with_none()

        # Should return None
        assert result is None

        # Check log output
        assert "ExplicitNone: ValueError: Test error" in caplog.text

    @pytest.mark.asyncio
    async def test_default_return_false(self, caplog):
        """Test False as default return value."""

        @log_exception("ReturnFalse", default_return=False)
        def func_with_false():
            raise ValueError("Test error")

        result = func_with_false()

        # Should return False (not None)
        assert result is False
        assert result is not None

        # Check log output
        assert "ReturnFalse: ValueError: Test error" in caplog.text

    @pytest.mark.asyncio
    async def test_default_return_empty_list(self, caplog):
        """Test empty list as default return value."""

        @log_exception("EmptyList", default_return=[])
        def func_with_empty_list():
            raise ValueError("Test error")

        result = func_with_empty_list()

        # Should return empty list
        assert result == []
        assert isinstance(result, list)

        # Check log output
        assert "EmptyList: ValueError: Test error" in caplog.text
