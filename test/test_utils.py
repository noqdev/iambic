from __future__ import annotations

import asyncio

import pytest


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
