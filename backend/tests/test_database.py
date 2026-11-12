"""Reads caught in a dropped Supabase connection are retried; writes are not."""

import httpx
import pytest

from app.database import RetryDroppedReads


class Flaky(httpx.BaseTransport):
    """Drops the connection `drops` times, then answers."""

    def __init__(self, drops):
        self.drops, self.calls = drops, 0

    def handle_request(self, request):
        self.calls += 1
        if self.calls <= self.drops:
            raise httpx.RemoteProtocolError("<ConnectionTerminated error_code:1>", request=request)
        return httpx.Response(200, json=[{"ok": True}], request=request)


def client(inner):
    return httpx.Client(base_url="https://db.example", transport=RetryDroppedReads(inner))


def test_a_dropped_read_is_retried():
    inner = Flaky(drops=2)
    assert client(inner).get("/rest/v1/profiles").json() == [{"ok": True}]
    assert inner.calls == 3


def test_a_read_gives_up_after_three_tries():
    inner = Flaky(drops=5)
    with pytest.raises(httpx.RemoteProtocolError):
        client(inner).get("/rest/v1/profiles")
    assert inner.calls == 3


def test_a_dropped_write_is_not_resent():
    inner = Flaky(drops=1)
    with pytest.raises(httpx.RemoteProtocolError):
        client(inner).post("/rest/v1/workout_logs", json={"x": 1})
    assert inner.calls == 1
