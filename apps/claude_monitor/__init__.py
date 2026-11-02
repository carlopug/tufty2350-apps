import sys
import os
import time

sys.path.insert(0, "/system/apps/claude_monitor")
os.chdir("/system/apps/claude_monitor")

import wifi
try:
    import secrets
except ImportError:  # nessun secrets.py: CollegamentoWifi mostrera' "Usa Wifi Config"
    secrets = None
from claude_oauth import ClaudeClient
from login_server import LoginServer
from collegamento import CollegamentoWifi
import localtime

# The app targets Tufty 2350's native 320x240 framebuffer.
badge.mode(HIRES | VSYNC)
screen.antialias = image.X2
screen.font = font.sins

# WiFi: only the network in secrets.py, which apps/wifi_config keeps in
# sync with the last network that worked (the multi-network logic lives
# there now, see docs/wifi-config.md). CollegamentoWifi never lets the
# firmware's wifi.connect() retry loop reach fatal_error() (= badge
# reboot): on failure the app shows "Usa Wifi Config..." instead.
wifi_link = CollegamentoWifi(wifi, getattr(secrets, "WIFI_SSID", None))
wifi_state = "attesa"

MODE_LOGIN = "login"
MODE_DASHBOARD = "dashboard"

LOGIN_STAGE_WIFI = "wifi"
LOGIN_STAGE_SERVING = "serving"

POLL_INTERVAL_MS = 60000
LOGIN_PORT = 8080
# Optional label shown bottom-right on the dashboard (e.g. the Claude account
# email), read from CLAUDE_ACCOUNT_LABEL in secrets.py; empty = not shown.
EMAIL_TEXT = str(getattr(secrets, "CLAUDE_ACCOUNT_LABEL", "") or "")

BG_COLOR = color.rgb(20, 30, 45)
PANEL_COLOR = color.rgb(31, 53, 82)
TEXT_COLOR = color.rgb(245, 247, 250)
DIM_TEXT_COLOR = color.rgb(150, 165, 188)
BAR_TRACK_COLOR = color.rgb(58, 70, 88)
BAR_FILL_COLOR = color.rgb(242, 169, 59)
BAR_WARN_COLOR = color.rgb(230, 60, 46)

# One shared accent for every countdown element (refresh ring, session and
# weekly mini-rings + duration text) so they read as one family of
# information, distinct from the amber/red usage bars above.
COUNTDOWN_COLOR = color.rgb(90, 200, 220)

SESSION_WINDOW_SECONDS = 5 * 3600
WEEKLY_WINDOW_SECONDS = 7 * 86400

BAR_X = 16
BAR_WIDTH = screen.width - 32
BAR_HEIGHT = 14
BAR_RADIUS = BAR_HEIGHT // 2
BAR_Y = {"session": 66, "weekly": 116, "credits": 166}

REFRESH_RING_RADIUS = 9
REFRESH_RING_Y = 23
REFRESH_RING_GAP = 8  # px between the ring's edge and whatever sits to its right
MINI_RING_RADIUS = 7
MINI_RING_GAP = 6  # px between a mini-ring's edge and the label that follows it

header_panel = shape.rounded_rectangle(8, 8, screen.width - 16, 30, 10)
bar_tracks = {
    key: shape.rounded_rectangle(BAR_X, y, BAR_WIDTH, BAR_HEIGHT, BAR_RADIUS)
    for key, y in BAR_Y.items()
}

# Track (background) circles for the two mini-rings: position/radius never
# change, so precompute once -- same idiom as header_panel/bar_tracks above.
# The refresh ring has no fixed track: its x depends on now_text's measured
# width (it sits just left of the clock), which varies, so it's built fresh
# each frame in draw_countdown_ring() instead. The filled pie wedge on top
# of every ring is always recreated every frame regardless, since its angle
# changes -- same idiom already used for the linear bars' fill.
mini_ring_tracks = {
    key: shape.circle(BAR_X + MINI_RING_RADIUS, BAR_Y[key] - 16 + 5, MINI_RING_RADIUS)
    for key in ("session", "weekly")
}

