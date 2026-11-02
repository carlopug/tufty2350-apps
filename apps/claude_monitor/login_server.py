"""Minimal non-blocking HTTP server for the one-time OAuth setup page.

Runs on the badge's existing home-WiFi connection (STA mode) — the user
opens the shown IP:port from a browser on the same network, clicks
through to Claude's authorize page, and pastes the resulting code back
into the form served here. There is no authentication on the form: this
server only exists transiently during setup, on a private home LAN.
"""
import socket

MAX_REQUEST_BYTES = 4096
MAX_CODE_LENGTH = 2048

HTML_PAGE = """<!doctype html>
<html>
<head><meta charset="utf-8"><title>Tufty 2350 - Claude Monitor</title></head>
<body style="font-family: sans-serif; max-width: 480px; margin: 40px auto;">
<h1>Claude Monitor - accesso</h1>
<ol>
<li><a href="{auth_url}" target="_blank" rel="noopener">Apri questo link e autorizza l'accesso a Claude</a></li>
<li>Copia il codice mostrato dopo l'autorizzazione e incollalo qui sotto</li>
</ol>
<form method="POST" action="/">
<input type="text" name="code" style="width: 100%; padding: 8px;" placeholder="Codice di autorizzazione" autofocus>
<button type="submit" style="margin-top: 8px; padding: 8px 16px;">Conferma</button>
</form>
{message}
</body>
</html>
"""


def _urldecode(value):
    value = value.replace("+", " ")
    out = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "%" and i + 2 < len(value):
            try:
                out.append(chr(int(value[i + 1:i + 3], 16)))
                i += 3
                continue
            except ValueError:
                pass
        out.append(ch)
        i += 1
    return "".join(out)


class LoginServer:

    def __init__(self, port=8080):
        self._port = port
        self._sock = None
        self._auth_url = ""
        self._verifier = ""
        self._state = ""
        self._message = ""
        self.on_code = None

    def start(self, auth_url, verifier, state):
        self._auth_url = auth_url
        self._verifier = verifier
        self._state = state
        self._message = ""

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("0.0.0.0", self._port))
        self._sock.listen(1)
        self._sock.setblocking(False)

    def stop(self):
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def poll(self):
        if self._sock is None:
            return

        try:
            conn, _addr = self._sock.accept()
        except OSError:
            return

        try:
            self._handle_connection(conn)
        finally:
            conn.close()

    def _handle_connection(self, conn):
        conn.settimeout(2)
        request = b""
        try:
            while b"\r\n\r\n" not in request and len(request) < MAX_REQUEST_BYTES:
                chunk = conn.recv(512)
                if not chunk:
                    break
                request += chunk
        except OSError:
            pass

        if request.startswith(b"POST"):
            body = self._read_body(conn, request)
            code = self._extract_code(body)
            if code and self.on_code is not None:
                try:
                    _ok, message = self.on_code(code, self._verifier, self._state)
                except Exception as error:
                    # on_code (Task 4's client.exchange_code) can raise more
                    # than OSError (e.g. a malformed JSON response); this
                    # server must never let that crash the app's frame loop,
                    # per the spec's "nessun crash dell'app se il body del
                    # POST è vuoto o il codice non è valido" requirement.
                    message = "Errore durante il login: {}".format(error)
            elif code:
                message = "Nessun gestore di login configurato"
            else:
                message = "Codice mancante o non valido"
            self._message = message
            self._respond_html(conn, self._render_page(message))
        else:
            self._respond_html(conn, self._render_page(self._message))

    def _read_body(self, conn, head):
        header_end = head.find(b"\r\n\r\n")
        body = head[header_end + 4:] if header_end >= 0 else b""
        content_length = self._content_length(head)
        try:
            while len(body) < content_length and len(body) < MAX_REQUEST_BYTES:
                chunk = conn.recv(512)
                if not chunk:
                    break
                body += chunk
        except OSError:
            pass
        return body

    def _content_length(self, head):
        for line in head.split(b"\r\n"):
            if line.lower().startswith(b"content-length:"):
                try:
                    return int(line.split(b":", 1)[1].strip())
                except ValueError:
                    return 0
        return 0

    def _extract_code(self, body):
        text = body.decode("utf-8", "ignore")
        for pair in text.split("&"):
            if "=" in pair:
                key, _, value = pair.partition("=")
                if key == "code":
                    return _urldecode(value).strip()[:MAX_CODE_LENGTH]
        return ""

    def _render_page(self, message):
        auth_url_html = self._auth_url.replace("&", "&amp;")
        message_html = "<p><strong>{}</strong></p>".format(message) if message else ""
        return HTML_PAGE.format(auth_url=auth_url_html, message=message_html)

    def _respond_html(self, conn, html):
        body = html.encode("utf-8")
        header = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            "Content-Length: {}\r\n"
            "Connection: close\r\n\r\n"
        ).format(len(body))
        try:
            conn.sendall(header.encode("utf-8") + body)
        except OSError:
            pass
