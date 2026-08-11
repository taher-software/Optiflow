"""Tests for `core.push`: the single-send primitive's non-raising `bool`
contract, and `send_push_notifications`'s total-vs-partial failure split
(`PushDeliveryError` only on total failure of a non-empty batch)."""

import pytest

from src.app.core.push import (
    PushDeliveryError,
    send_push_notification,
    send_push_notifications,
)


class _FakeResponse:
    def __init__(self, ok: bool):
        self.ok = ok

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("simulated Expo API failure")


def test_send_push_notification_returns_true_on_success(monkeypatch):
    import src.app.core.push as push_module

    monkeypatch.setattr(
        push_module.requests, "post", lambda *a, **k: _FakeResponse(ok=True)
    )
    assert send_push_notification("tok", "title", "body") is True


def test_send_push_notification_returns_false_and_never_raises_on_failure(monkeypatch):
    import src.app.core.push as push_module

    monkeypatch.setattr(
        push_module.requests, "post", lambda *a, **k: _FakeResponse(ok=False)
    )
    assert send_push_notification("tok", "title", "body") is False


def test_send_push_notification_returns_false_for_blank_token():
    assert send_push_notification("", "title", "body") is False


def test_send_push_notifications_no_valid_tokens_is_a_noop_never_raises():
    # No tokens at all, and a list of only falsy tokens: neither is a
    # failure — nothing was attempted.
    send_push_notifications([], "title", "body")
    send_push_notifications([None, "", None], "title", "body")


def test_send_push_notifications_partial_failure_does_not_raise_and_logs(monkeypatch):
    import src.app.core.push as push_module

    calls = {"n": 0}

    def _fake_send(token, title, message, notif_level="urgent", data=None):
        calls["n"] += 1
        return token != "bad"

    monkeypatch.setattr(push_module, "send_push_notification", _fake_send)

    logged = []
    monkeypatch.setattr(push_module.logger, "warning", lambda msg: logged.append(msg))

    # Should not raise despite one failure.
    send_push_notifications(["good", "bad"], "title", "body")

    assert calls["n"] == 2
    assert any("1 of 2" in msg for msg in logged)


def test_send_push_notifications_total_failure_raises_push_delivery_error(monkeypatch):
    import src.app.core.push as push_module

    monkeypatch.setattr(push_module, "send_push_notification", lambda *a, **k: False)

    with pytest.raises(PushDeliveryError, match="2"):
        send_push_notifications(["tok-a", "tok-b"], "title", "body")


def test_send_push_notifications_all_success_does_not_raise(monkeypatch):
    import src.app.core.push as push_module

    monkeypatch.setattr(push_module, "send_push_notification", lambda *a, **k: True)

    send_push_notifications(["tok-a", "tok-b"], "title", "body")