client = ClaudeClient()
server = LoginServer(LOGIN_PORT)

mode = MODE_DASHBOARD if client.has_credentials() else MODE_LOGIN
login_stage = LOGIN_STAGE_WIFI
login_message = ""
# True from the moment enter_login_mode() runs until a login actually
# succeeds. This -- not has_credentials() -- is what the SERVING stage
# checks to decide when to leave login mode. Keeping it separate from
# the credentials themselves means a dropped WiFi connection, a failed
# server bind, or simply changing your mind and pressing HOME never
# leaves the badge logged out with no way back short of redoing the
# full browser OAuth flow.
# A fresh install (no stored credentials) starts directly in MODE_LOGIN
# at the line above without ever calling enter_login_mode() -- so this
# has to mirror that same condition, or the SERVING stage's `if not
# login_pending` would immediately (and wrongly) bounce a first-ever
# boot straight to an empty dashboard, skipping login entirely.
login_pending = mode == MODE_LOGIN

last_poll_ticks = None
usage = {}

# True once rtc.time_from_ntp() has succeeded at least once this boot --
# mirrors apps/iss_tracker's own time_set flag. Until then, time.time()
# may hold whatever the hardware RTC last had (possibly correct already,
# via a previous NTP sync from another app -- see badgeware/rtc.py's own
# boot-time propagation -- or possibly nothing meaningful yet).
time_synced = False
now_text = ""
now_ts = None
tz_offset_seconds = None


def enter_login_mode(message="", clear=False):
    global mode, login_stage, login_message, login_pending, usage, last_poll_ticks
    # Only the automatic oauth_expired path (which already knows there is
    # no refresh token left to try) passes clear=True. The manual A+C
    # path does not clear anything up front: if the user changes their
    # mind, drops WiFi mid-flow, or the setup server fails to bind, the
    # existing credentials are still sitting there untouched and the app
    # is still usable. A successful login overwrites them anyway via
    # exchange_code() -> _write_credentials().
    if clear:
        client.clear_credentials()
    login_pending = True
    mode = MODE_LOGIN
    login_stage = LOGIN_STAGE_WIFI
    login_message = message
    # Otherwise the dashboard would keep showing the previous account's
    # (or the pre-logout) numbers for up to a full POLL_INTERVAL_MS after
    # returning, since last_poll_ticks still points at the old cycle.
    usage = {}
    last_poll_ticks = None
    server.stop()


def handle_submitted_code(code, code_verifier, code_state):
    global login_pending
    try:
        client.exchange_code(code, code_verifier, code_state)
    except OSError as error:
        return False, "Errore di rete: {}".format(error)
    login_pending = False
    return True, "Login riuscito! Torno alla dashboard..."


def start_login_server():
    url, verifier, oauth_state = client.build_authorize_url()
    server.on_code = handle_submitted_code
    try:
        server.start(url, verifier, oauth_state)
    except OSError as error:
        # Bind/listen can fail (e.g. the port is already bound from a
        # previous run). Don't let it crash the frame loop -- the IP
        # screen will just sit unreachable, which is a stuck UI, not a
        # dead app; HOME still exits (A+C is inert here, it only fires
        # from MODE_DASHBOARD), and since enter_login_mode() no longer
        # clears credentials up front, the badge is still fully usable
        # after a HOME-and-relaunch even if this bind never succeeds.
        print("login server failed to start:", error)


def draw_lines(lines, x, y, line_height, pen):
    screen.pen = pen
    for line in lines:
        screen.text(line, x, y)
        y += line_height


