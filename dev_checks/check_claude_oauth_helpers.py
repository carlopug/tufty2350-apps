"""Desktop-only sanity check for claude_oauth's pure helper functions.

Run with any desktop Python 3.10+. Never touches State or the network
(the pure functions checked here don't use either), but importing
claude_oauth.py at all still requires two platform shims because the
*module itself* imports MicroPython-only things at the top:

- `ubinascii` doesn't exist on desktop Python -> aliased to the stdlib
  `binascii`, which has the same `b2a_base64` API.
- `requests` isn't installed in this venv (and must never actually be
  called here) -> a fake module whose get/post raise if invoked.
- `time.mktime()` on MicroPython takes an 8-tuple (year, month, mday,
  hour, minute, second, weekday, yearday); CPython's `time.mktime()`
  requires a 9-tuple (it wants isdst too). `_iso_to_ts` is written for
  the MicroPython signature (correct for the real device), so this
  check pads the tuple by one field before delegating to the real
  `time.mktime` — a desktop-only shim, not a change to claude_oauth.py.
"""
import binascii
import os
import sys
import time
import types

sys.modules.setdefault("ubinascii", binascii)

fake_requests = types.ModuleType("requests")


def _network_forbidden(*_args, **_kwargs):
    raise AssertionError("this check must not touch the network")


fake_requests.get = _network_forbidden
fake_requests.post = _network_forbidden
sys.modules.setdefault("requests", fake_requests)

_real_mktime = time.mktime


def _mktime_8_or_9_tuple(value):
    value = tuple(value)
    if len(value) == 8:
        value = value + (0,)
    return _real_mktime(value)


time.mktime = _mktime_8_or_9_tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "claude_monitor"))

import claude_oauth as co

# _to_pct: normalises both 0..1 fractions and 0..100 values, clamped.
assert co._to_pct(0.5) == 50
assert co._to_pct(75) == 75
assert co._to_pct(1.0) == 100
assert co._to_pct(150) == 100
assert co._to_pct(-10) == 0

# _urlquote: RFC3986-ish "safe" characters pass through, space becomes
# %20, everything else is percent-encoded.
assert co._urlquote("hello world") == "hello%20world"
assert co._urlquote("a-b_c.d~e") == "a-b_c.d~e"
assert co._urlquote("a/b") == "a%2Fb"

# _urlencode: joins encoded key=value pairs with "&", preserving dict order.
assert co._urlencode({"a": "1", "b": "x y"}) == "a=1&b=x%20y"

# _iso_to_ts: epoch base differs between desktop CPython and MicroPython
# (a known, documented caveat — see the spec's "Rischi noti" section), so
# only relative differences are portable to assert on here.
ts_start = co._iso_to_ts("2025-01-01T00:00:00Z")
ts_plus_10s = co._iso_to_ts("2025-01-01T00:00:10Z")
assert ts_start is not None
assert ts_plus_10s - ts_start == 10
assert co._iso_to_ts("not-a-date") is None

# _map_usage: maps the Anthropic usage payload shape into flat pct/EUR
# fields.
sample = {
    "five_hour": {"utilization": 0.42, "resets_at": "2025-01-01T05:00:00Z"},
    "seven_day": {"utilization": 0.10, "resets_at": "2025-01-08T00:00:00Z"},
    "extra_usage": {"is_enabled": True, "monthly_limit": 2000, "used_credits": 550},
}
result = co._map_usage(sample)
assert result["plan"] == "pro"
assert result["session_pct_used"] == 42
assert result["session_pct_remaining"] == 58
assert result["weekly_pct_used"] == 10
assert result["credits_limit_eur"] == 20.0
assert result["credits_spent_eur"] == 5.5
assert result["credits_balance_eur"] == 14.5
# Raw ISO strings must survive alongside the computed epoch values --
# localtime.py's dashboard display shifts these directly, it doesn't use
# the _ts fields (see the comment in _map_usage for why).
assert result["session_resets_at_iso"] == "2025-01-01T05:00:00Z"
assert result["weekly_resets_at_iso"] == "2025-01-08T00:00:00Z"

# extra_usage disabled -> no credits keys, no session keys without utilization.
sample_disabled = {"five_hour": {}, "seven_day": {}, "extra_usage": {"is_enabled": False}}
result_disabled = co._map_usage(sample_disabled)
assert "credits_limit_eur" not in result_disabled
assert "session_pct_used" not in result_disabled

print("OK")
