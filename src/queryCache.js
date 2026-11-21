import { useCallback, useEffect, useRef, useState } from "react";

// Remembers each screen's last data, so going back to a tab shows it straight away while it
// refreshes in the background (stale-while-revalidate), and lets other tabs be loaded ahead of time
// (prefetch). Data lives in memory only, for this visit; logging out clears it.

const cache = new Map();      // key -> data
const pending = new Map();    // key -> promise, so a prefetch and a screen share one request

function fetchInto(key, load) {
  if (!pending.has(key)) {
    const request = load()
      .then((data) => {
        cache.set(key, data);
        return data;
      })
      .finally(() => pending.delete(key));
    pending.set(key, request);
  }
  return pending.get(key);
}

/** Load a query in the background if it isn't cached yet (errors are ignored: the screen retries). */
export function prefetch({ key, load }) {
  if (!cache.has(key)) fetchInto(key, load).catch(() => {});
}

/** A query's cached data, or undefined: for screens that manage their own loading. */
export function peekQuery({ key }) {
  return cache.get(key);
}

/** Ask the server and update the cache. shareInFlight: reuse a request already on its way (a
    screen's first load can share a prefetch; a reload after a change mustn't). */
export function refetch({ key, load }, { shareInFlight = false } = {}) {
  if (!shareInFlight) pending.delete(key);
  return fetchInto(key, load);
}

export function clearQueryCache() {
  cache.clear();
}

/**
 * { status: "loading" | "ready" | "error", data, error, refreshing, reload } for a query
 * ({ key, load }). With cached data it starts "ready" with that data and refreshes it quietly.
 */
export function useCachedQuery({ key, load }) {
  const [state, setState] = useState(() =>
    cache.has(key) ? { status: "ready", data: cache.get(key), error: null } : { status: "loading", data: null, error: null });
  const [attempt, setAttempt] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    let cancelled = false;
    const cached = cache.get(key);
    setState(cached !== undefined
      ? { status: "ready", data: cached, error: null, refreshing: true }
      : { status: "loading", data: null, error: null });
    // always asks the server again (a request already on its way, e.g. a prefetch, is shared)
    fetchInto(key, loadRef.current)
      .then((data) => !cancelled && setState({ status: "ready", data, error: null }))
      .catch((error) => !cancelled && setState((s) => (s.data != null
        ? { ...s, refreshing: false }   // keep showing what we had
        : { status: "error", data: null, error })));
    return () => {
      cancelled = true;
    };
  }, [key, attempt]);

  const reload = useCallback(() => {
    pending.delete(key);
    setAttempt((n) => n + 1);
  }, [key]);
  return { ...state, reload };
}
