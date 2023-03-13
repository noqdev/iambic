from __future__ import annotations

import asyncio
import traceback

import pytest
from iambic.core.utils import sanitize_string


async def success():
    return "success"


async def fail():
    raise Exception("hello")


@pytest.mark.asyncio
async def test_async_gather_behavior():
    tasks = [success(), fail()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert len(results) == 2
    assert results[0] == "success"
    assert isinstance(results[1], Exception)


def test_exception_traceback_behavior():
    def raise_exception():
        raise Exception("hello")

    try:
        raise_exception()
    except Exception:
        captured_message = traceback.format_exc()
        assert "raise_exception" in captured_message


def test_valid_characters():
    # Test that only valid characters are kept
    unsanitized_str = "abc123$%^"
    valid_characters_re = r"[a-zA-Z0-9]"
    expected_output = "abc123"
    assert sanitize_string(unsanitized_str, valid_characters_re) == expected_output


def test_max_length():
    # Test that the string is truncated to the max length
    unsanitized_str = "a" * 100
    valid_characters_re = r"[a-zA-Z0-9]"
    expected_output = "a" * 64
    assert sanitize_string(unsanitized_str, valid_characters_re) == expected_output


def test_no_valid_characters():
    # Test that an empty string is returned if there are no valid characters
    unsanitized_str = "!@#$%^&*()"
    valid_characters_re = r"[a-zA-Z0-9]"
    expected_output = ""
    assert sanitize_string(unsanitized_str, valid_characters_re) == expected_output