def draw_login_screen():
    screen.pen = BG_COLOR
    screen.clear()

    if login_stage == LOGIN_STAGE_WIFI:
        draw_lines(
            ["Connessione al WiFi di casa...", "(serve per il login via browser)"],
            16, 40, 14, TEXT_COLOR
        )
        if login_message:
            draw_lines([login_message], 16, 80, 14, DIM_TEXT_COLOR)
        return

    ip = wifi.ip() or "?"
    draw_lines(
        [
            "Login Claude Monitor",
            "",
            "Apri dal telefono/PC sulla",
            "stessa rete:",
            "http://{}:{}/".format(ip, LOGIN_PORT),
        ],
        16, 30, 16, TEXT_COLOR
    )

    if login_message:
        draw_lines([login_message], 16, 150, 14, DIM_TEXT_COLOR)


def draw_countdown_ring(cx, cy, r, frac, track=None):
    """Draws a full circle that empties counterclockwise as frac goes from
    1 (just refreshed / far from reset) to 0 (due now). shape.pie() angles
    run clockwise from straight up (0deg); fixing the wedge's start at 0
    and shrinking its end towards 0 as frac shrinks means the "eaten"
    (empty) slice always opens at the top and grows towards 11, 10, 9
    o'clock -- i.e. counterclockwise -- while the pie's own fill covers
    the clockwise side. See references/api/shape.md's pie()/circle() docs.

    `track` lets a caller reuse a precomputed shape.circle() for a ring
    whose position never moves (the mini-rings); omit it for one whose
    position varies frame to frame (the refresh ring)."""
    screen.pen = BAR_TRACK_COLOR
    screen.shape(track if track is not None else shape.circle(cx, cy, r))
    frac = max(0.0, min(1.0, frac))
    if frac > 0:
        screen.pen = COUNTDOWN_COLOR
        screen.shape(shape.pie(cx, cy, r, 0, 360 * frac))


def countdown_fraction_and_text(resets_at_iso, window_seconds):
    """(fraction_remaining, duration_text) for a *_resets_at_iso field, or
    (None, None) if that field isn't in `usage` yet (e.g. no poll has
    succeeded since login)."""
    if not resets_at_iso or now_ts is None:
        return None, None
    try:
        remaining = localtime.seconds_remaining(resets_at_iso, now_ts)
    except (ValueError, IndexError):
        return None, None
    return remaining / window_seconds, localtime.format_duration(remaining)


def draw_bar(key, label, pct, reset_text=None, countdown_frac=None, countdown_text=None):
    y = BAR_Y[key]
    label_x = BAR_X

    if countdown_frac is not None:
        ring_cx = BAR_X + MINI_RING_RADIUS
        ring_cy = y - 16 + 5
        draw_countdown_ring(ring_cx, ring_cy, MINI_RING_RADIUS, countdown_frac, mini_ring_tracks[key])
        label_x = BAR_X + 2 * MINI_RING_RADIUS + MINI_RING_GAP

    screen.pen = TEXT_COLOR
    screen.text(label, label_x, y - 16)

    if countdown_text:
        label_width, _ = screen.measure_text(label)
        screen.pen = COUNTDOWN_COLOR
        screen.text(countdown_text, label_x + label_width + 8, y - 16)

    if reset_text:
        screen.pen = DIM_TEXT_COLOR
        reset_width, _ = screen.measure_text(reset_text)
        screen.text(reset_text, BAR_X + BAR_WIDTH - reset_width, y - 16)

    screen.pen = BAR_TRACK_COLOR
    screen.shape(bar_tracks[key])

    if pct is not None:
        fill_width = max(0, min(BAR_WIDTH, (BAR_WIDTH * pct) / 100))
        if fill_width > 0:
            # A plain screen.rectangle() has square corners, which shows
            # as a hard edge poking out of the track's rounded left cap.
            # Draw the fill as its own rounded_rectangle instead -- same
            # idiom as online/firmware/apps/snarky_sciuridae/ui.py's
            # draw_bar(), which insets a smaller rounded fill inside a
            # rounded track. Clamp the radius so it never exceeds half
            # the fill's own width (a very thin sliver would otherwise
            # ask for a radius bigger than the shape itself).
            fill_radius = min(BAR_RADIUS, fill_width / 2)
            screen.pen = BAR_WARN_COLOR if pct >= 90 else BAR_FILL_COLOR
            screen.shape(shape.rounded_rectangle(BAR_X, y, fill_width, BAR_HEIGHT, fill_radius))

        screen.pen = TEXT_COLOR
        value_text = "{}%".format(pct)
        text_width, _ = screen.measure_text(value_text)
        screen.text(value_text, BAR_X + BAR_WIDTH - text_width - 4, y + 1)


