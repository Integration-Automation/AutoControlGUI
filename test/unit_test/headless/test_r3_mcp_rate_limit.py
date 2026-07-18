"""Round-3 regression: ac_rate_limit must honour changed rate/capacity.

The handler used ``_RATE_LIMITERS.setdefault(name, TokenBucket(rate,
capacity))`` so the *second* call with the same name but a new rate or
capacity silently kept the original bucket. The fix rebuilds the bucket when
either parameter changes while reusing it when they do not.
"""
import uuid

from je_auto_control.utils.mcp_server.tools._handlers import rate_limit


def _name() -> str:
    return f"r3-{uuid.uuid4().hex}"


def test_changed_capacity_rebuilds_the_bucket():
    name = _name()
    first = rate_limit(name, rate=1.0, capacity=1.0)
    assert first["acquired"] is True  # drains the single token

    # Same name, larger capacity: previously ignored (bucket still cap 1, so
    # this second acquire would fail with ~0 tokens). Now it rebuilds.
    second = rate_limit(name, rate=1.0, capacity=5.0)
    assert second["acquired"] is True
    assert second["tokens"] > 3.5


def test_unchanged_params_reuse_the_same_bucket():
    name = _name()
    first = rate_limit(name, rate=100.0, capacity=100.0)
    second = rate_limit(name, rate=100.0, capacity=100.0)
    # A reused bucket keeps draining; a rebuilt one would reset to full.
    assert second["tokens"] < first["tokens"]
