# sim_network.py - modulo `network` finto per provare wifi_config nel simulatore
# try.badgewa.re (che non ha una rete vera). Il runner lo mette in
# sys.modules["network"] e programma:
#   CONNETTIBILI = {ssid: password}  reti che accettano quella password ("" = aperta)
#   SCAN = [(ssid, rssi, sicurezza), ...]   reti visibili (sicurezza 0 = aperta)
# Una rete non visibile risponde -2 dopo 800 ms, una password sbagliata -3 dopo
# 1200 ms, una connessione buona riesce dopo 1500 ms.

STA_IF = 0
CONNETTIBILI = {}
SCAN = []


class _WLAN:
    def __init__(self):
        self._ssid = None
        self._pw = None
        self._inizio = None
        self._connesso = False

    def active(self, v=None):
        return True

    def connect(self, ssid, password=""):
        self._ssid, self._pw = ssid, password
        self._inizio = badge.ticks
        self._connesso = False

    def disconnect(self):
        self._ssid = None
        self._connesso = False

    def _calcola(self):
        if self._ssid is None:
            return 0
        t = badge.ticks - self._inizio
        visibile = any(s == self._ssid for s, _, _ in SCAN)
        if not visibile:
            return -2 if t > 800 else 1
        if self._ssid in CONNETTIBILI and CONNETTIBILI[self._ssid] == (self._pw or ""):
            if t > 1500:
                self._connesso = True
                return 3
            return 1
        return -3 if t > 1200 else 1

    def status(self, param=None):
        if param == "rssi":
            for s, r, _ in SCAN:
                if s == self._ssid:
                    return r
            return -90
        return self._calcola()

    def isconnected(self):
        self._calcola()
        return self._connesso

    def ifconfig(self):
        return ("192.168.1.57", "255.255.255.0", "192.168.1.1", "8.8.8.8")

    def scan(self):
        return [(s.encode(), b"\x00" * 6, 1, r, sic, False) for s, r, sic in SCAN]


_wlan = _WLAN()


def WLAN(_iface):
    return _wlan
