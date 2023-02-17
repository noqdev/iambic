from __future__ import annotations

import asyncio


async def handle_azure_ad_fn(fn, *args, **kwargs):
    try:
        res = await fn(*args, **kwargs)
    except asyncio.exceptions.TimeoutError:
        raise asyncio.exceptions.TimeoutError
    return res