def draw_dashboard():
    screen.pen = BG_COLOR
    screen.clear()

    screen.pen = PANEL_COLOR
    screen.shape(header_panel)
    screen.pen = TEXT_COLOR
    screen.text("CLAUDE USAGE MONITOR", 20, 18)

    if now_text:
        now_width, _ = screen.measure_text(now_text)
        now_x = screen.width - now_width - 20
        screen.text(now_text, now_x, 18)

        # Refresh countdown: only meaningful once the first poll has
        # actually happened (last_poll_ticks is None before that), same
        # guard used elsewhere for "no data yet" states. Sits just left of
        # the clock, whose width varies frame to frame with its own text.
        if last_poll_ticks is not None:
            refresh_frac = 1 - (badge.ticks - last_poll_ticks) / POLL_INTERVAL_MS
            ring_cx = now_x - REFRESH_RING_GAP - REFRESH_RING_RADIUS
            draw_countdown_ring(ring_cx, REFRESH_RING_Y, REFRESH_RING_RADIUS, refresh_frac)

    session_frac, session_countdown_text = countdown_fraction_and_text(
        usage.get("session_resets_at_iso"), SESSION_WINDOW_SECONDS
    )
    draw_bar(
        "session", "Sessione (5h)", usage.get("session_pct_used"),
        format_reset(usage.get("session_resets_at_iso")),
        session_frac, session_countdown_text
    )

    weekly_frac, weekly_countdown_text = countdown_fraction_and_text(
        usage.get("weekly_resets_at_iso"), WEEKLY_WINDOW_SECONDS
    )
    draw_bar(
        "weekly", "Settimanale (7d)", usage.get("weekly_pct_used"),
        format_reset(usage.get("weekly_resets_at_iso")),
        weekly_frac, weekly_countdown_text
    )

    credits_limit = usage.get("credits_limit_eur")
    credits_spent = usage.get("credits_spent_eur")
    if not usage:
        # Distinct from "no extra-usage limit configured" below: this is
        # "no data has arrived yet at all" (still connecting, or waiting
        # on the first poll) -- saying "nessun limite configurato" here
        # would be stating something false about the account, not just
        # an empty state.
        draw_bar("credits", "Crediti (EUR)", None)
        screen.pen = DIM_TEXT_COLOR
        status = "Connessione al WiFi..." if not wifi.is_connected() else "In attesa dei dati..."
        screen.text(status, BAR_X, BAR_Y["credits"] + 20)
    elif credits_limit:
        credits_pct = int(min(100, (credits_spent / credits_limit) * 100))
        draw_bar("credits", "Crediti (EUR)", credits_pct)
        screen.pen = DIM_TEXT_COLOR
        screen.text("{} / {} EUR".format(credits_spent, credits_limit), BAR_X, BAR_Y["credits"] + 20)
    else:
        draw_bar("credits", "Crediti (EUR)", None)
        screen.pen = DIM_TEXT_COLOR
        screen.text("Nessun limite extra configurato", BAR_X, BAR_Y["credits"] + 20)

    screen.pen = DIM_TEXT_COLOR
    screen.text("A+C: rifai login", BAR_X, screen.height - 20)
    if EMAIL_TEXT:
        email_width, _ = screen.measure_text(EMAIL_TEXT)
        screen.text(EMAIL_TEXT, screen.width - email_width - BAR_X, screen.height - 20)


