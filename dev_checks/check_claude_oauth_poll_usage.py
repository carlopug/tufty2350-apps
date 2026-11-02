"""Desktop-only check for ClaudeClient.poll_usage()'s branching between a
terminal failure (no refresh token left at all -> oauth_expired) and a
transient one (429/500/malformed refresh response with a refresh token
still on file -> skip this cycle, do NOT wipe credentials).
"""
import binascii
import builtins
import os
import sys

sys.modules.setdefault("ubinascii", binascii)


class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data

    def close(self):
        pass


class FakeRequests:
    def __init__(self):
        self.get_queue = []
        self.post_queue = []

    def get(self, *_args, **_kwargs):
        return self.get_queue.pop(0)

    def post(self, *_args, **_kwargs):
        return self.post_queue.pop(0)


fake_requests = FakeRequests()
sys.modules.setdefault("requests", fake_requests)


class FakeState:
    def __init__(self):
        self.saved = {}

    def load(self, name, data):
        data.update(self.saved.get(name, {}))
        return name in self.saved

    def save(self, name, data):
        self.saved[name] = dict(data)


builtins.State = FakeState()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "claude_monitor"))
import claude_oauth  # noqa: E402


def make_client(access_token="access-1", refresh_token="refresh-1"):
    client = claude_oauth.ClaudeClient()
    # FakeState is shared across every case in this script (it's the one
    # ambient `State` global), so without resetting first, a refresh_token
    # persisted by an earlier case would leak into a later case that asks
    # for refresh_token=None -- _write_credentials only ever ADDS a
    # refresh_token, it never clears one that's merely not passed this
    # time. clear_credentials() gives every case a genuinely blank slate.
    client.clear_credentials()
    client._write_credentials(access_token, refresh_token, 3600)
    fake_requests.get_queue.clear()
    fake_requests.post_queue.clear()
    return client


# Case 1: usage call succeeds outright.
client = make_client()
fake_requests.get_queue.append(FakeResponse(200, {"five_hour": {"utilization": 0.5}}))
result = client.poll_usage()
assert result["session_pct_used"] == 50

# Case 2: 401, refresh succeeds, retried usage call succeeds.
client = make_client()
fake_requests.get_queue.append(FakeResponse(401))
fake_requests.post_queue.append(FakeResponse(
    200, {"access_token": "access-2", "refresh_token": "refresh-2", "expires_in": 3600}
))
fake_requests.get_queue.append(FakeResponse(200, {"five_hour": {"utilization": 0.25}}))
result = client.poll_usage()
assert result["session_pct_used"] == 25
assert client._data["access_token"] == "access-2"

# Case 3: 401, refresh transiently fails (429) -- must NOT wipe credentials.
client = make_client()
fake_requests.get_queue.append(FakeResponse(401))
fake_requests.post_queue.append(FakeResponse(429))
result = client.poll_usage()
assert result is None
assert client.has_credentials() is True
assert client._data.get("refresh_token") == "refresh-1"

# Case 4: 401, refresh transiently fails (500) -- must NOT wipe credentials.
client = make_client()
fake_requests.get_queue.append(FakeResponse(401))
fake_requests.post_queue.append(FakeResponse(500))
result = client.poll_usage()
assert result is None
assert client.has_credentials() is True

# Case 5: 401, and there is no refresh token at all -- this IS terminal.
client = make_client(refresh_token=None)
fake_requests.get_queue.append(FakeResponse(401))
result = client.poll_usage()
assert result == {"_error": "oauth_expired"}

print("OK")
