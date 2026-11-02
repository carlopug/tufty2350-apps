"""OAuth PKCE + polling usage Claude (Pro/Max) for Tufty 2350 / Badgeware."""

import os
import time
import ubinascii
import hashlib
import requests

CLIENT_ID    = '9d1c250a-e61b-44d9-88ed-5944d1962f5e'
AUTH_URL     = 'https://claude.com/cai/oauth/authorize'
TOKEN_URL    = 'https://console.anthropic.com/v1/oauth/token'
USAGE_URL    = 'https://api.anthropic.com/api/oauth/usage'
REDIRECT_URI = 'https://platform.claude.com/oauth/code/callback'
SCOPES       = ('org:create_api_key user:profile user:inference '
                'user:sessions:claude_code user:mcp_servers user:file_upload')
BETA_HEADER  = 'oauth-2025-04-20'

STATE_NAME   = 'claude_monitor'
MIN_INTERVAL = 30
BACKOFF_429  = 180


def _b64url(data):
    b = ubinascii.b2a_base64(data).strip()
    b = b.replace(b'+', b'-').replace(b'/', b'_').replace(b'=', b'')
    return b.decode()


def _urlquote(s):
    safe = '-_.~'
    out = []
    for ch in s:
        if ch.isalpha() or ch.isdigit() or ch in safe:
            out.append(ch)
        elif ch == ' ':
            out.append('%20')
        else:
            out.append('%{:02X}'.format(ord(ch)))
    return ''.join(out)


def _urlencode(d):
    return '&'.join('{}={}'.format(k, _urlquote(v)) for k, v in d.items())


def _to_pct(v):
    f = float(v)
    if f <= 1.0:
        f *= 100
    return min(100, max(0, round(f)))


def _iso_to_ts(iso):
    try:
        s = iso.replace('Z', '').split('.')[0]
        date_part, time_part = s.split('T')
        y, mo, d = [int(x) for x in date_part.split('-')]
        h, mi, se = [int(x) for x in time_part.split(':')]
        return time.mktime((y, mo, d, h, mi, se, 0, 0))
    except Exception:
        return None


def _map_usage(data):
    out = {'plan': 'pro'}

    fh = data.get('five_hour') or {}
    if fh.get('utilization') is not None:
        spct = _to_pct(fh['utilization'])
        out['session_pct_used'] = spct
        out['session_pct_remaining'] = 100 - spct
    if fh.get('resets_at'):
        out['session_resets_at_ts'] = _iso_to_ts(fh['resets_at'])
        # Raw ISO string kept alongside the computed epoch value: the
        # dashboard's local-time display (see localtime.py) needs the
        # original UTC timestamp to shift, not this module's epoch value,
        # which may not use the same epoch base as any other time source.
        out['session_resets_at_iso'] = fh['resets_at']

    sd = data.get('seven_day') or {}
    if sd.get('utilization') is not None:
        wpct = _to_pct(sd['utilization'])
        out['weekly_pct_used'] = wpct
        out['weekly_pct_remaining'] = 100 - wpct
    if sd.get('resets_at'):
        out['weekly_resets_at_ts'] = _iso_to_ts(sd['resets_at'])
        out['weekly_resets_at_iso'] = sd['resets_at']

    eu = data.get('extra_usage') or {}
    if eu.get('is_enabled') and eu.get('monthly_limit') is not None:
        limit_cents = float(eu['monthly_limit'])
        used_cents = float(eu.get('used_credits', 0))
        out['credits_limit_eur'] = round(limit_cents / 100, 2)
        out['credits_spent_eur'] = round(used_cents / 100, 2)
        out['credits_balance_eur'] = round((limit_cents - used_cents) / 100, 2)

    return out


