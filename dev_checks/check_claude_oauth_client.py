"""Desktop-only check for ClaudeClient's State-backed credential storage.

Stubs the two things claude_oauth.py expects from the Badgeware runtime
that don't exist on a desktop: the `ubinascii` module (aliased to the
stdlib `binascii`, same API) and the ambient `State` global (a fake
in-memory implementation here). `requests` is stubbed too, and made to
raise if actually called — this check never hits the network, it only
exercises has_credentials()/_write_credentials()/State round-tripping.
"""
import binascii
import builtins
import os
import sys
import types

sys.modules.setdefault("ubinascii", binascii)

fake_requests = types.ModuleType("requests")


def _network_forbidden(*_args, **_kwargs):
    raise AssertionError("this check must not touch the network")


fake_requests.get = _network_forbidden
fake_requests.post = _network_forbidden
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
import claude_oauth  # noqa: E402  (must come after the stubs above)

client = claude_oauth.ClaudeClient()
assert client.has_credentials() is False

client._write_credentials("access-123", "refresh-456", 3600)
assert client.has_credentials() is True
assert builtins.State.saved["claude_monitor"]["access_token"] == "access-123"
assert builtins.State.saved["claude_monitor"]["refresh_token"] == "refresh-456"

# A second client instance must pick up what the first one saved.
client2 = claude_oauth.ClaudeClient()
assert client2.has_credentials() is True
assert client2._data["access_token"] == "access-123"

# clear_credentials() must reset AND persist — a third instance must not
# pick the old token back up. This is what enter_login_mode() (Task 4)
# relies on to avoid immediately bouncing back to the dashboard.
client2._retry_after = 9999999999
client2._refresh_retry_after = 9999999999
client2.clear_credentials()
assert client2.has_credentials() is False
assert "access_token" not in builtins.State.saved["claude_monitor"]
# Backoff bookkeeping must reset too, so a freshly logged-in account
# never inherits a previous account's rate-limit backoff.
assert client2._retry_after == 0
assert client2._refresh_retry_after == 0

client3 = claude_oauth.ClaudeClient()
assert client3.has_credentials() is False

print("OK")
