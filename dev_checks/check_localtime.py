"""Desktop-only check for localtime.py's pure DST-rule and formatting logic.

Run with any desktop Python 3.10+. No network involved at all -- this
module no longer calls any external service (see localtime.py's docstring
for why). The only shim needed is for time.mktime()'s semantics:

- `time.mktime()` on MicroPython has no timezone database at all: it just
  packs a (year, month, day, hour, minute, second, ...) tuple into seconds
  since its epoch with no adjustment, treating the fields as naive/UTC.
  CPython's `time.mktime()` is NOT equivalent -- it interprets the tuple as
  *local time on the machine running this check* and converts it to a UTC
  epoch using that machine's own timezone, which silently shifts every
  absolute value it touches by an unrelated, environment-dependent amount
  (this bit an earlier version of this same check on a developer machine
  set to a non-UTC timezone). This check replaces time.mktime with
  `calendar.timegm`, which is exactly the naive/UTC-only semantics
  MicroPython's mktime actually has -- the standard-library function
  documented as gmtime()'s inverse, with no local-timezone involvement.
"""
import calendar
import os
import sys
import time

time.mktime = calendar.timegm

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "claude_monitor"))
import localtime as lt  # noqa: E402  (must come after the mktime shim above)

# --- DST transition dates, checked against known real-world EU dates ------
# 2024: DST starts 2024-03-31, ends 2024-10-27 (both confirmed Sundays).
# 2025: DST starts 2025-03-30, ends 2025-10-26 (both confirmed Sundays).

def _ts(year, month, day, hour=0, minute=0):
    return calendar.timegm((year, month, day, hour, minute, 0, 0, 0))


# Just before the 2024 spring transition (01:00 UTC on 2024-03-31): still CET.
assert lt.rome_utc_offset_seconds(_ts(2024, 3, 31, 0, 59)) == 3600
# Exactly at and just after the transition instant: CEST.
assert lt.rome_utc_offset_seconds(_ts(2024, 3, 31, 1, 0)) == 7200
assert lt.rome_utc_offset_seconds(_ts(2024, 6, 15, 12, 0)) == 7200

# Just before the 2024 autumn transition (01:00 UTC on 2024-10-27): still CEST.
assert lt.rome_utc_offset_seconds(_ts(2024, 10, 27, 0, 59)) == 7200
# Exactly at and just after: back to CET.
assert lt.rome_utc_offset_seconds(_ts(2024, 10, 27, 1, 0)) == 3600
assert lt.rome_utc_offset_seconds(_ts(2024, 12, 25, 12, 0)) == 3600

# A different year, to confirm the "last Sunday" calculation isn't
# hardcoded to 2024's specific dates.
assert lt.rome_utc_offset_seconds(_ts(2025, 3, 30, 0, 59)) == 3600
assert lt.rome_utc_offset_seconds(_ts(2025, 3, 30, 1, 0)) == 7200
assert lt.rome_utc_offset_seconds(_ts(2025, 10, 26, 0, 59)) == 7200
assert lt.rome_utc_offset_seconds(_ts(2025, 10, 26, 1, 0)) == 3600

# --- format_local -----------------------------------------------------------
assert lt.format_local(_ts(2025, 1, 15, 14, 30), 3600) == "15/01 15:30"
assert lt.format_local(_ts(2025, 7, 15, 14, 30), 7200) == "15/07 16:30"
# Day rollover: 23:30 UTC + 2h -> next day 01:30.
assert lt.format_local(_ts(2025, 1, 1, 23, 30), 7200) == "02/01 01:30"

# --- shift_and_format (used for Anthropic's `resets_at`, always UTC 'Z') ----
assert lt.shift_and_format("2025-01-01T05:00:00.000Z", 3600) == "01/01 06:00"
assert lt.shift_and_format("2025-01-01T05:00:00.000Z", 7200) == "01/01 07:00"
# Day rollover.
assert lt.shift_and_format("2025-01-01T23:30:00.000Z", 7200) == "02/01 01:30"
# Negative offset, rolling back into the previous month (exercises the
# same gmtime()-based rollover even though Rome's own offset is never
# negative -- shift_and_format() is generic).
assert lt.shift_and_format("2025-01-01T01:00:00.000Z", -7200) == "31/12 23:00"

print("OK")
