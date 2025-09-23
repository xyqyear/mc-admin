#!/usr/bin/env python3
"""
Simple test script to verify the backup time restriction logic.
Run this to test different time scenarios.
"""

import asyncio
from datetime import datetime
from unittest.mock import MagicMock

from fastapi import HTTPException

from app.routers.snapshots import _check_backup_time_restriction


async def test_time_scenarios_with_config(
    time_restriction_enabled=True, before_seconds=30, after_seconds=60
):
    """Test different time scenarios"""
    # Generate test cases based on the actual config
    test_cases = []

    # Test cases around each backup minute (0, 15, 30, 45)
    backup_minutes = [0, 15, 30, 45]

    for backup_minute in backup_minutes:
        # Calculate restricted ranges
        before_minute = backup_minute
        before_second = 60 - before_seconds if backup_minute == 0 else 0
        if backup_minute == 0:
            before_minute = 59
        else:
            before_minute = backup_minute - 1
            before_second = 60 - before_seconds

        # Add test cases for this backup minute
        # Before restriction boundary
        if before_second < 60:
            test_cases.append(
                (before_minute, before_second, True)
            )  # exactly at boundary (restricted)
            if before_second > 0:
                test_cases.append(
                    (before_minute, before_second - 1, False)
                )  # just outside boundary (allowed)

        # Exact backup time
        test_cases.append((backup_minute, 0, True))  # exact mark (restricted)

        # After restriction
        after_minute = backup_minute
        after_second = after_seconds
        if after_second >= 60:
            after_minute = (backup_minute + 1) % 60
            after_second = after_second - 60

        test_cases.append(
            (after_minute, after_second, True)
        )  # exactly at boundary (restricted)
        if after_second < 59:
            test_cases.append(
                (after_minute, after_second + 1, False)
            )  # just outside boundary (allowed)

    # Add some clearly allowed times
    test_cases.extend(
        [
            (5, 0, False),  # 5:00 (allowed)
            (10, 30, False),  # 10:30 (allowed)
            (20, 15, False),  # 20:15 (allowed)
            (35, 45, False),  # 35:45 (allowed)
        ]
    )

    print("Testing backup time restriction logic...")
    print("=" * 50)

    all_passed = True

    print(
        f"Testing with config: enabled={time_restriction_enabled}, before={before_seconds}s, after={after_seconds}s"
    )

    for minute, second, should_be_restricted in test_cases:
        # Mock the current time, backup minutes, and dynamic config
        import unittest.mock

        mock_time = datetime(2024, 1, 1, 12, minute, second)
        # Use the original quarter-hour marks for testing: 0, 15, 30, 45
        backup_minutes = {0, 15, 30, 45}

        # Create mock configuration
        mock_time_restriction = MagicMock()
        mock_time_restriction.enabled = time_restriction_enabled
        mock_time_restriction.before_seconds = before_seconds
        mock_time_restriction.after_seconds = after_seconds

        mock_snapshots_config = MagicMock()
        mock_snapshots_config.time_restriction = mock_time_restriction

        with (
            unittest.mock.patch("app.routers.snapshots.datetime") as mock_datetime,
            unittest.mock.patch(
                "app.routers.snapshots.restart_scheduler.get_backup_minutes"
            ) as mock_get_backup_minutes,
            unittest.mock.patch("app.routers.snapshots.config") as mock_config,
        ):
            mock_datetime.now.return_value = mock_time
            mock_get_backup_minutes.return_value = backup_minutes
            mock_config.snapshots = mock_snapshots_config

            try:
                await _check_backup_time_restriction()
                is_restricted = False
            except HTTPException:
                is_restricted = True

            # When time restriction is disabled, nothing should be restricted
            if not time_restriction_enabled:
                expected_restricted = False
            else:
                expected_restricted = should_be_restricted

            status = "✓" if is_restricted == expected_restricted else "✗"
            result = "PASS" if is_restricted == expected_restricted else "FAIL"
            restriction_text = "RESTRICTED" if is_restricted else "ALLOWED"
            expected_text = "RESTRICTED" if expected_restricted else "ALLOWED"

            print(
                f"{status} {minute:2d}:{second:02d} -> {restriction_text:10} (expected: {expected_text:10}) {result}"
            )

            if is_restricted != expected_restricted:
                all_passed = False

    print("=" * 50)
    if all_passed:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed!")

    return all_passed


async def test_time_scenarios():
    """Test original scenarios with default config"""
    return await test_time_scenarios_with_config()


async def test_disabled_restriction():
    return await test_time_scenarios_with_config(time_restriction_enabled=False)


async def test_custom_timing():
    """Test with custom before/after seconds"""
    return await test_time_scenarios_with_config(before_seconds=10, after_seconds=20)