def poll_if_due():
    global last_poll_ticks, usage

    if last_poll_ticks is not None and (badge.ticks - last_poll_ticks) < POLL_INTERVAL_MS:
        return

    last_poll_ticks = badge.ticks
    try:
        result = client.poll_usage()
    except (OSError, ValueError) as error:
        # A transient network/TLS/JSON failure must not crash the app --
        # just skip this cycle, the next scheduled poll tries again.
        print("poll_usage failed:", error)
        return

    if result is None:
        return

    if result.get("_error") == "oauth_expired":
        # This is the one path that already knows there's no refresh
        # token left to try -- clearing here is safe and avoids leaving
        # a dead access token sitting in State.
        enter_login_mode("Sessione scaduta, rifai il login", clear=True)
        return

    usage = result


def sync_time_if_needed():
    global time_synced
    if time_synced:
        return
    try:
        rtc.time_from_ntp()
        time_synced = True
    except OSError as error:
        print("NTP sync failed:", error)


def refresh_local_time():
    # Pure local computation now (no network call) -- cheap enough to run
    # every frame, no throttling needed.
    global now_text, now_ts, tz_offset_seconds

    now_ts = time.time()
    tz_offset_seconds = localtime.rome_utc_offset_seconds(now_ts)
    now_text = localtime.format_local(now_ts, tz_offset_seconds)


def format_reset(iso_field):
    if not iso_field:
        return None
    try:
        return "reset {}".format(localtime.shift_and_format(iso_field, tz_offset_seconds))
    except (ValueError, IndexError):
        return None


def handle_buttons():
    if mode == MODE_DASHBOARD and badge.held(BUTTON_A) and badge.held(BUTTON_C):
        enter_login_mode()


def init():
    pass


def draw_no_wifi_screen():
    screen.pen = BG_COLOR
    screen.clear()
    screen.pen = PANEL_COLOR
    screen.shape(shape.rounded_rectangle(8, 6, screen.width - 16, 24, 8))
    screen.pen = TEXT_COLOR
    screen.text("Claude Monitor", 16, 11)
    screen.pen = PANEL_COLOR
    screen.shape(shape.rounded_rectangle(16, 70, screen.width - 32, 80, 10))
    for text, y, pen in (("WiFi non disponibile", 88, BAR_WARN_COLOR),
                         ("Usa Wifi Config per gestire", 112, TEXT_COLOR),
                         ("le reti WiFi", 128, TEXT_COLOR),
                         ("HOME: torna al menu", screen.height - 16, DIM_TEXT_COLOR)):
        width, _ = screen.measure_text(text)
        screen.pen = pen
        screen.text(text, (screen.width - width) // 2, y)


def update():
    global mode, login_stage, wifi_state

    wifi_state = wifi_link.tick(badge.ticks)
    if wifi_state == "fallito":
        server.stop()
        draw_no_wifi_screen()
        return
    wifi_ok = wifi_state == "connesso"

    handle_buttons()

    if mode == MODE_LOGIN:
        if login_stage == LOGIN_STAGE_WIFI:
            if wifi_ok:
                login_stage = LOGIN_STAGE_SERVING
                start_login_server()
        else:
            if not wifi_ok:
                # Connection dropped after the setup page was already
                # being served: fall back to the WIFI stage so a fresh
                # server gets bound once reconnected, instead of leaving
                # a dead, unreachable IP on screen forever.
                server.stop()
                login_stage = LOGIN_STAGE_WIFI
            else:
                server.poll()
                if not login_pending:
                    mode = MODE_DASHBOARD
                    server.stop()

        draw_login_screen()
    else:
        # Dashboard mode needs the WiFi connection alive too (wifi_link
        # above keeps it up, reconnecting once if it drops).
        if wifi_ok:
            sync_time_if_needed()
            poll_if_due()
        # Pure computation, no network -- runs whether or not WiFi is up,
        # using whatever the device's own clock currently holds.
        refresh_local_time()
        draw_dashboard()


def on_exit():
    server.stop()


init()
run(update)
