from __future__ import annotations

import asyncio
from typing import Any, Awaitable, TypeVar

T = TypeVar("T")


async def gather_limit(
    *args: Awaitable[T],
    return_exceptions: bool = False,
    limit: int = -1,
) -> list[Any]:
    """
    (Taken from https://github.com/omnilib/aioitertools/blob/v0.7.1/aioitertools/asyncio.py)
    Like asyncio.gather but with a limit on concurrency.

    Note that all results are buffered.

    If gather is cancelled all tasks that were internally created and still pending
    will be cancelled as well.

    Example::

        futures = [some_coro(i) for i in range(10)]

        results = await gather(*futures, limit=2)
    """

    # For detecting input duplicates and reconciling them at the end
    input_map: dict[Awaitable[T], list[int]] = {}
    # This is keyed on what we'll get back from asyncio.wait
    pos: dict[asyncio.Future[T], int] = {}
    ret: list[Any] = [None] * len(args)

    pending: set[asyncio.Future[T]] = set()
    done: set[asyncio.Future[T]] = set()

    next_arg = 0

    while True:
        while next_arg < len(args) and (limit == -1 or len(pending) < limit):
            # We have to defer the creation of the Task as long as possible
            # because once we do, it starts executing, regardless of what we
            # have in the pending set.
            if args[next_arg] in input_map:
                input_map[args[next_arg]].append(next_arg)
            else:
                # We call ensure_future directly to ensure that we have a Task
                # because the return value of asyncio.wait will be an implicit
                # task otherwise, and we won't be able to know which input it
                # corresponds to.
                task: asyncio.Future[T] = asyncio.ensure_future(args[next_arg])
                pending.add(task)
                pos[task] = next_arg
                input_map[args[next_arg]] = [next_arg]
            next_arg += 1

        # pending might be empty if the last items of args were dupes;
        # asyncio.wait([]) will raise an exception.
        if pending:
            try:
                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )
                for x in done:
                    if return_exceptions and x.exception():
                        ret[pos[x]] = x.exception()
                    else:
                        ret[pos[x]] = x.result()
            except asyncio.CancelledError:
                # Since we created these tasks we should cancel them
                for x in pending:
                    x.cancel()
                # we insure that all tasks are cancelled before we raise
                await asyncio.gather(*pending, return_exceptions=True)
                raise

        if not pending and next_arg == len(args):
            break

    for lst in input_map.values():
        for i in range(1, len(lst)):
            ret[lst[i]] = ret[lst[0]]

    return ret
