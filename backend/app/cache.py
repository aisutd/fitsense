"""Short-lived caches for data that hardly ever changes (the HealthScore weights, the badge list), kept
on the database client so each client (and each test's fake database) has its own."""

import time

_ATTR = "_fitsense_cache"


def per_client(client, key: str, ttl: float, load):
    """load()'s result, reused for ttl seconds on this client."""
    store = getattr(client, _ATTR, None)
    if store is None:
        store = {}
        try:
            setattr(client, _ATTR, store)
        except AttributeError:   # a client that can't hold a cache: read every time
            return load()
    hit = store.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    value = load()
    store[key] = (time.monotonic(), value)
    return value


def clear(client) -> None:
    """Forget everything cached on this client (after changing cached data directly)."""
    store = getattr(client, _ATTR, None)
    if store is not None:
        store.clear()
