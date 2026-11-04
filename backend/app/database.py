import os
from functools import lru_cache

import httpx
from fastapi import HTTPException
from supabase import create_client, Client

# Supabase closes idle connections, and the PostgREST client's default HTTP/2 connection then fails
# the next request on it, write or read (RemoteProtocolError: "Server disconnected", ConnectionTerminated),
# typically the first one after the app sits idle. HTTP/1.1 connections are checked before they're reused,
# which avoids that; and a read that still hits a dropped connection is sent again. Writes aren't resent,
# since the server may already have applied them.
SAFE_TO_RETRY = {"GET", "HEAD"}
READ_ATTEMPTS = 3


class RetryDroppedReads(httpx.BaseTransport):
    def __init__(self, inner: httpx.BaseTransport, attempts: int = READ_ATTEMPTS):
        self.inner = inner
        self.attempts = attempts

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        for attempt in range(self.attempts):
            try:
                return self.inner.handle_request(request)
            except (httpx.RemoteProtocolError, httpx.ReadError):
                if request.method not in SAFE_TO_RETRY or attempt == self.attempts - 1:
                    raise
        raise AssertionError("unreachable")

    def close(self) -> None:
        self.inner.close()


@lru_cache
def _create_supabase(url: str, key: str) -> Client:
    client = create_client(url, key)
    # same session the PostgREST client builds (base URL, API key headers), over HTTP/1.1 with dropped reads retried
    old = client.postgrest.session
    client.postgrest.session = httpx.Client(
        base_url=old.base_url, headers=old.headers, timeout=old.timeout, follow_redirects=True,
        transport=RetryDroppedReads(httpx.HTTPTransport()),
    )
    old.close()
    return client


def get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise HTTPException(
            status_code=503,
            detail="Database not configured: set SUPABASE_URL and SUPABASE_KEY (see .env.example)",
        )
    return _create_supabase(url, key)