class ClaudeClient:

    def __init__(self):
        self._data = {}
        State.load(STATE_NAME, self._data)
        self._last_call = 0
        self._retry_after = 0
        self._refresh_retry_after = 0

    def has_credentials(self):
        return bool(self._data.get('access_token'))

    def clear_credentials(self):
        self._data = {}
        # Also reset backoff bookkeeping -- otherwise a freshly logged-in
        # account (possibly a different one) could inherit up to
        # BACKOFF_429 (or BACKOFF_429 * 4 for a refresh backoff) seconds
        # of the previous account's rate-limit backoff.
        self._last_call = 0
        self._retry_after = 0
        self._refresh_retry_after = 0
        State.save(STATE_NAME, self._data)

    def build_authorize_url(self):
        verifier = _b64url(os.urandom(32))
        challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
        state = _b64url(os.urandom(32))
        params = {
            'code': 'true',
            'client_id': CLIENT_ID,
            'response_type': 'code',
            'redirect_uri': REDIRECT_URI,
            'scope': SCOPES,
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
            'state': state,
        }
        return '{}?{}'.format(AUTH_URL, _urlencode(params)), verifier, state

    def exchange_code(self, code, verifier, state):
        raw = code.strip()
        if '#' in raw:
            code_part, state_part = raw.split('#', 1)
        else:
            code_part, state_part = raw, state

        data = {
            'grant_type': 'authorization_code',
            'code': code_part.strip(),
            'redirect_uri': REDIRECT_URI,
            'client_id': CLIENT_ID,
            'code_verifier': verifier,
            'state': state_part.strip(),
        }
        resp = requests.post(
            TOKEN_URL, data=_urlencode(data),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
        try:
            if resp.status_code != 200:
                raise OSError('exchange fallito {}: {}'.format(resp.status_code, resp.text[:200]))
            j = resp.json()
        finally:
            resp.close()

        access = j.get('access_token')
        if not access:
            raise OSError('risposta senza access_token')
        self._write_credentials(access, j.get('refresh_token'), int(j.get('expires_in', 28800)))
        return True

    def _write_credentials(self, access, refresh, expires_in):
        self._data['access_token'] = access
        if refresh:
            self._data['refresh_token'] = refresh
        self._data['expires_at'] = time.time() + expires_in
        State.save(STATE_NAME, self._data)

    def refresh_token(self):
        rt = self._data.get('refresh_token')
        if not rt:
            return False
        now = time.time()
        if now < self._refresh_retry_after:
            return False

        resp = requests.post(
            TOKEN_URL,
            data=_urlencode({'grant_type': 'refresh_token', 'refresh_token': rt, 'client_id': CLIENT_ID}),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
        try:
            if resp.status_code == 429:
                self._refresh_retry_after = time.time() + BACKOFF_429 * 4
                return False
            if resp.status_code != 200:
                return False
            j = resp.json()
        finally:
            resp.close()

        access = j.get('access_token')
        if not access:
            return False
        self._write_credentials(access, j.get('refresh_token', rt), int(j.get('expires_in', 3600)))
        return True

    def poll_usage(self):
        now = time.time()
        if now < self._retry_after:
            return None
        if now - self._last_call < MIN_INTERVAL:
            return None

        token = self._data.get('access_token')
        if not token:
            return None

        out = self._get_usage(token)
        if out == '401':
            if self.refresh_token():
                token = self._data.get('access_token')
                out = self._get_usage(token)
            elif not self._data.get('refresh_token'):
                # No refresh token to fall back on at all: this really is
                # terminal, the user must log in again.
                return {'_error': 'oauth_expired'}
            else:
                # refresh_token() failed for a transient reason (backoff,
                # 429, a non-200 from the token endpoint, a malformed
                # response) while a refresh token is still on file. Treating
                # this as expired would make enter_login_mode() wipe a
                # still-valid refresh token over what might be a one-off
                # blip. Skip this cycle instead; the next scheduled poll
                # tries again.
                return None
        if out == '401':
            return {'_error': 'oauth_expired'}
        return out

    def _get_usage(self, token):
        resp = requests.get(
            USAGE_URL,
            headers={'Authorization': 'Bearer ' + token, 'anthropic-beta': BETA_HEADER},
        )
        try:
            status = resp.status_code
            if status == 401:
                return '401'
            if status == 429:
                self._retry_after = time.time() + BACKOFF_429
                return None
            if status != 200:
                return None
            data = resp.json()
        finally:
            resp.close()

        self._last_call = time.time()
        return _map_usage(data)
