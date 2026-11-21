"""Run independent database reads at the same time.

Every Supabase request costs a network round trip (about 70 ms from here), and most endpoints made
theirs one after another, so a page waited for the sum of them. parallel() runs reads that don't
depend on each other together, so it waits for the slowest one instead. The PostgREST client's HTTP
connection pool is safe to share between threads.

Calls can nest one level (a parallel step that itself reads several tables in parallel): the outer
calls run in one pool and the inner ones in another, so an outer call never waits on work queued
behind itself. Deeper nesting runs in order.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

WORKERS = 24
_PREFIXES = ("fitsense-db-outer", "fitsense-db-inner")
_pools = [ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix=prefix) for prefix in _PREFIXES]


def _level() -> int:
    """0 on a request thread, 1 in an outer worker, 2 in an inner worker."""
    name = threading.current_thread().name
    return next((i + 1 for i, prefix in enumerate(_PREFIXES) if name.startswith(prefix)), 0)


def parallel(*calls):
    """Run zero-argument callables at the same time; their results in the same order. The first
    error is raised once they've all finished."""
    level = _level()
    if len(calls) < 2 or level >= len(_pools):
        return [call() for call in calls]
    futures = [_pools[level].submit(call) for call in calls]
    results, error = [], None
    for future in futures:
        try:
            results.append(future.result())
        except BaseException as e:   # noqa: BLE001 - re-raised below, after the others finish
            error = error or e
            results.append(None)
    if error:
        raise error
    return results
