"""Local time for Europe/Rome, computed directly from the device's own UTC
clock plus the EU-wide DST rule -- no external time service. Italy (like
every other EU member state) follows a single simple rule: clocks move
forward at 01:00 UTC on the last Sunday of March, and back at 01:00 UTC on
the last Sunday of October. That's the whole rule, unlike the per-region
DaylightSavingPolicy machinery in the firmware's own `clock` app (built to
handle many different countries' rules, most of which do change).

This needs the device's own clock to be roughly correct in the first
place -- see rtc.time_from_ntp(), already used the same way by
apps/iss_tracker elsewhere in this firmware.

A prior version of this module called worldtimeapi.org for the same
result; that call never succeeded on real hardware (verified on-device,
2026-08-29), so this now avoids the external dependency entirely instead
of chasing why one specific free API endpoint wasn't reachable.
"""
import time


def _last_sunday_ts(year, month):
    """UTC timestamp of 00:00 on the last Sunday of (year, month).

    Indexes into gmtime()'s result rather than unpacking a fixed count of
    fields: MicroPython's gmtime() returns an 8-tuple, CPython's a 9-tuple
    (it adds tm_isdst) -- indexing works for either."""
    if month == 12:
        next_month_first = time.mktime((year + 1, 1, 1, 0, 0, 0, 0, 0))
    else:
        next_month_first = time.mktime((year, month + 1, 1, 0, 0, 0, 0, 0))
    last_day_tuple = time.gmtime(next_month_first - 86400)
    last_day_year, last_day_month, last_day, weekday = (
        last_day_tuple[0], last_day_tuple[1], last_day_tuple[2], last_day_tuple[6]
    )
    sunday_day = last_day - ((weekday + 1) % 7)
    return time.mktime((last_day_year, last_day_month, sunday_day, 0, 0, 0, 0, 0))


def rome_utc_offset_seconds(now_utc_ts):
    """3600 (CET, +1h) or 7200 (CEST, +2h) for the given UTC timestamp,
    per the EU DST rule."""
    year = time.gmtime(now_utc_ts)[0]
    dst_start = _last_sunday_ts(year, 3) + 3600   # 01:00 UTC, not midnight
    dst_end = _last_sunday_ts(year, 10) + 3600
    return 7200 if dst_start <= now_utc_ts < dst_end else 3600


def format_local(utc_ts, offset_seconds):
    """Format a UTC epoch timestamp as local wall-clock 'gg/mm HH:MM'."""
    t = time.gmtime(utc_ts + offset_seconds)
    return "{:02d}/{:02d} {:02d}:{:02d}".format(t[2], t[1], t[3], t[4])


def _parse_iso_fields(iso):
    """(y, mo, d, h, mi, se) from an ISO 8601 string, ignoring whatever
    follows the fixed-width "HH:MM:SS" (fractional seconds, a trailing
    'Z', an explicit offset -- all irrelevant here, Anthropic's
    `resets_at` is always UTC)."""
    date_part, rest = iso.split("T")
    y, mo, d = [int(x) for x in date_part.split("-")]
    h, mi, se = [int(x) for x in rest[:8].split(":")]
    return y, mo, d, h, mi, se


def shift_and_format(iso_utc, offset_seconds):
    """Format a UTC ISO timestamp (e.g. Anthropic's `resets_at`) as local
    wall-clock time, given a known UTC offset in seconds."""
    y, mo, d, h, mi, se = _parse_iso_fields(iso_utc)
    utc_ts = time.mktime((y, mo, d, h, mi, se, 0, 0))
    return format_local(utc_ts, offset_seconds)


def seconds_remaining(iso_utc, now_ts):
    """Seconds between now_ts and a UTC ISO timestamp (e.g. `resets_at`),
    clamped to 0 once it's in the past (clock skew, or the badge just
    hasn't polled fresh usage since the actual reset happened)."""
    y, mo, d, h, mi, se = _parse_iso_fields(iso_utc)
    target_ts = time.mktime((y, mo, d, h, mi, se, 0, 0))
    return max(0, target_ts - now_ts)


def format_duration(seconds):
    """Compact countdown string: "42s", "12m", "3h 42m", or "2g 14h" --
    picks the coarsest unit that still lets the reader see it counting
    down (so "0h 00m" never quietly sits there for a whole minute)."""
    seconds = int(seconds)
    if seconds < 60:
        return "{}s".format(seconds)
    minutes = seconds // 60
    if minutes < 60:
        return "{}m".format(minutes)
    hours = minutes // 60
    minutes %= 60
    if hours < 24:
        return "{}h {:02d}m".format(hours, minutes)
    days = hours // 24
    hours %= 24
    return "{}g {:02d}h".format(days, hours)
