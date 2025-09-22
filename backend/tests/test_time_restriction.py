#!/usr/bin/env python3
"""
Simple test script to verify the backup time restriction logic.
Run this to test different time scenarios.
"""

from datetime import datetime

from fastapi import HTTPException

from app.routers.snapshots import _check_backup_time_restriction


def test_time_scenarios():
    """Test different time scenarios"""
    test_cases = [
        # Format: (minute, second, should_be_restricted)
        # Test cases around 0 minute mark
        (59, 30, True),  # 59:30 - 30s before 0:00 (restricted)
        (59, 29, False),  # 59:29 - 31s before 0:00 (allowed)
        (0, 0, True),  # 0:00 - exact mark (restricted)
        (0, 30, True),  # 0:30 - 30s after 0:00 (restricted)
        (1, 0, True),  # 1:00 - 60s after 0:00 (restricted)
        (1, 1, False),  # 1:01 - 61s after 0:00 (allowed)
        # Test cases around 15 minute mark
        (14, 30, True),  # 14:30 - 30s before 15:00 (restricted)
        (14, 29, False),  # 14:29 - 31s before 15:00 (allowed)
        (15, 0, True),  # 15:00 - exact mark (restricted)
        (15, 30, True),  # 15:30 - 30s after 15:00 (restricted)
        (16, 0, True),  # 16:00 - 60s after 15:00 (restricted)
        (16, 1, False),  # 16:01 - 61s after 15:00 (allowed)
        # Test cases around 30 minute mark
        (29, 30, True),  # 29:30 - 30s before 30:00 (restricted)
        (29, 29, False),  # 29:29 - 31s before 30:00 (allowed)
        (30, 0, True),  # 30:00 - exact mark (restricted)
        (30, 30, True),  # 30:30 - 30s after 30:00 (restricted)
        (31, 0, True),  # 31:00 - 60s after 30:00 (restricted)
        (31, 1, False),  # 31:01 - 61s after 30:00 (allowed)
        # Test cases around 45 minute mark
        (44, 30, True),  # 44:30 - 30s before 45:00 (restricted)
        (44, 29, False),  # 44:29 - 31s before 45:00 (allowed)
        (45, 0, True),  # 45:00 - exact mark (restricted)
        (45, 30, True),  # 45:30 - 30s after 45:00 (restricted)
        (46, 0, True),  # 46:00 - 60s after 45:00 (restricted)
        (46, 1, False),  # 46:01 - 61s after 45:00 (allowed)
        # Test some random allowed times
        (5, 0, False),  # 5:00 (allowed)
        (10, 30, False),  # 10:30 (allowed)
        (20, 15, False),  # 20:15 (allowed)
        (35, 45, False),  # 35:45 (allowed)
    ]

    print("Testing backup time restriction logic...")
    print("=" * 50)

    all_passed = True

    for minute, second, should_be_restricted in test_cases:
        # Mock the current time
        import unittest.mock

        mock_time = datetime(2024, 1, 1, 12, minute, second)

        with unittest.mock.patch("app.routers.snapshots.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_time

            try:
                _check_backup_time_restriction()
                is_restricted = False
            except HTTPException:
                is_restricted = True

            status = "✓" if is_restricted == should_be_restricted else "✗"
            result = "PASS" if is_restricted == should_be_restricted else "FAIL"
            restriction_text = "RESTRICTED" if is_restricted else "ALLOWED"
            expected_text = "RESTRICTED" if should_be_restricted else "ALLOWED"

            print(
                f"{status} {minute:2d}:{second:02d} -> {restriction_text:10} (expected: {expected_text:10}) {result}"
            )

            if is_restricted != should_be_restricted:
                all_passed = False

    print("=" * 50)
    if all_passed:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed!")

    return all_passed


if __name__ == "__main__":
    test_time_scenarios()
