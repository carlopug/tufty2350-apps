# collegamento.py - connessione WiFi di claude_monitor senza rischio di riavvio.
#
# La rete e' quella di secrets.py, che apps/wifi_config tiene allineato. Il
# wifi.py del firmware, se richiamato con wifi.wlan gia' esistente, fa avanzare
# retry interni che a fine corsa chiamano fatal_error() -> riavvio del badge.
# Qui: una sola wifi.connect() per tentativo (solo con wlan assente, cioe' dopo
# disconnect()), poi solo is_connected()/wlan.status(), con timeout nostro.
# Se il WiFi cade dopo essere stato connesso si tenta UNA riconnessione; se
# fallisce, "fallito" e l'app mostra "Usa Wifi Config per gestire le reti WiFi".

_ERRORI = (-1, -2, -3)


class CollegamentoWifi:
    def __init__(self, wifi_mod, ssid, timeout_ms=20000):
        self.wifi = wifi_mod
        self.ssid = ssid
        self.timeout_ms = timeout_ms
        self.stato = "inizio"
        self._scadenza = None

    def _tenta(self, ora):
        self.wifi.connect()
        self._scadenza = ora + self.timeout_ms
        self.stato = "attesa"

    def tick(self, ora):
        """"connesso", "attesa" o "fallito" (definitivo)."""
        if self.stato == "inizio":
            if not self.ssid:
                self.stato = "fallito"
            else:
                self._tenta(ora)
        elif self.stato == "attesa":
            if self.wifi.is_connected():
                self.stato = "connesso"
            else:
                wlan = self.wifi.wlan
                errore = wlan is not None and wlan.status() in _ERRORI
                if errore or ora > self._scadenza:
                    self.stato = "fallito"
        elif self.stato == "connesso":
            if not self.wifi.is_connected():
                self.wifi.disconnect()
                self._tenta(ora)
        return self.stato
