"""Desktop-only check for LoginServer's request-parsing helpers.

Only exercises pure parsing/rendering methods (no .start()/.poll(), so no
real socket is ever opened) — safe to run on a normal desktop.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "claude_monitor"))

import login_server

srv = login_server.LoginServer()

assert srv._extract_code(b"code=abc123") == "abc123"
assert srv._extract_code(b"other=1&code=abc%20def&more=2") == "abc def"
assert srv._extract_code(b"nothing=here") == ""

assert srv._content_length(b"POST / HTTP/1.1\r\nContent-Length: 42\r\nHost: x\r\n\r\n") == 42
assert srv._content_length(b"GET / HTTP/1.1\r\n\r\n") == 0

srv._auth_url = "https://example.com/authorize?a=1&b=2"
page = srv._render_page("")
assert "https://example.com/authorize?a=1&amp;b=2" in page
assert '<form method="POST" action="/">' in page

page_with_message = srv._render_page("Errore di test")
assert "Errore di test" in page_with_message

print("OK")
