import asyncio
import pytest

from iambic.core.aio_utils import gather_limit

@pytest.mark.asyncio
async def test_gather_limit_non_awaitable():
    with pytest.raises(TypeError):
        await gather_limit(
            lambda: [asyncio.sleep(1) for _ in range(10)], limit=2, return_exceptions=True
        )


@pytest.mark.asyncio
async def test_gather_limit_cancelled():
    with pytest.raises(asyncio.CancelledError):
        task = asyncio.create_task(gather_limit(
            *[asyncio.sleep(1) for _ in range(10)], limit=2
        ))
        await asyncio.sleep(0.2)
        task.cancel()
        await task
