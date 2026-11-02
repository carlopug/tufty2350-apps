"""Controllo desktop della logica di apps/wifi_config (e di apps/claude_monitor/collegamento.py).

    python dev_checks/check_wifi_config.py   (dalla radice del repo)

Stampa OK se tutto passa. Nessun hardware: i volumi "/" e "/system" del badge
sono due cartelle temporanee (reti.ROOT / reti.SYSTEM puntati li'), la rete e'
un modulo `network` finto programmabile.
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import time

QUI = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(QUI, "..", "apps", "wifi_config")
MONITOR = os.path.join(QUI, "..", "apps", "claude_monitor")


def carica_modulo(nome, cartella):
    spec = importlib.util.spec_from_file_location(nome, os.path.join(cartella, nome + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


TESTS = []


def test(f):
    TESTS.append(f)
    return f


# ---------------------------------------------------------------- reti.py
reti = carica_modulo("reti", APP)
D_ROOT = tempfile.mkdtemp(prefix="wc_root_")
D_SYS = tempfile.mkdtemp(prefix="wc_sys_")
reti.ROOT = D_ROOT.replace("\\", "/") + "/"
reti.SYSTEM = D_SYS.replace("\\", "/") + "/"


def pulisci():
    for d in (D_ROOT, D_SYS):
        for n in os.listdir(d):
            os.remove(os.path.join(d, n))


def scrivi(cartella, nome, testo):
    with open(os.path.join(cartella, nome), "w", encoding="utf-8") as f:
        f.write(testo)


def leggi(cartella, nome):
    with open(os.path.join(cartella, nome), encoding="utf-8") as f:
        return f.read()


def ns_di(cartella, nome):
    ns = {}
    exec(leggi(cartella, nome), ns)
    return {k: v for k, v in ns.items() if not k.startswith("__")}


def esiste(cartella, nome):
    return os.path.exists(os.path.join(cartella, nome))


SYS_MULTI = "NETWORKS = [\n {'ssid': 'casa', 'password': 'pw-casa'},\n {'ssid': 'lavoro', 'password': 'pw-lav'},\n]\n"


@test
def importazione_iniziale_da_system():
    pulisci()
    scrivi(D_SYS, "multi_secrets.py", SYS_MULTI)
    scrivi(D_SYS, "secrets.py", "WIFI_SSID = 'telefono'\nWIFI_PASSWORD = 'pw-tel'\nREGION = 'IT'\n")
    r, stato, n = reti.carica()
    assert stato == "importato", stato
    assert n == 3, n
    assert [x["ssid"] for x in r] == ["casa", "lavoro", "telefono"], r
    assert ns_di(D_ROOT, "multi_secrets.py")["NETWORKS"] == r


@test
def importazione_rete_secrets_gia_presente_non_duplicata():
    pulisci()
    scrivi(D_SYS, "multi_secrets.py", SYS_MULTI)
    scrivi(D_SYS, "secrets.py", "WIFI_SSID = 'casa'\nWIFI_PASSWORD = 'pw-casa'\n")
    r, stato, n = reti.carica()
    assert n == 2 and [x["ssid"] for x in r] == ["casa", "lavoro"], r


@test
def niente_da_importare_vuoto():
    pulisci()
    r, stato, n = reti.carica()
    assert (r, stato, n) == ([], "vuoto", 0)
    assert not esiste(D_ROOT, "multi_secrets.py")


@test
def root_presente_ignora_system_e_forget():
    pulisci()
    scrivi(D_ROOT, "multi_secrets.py", "NETWORKS = [{'ssid': 'solo', 'password': 'p1234567'}]\n")
    scrivi(D_SYS, "multi_secrets.py", SYS_MULTI + "FORGET = ['solo']\n")
    scrivi(D_SYS, "secrets.py", "WIFI_SSID = 'altra'\nWIFI_PASSWORD = 'x'\n")
    r, stato, n = reti.carica()
    assert stato == "ok" and r == [{"ssid": "solo", "password": "p1234567"}], (r, stato)


@test
def in_cima_e_togli():
    r = [{"ssid": "a", "password": "1"}, {"ssid": "b", "password": "2"}]
    r2 = reti.in_cima(r, "b", "nuova")
    assert r2 == [{"ssid": "b", "password": "nuova"}, {"ssid": "a", "password": "1"}], r2
    assert r[1]["password"] == "2", "non deve modificare la lista originale"
    assert reti.in_cima(r, "c", "")[0] == {"ssid": "c", "password": ""}
    assert reti.togli(r, "a") == [{"ssid": "b", "password": "2"}]
    assert reti.togli(r, "zzz") == r


@test
def salva_crea_bak_della_versione_precedente():
    pulisci()
    reti.salva([{"ssid": "uno", "password": "p"}])
    assert not esiste(D_ROOT, "multi_secrets.py.bak")
    reti.salva([{"ssid": "due", "password": "q"}])
    assert ns_di(D_ROOT, "multi_secrets.py.bak")["NETWORKS"] == [{"ssid": "uno", "password": "p"}]
    assert ns_di(D_ROOT, "multi_secrets.py")["NETWORKS"] == [{"ssid": "due", "password": "q"}]
    assert not esiste(D_ROOT, "multi_secrets.py.tmp")


@test
def salva_non_riscrive_se_uguale():
    pulisci()
    reti.salva([{"ssid": "uno", "password": "p"}])
    p = os.path.join(D_ROOT, "multi_secrets.py")
    prima = os.stat(p).st_mtime_ns
    time.sleep(0.02)
    reti.salva([{"ssid": "uno", "password": "p"}])
    assert os.stat(p).st_mtime_ns == prima
    assert not esiste(D_ROOT, "multi_secrets.py.bak")


@test
def corrotto_usa_bak():
    pulisci()
    scrivi(D_ROOT, "multi_secrets.py", "NETWORKS = [\n {'ssid'")
    scrivi(D_ROOT, "multi_secrets.py.bak", "NETWORKS = [{'ssid': 'salvata', 'password': 'pppppppp'}]\n")
    r, stato, n = reti.carica()
    assert stato == "ok" and r[0]["ssid"] == "salvata", (r, stato)


@test
def corrotto_senza_bak_valido_non_sovrascrive():
    pulisci()
    rotto = "NETWORKS = [\n {'ssid'"
    scrivi(D_ROOT, "multi_secrets.py", rotto)
    scrivi(D_ROOT, "multi_secrets.py.bak", "rotto anche questo (")
    scrivi(D_SYS, "multi_secrets.py", SYS_MULTI)
    r, stato, n = reti.carica()
    assert (r, stato, n) == ([], "danneggiato", 0), (r, stato, n)
    assert leggi(D_ROOT, "multi_secrets.py") == rotto


@test
def ssid_strani_round_trip():
    pulisci()
    strano = {"ssid": "weird's \"q\" \\ è", "password": "pa'ss\\w\"ord"}
    reti.salva([strano])
    r, stato, n = reti.carica()
    assert r == [strano], r


@test
def allinea_secrets_unisce_chiavi_system_vince():
    pulisci()
    scrivi(D_ROOT, "secrets.py", "WIFI_SSID = 'vecchia'\nWIFI_PASSWORD = 'v'\nKEEP = 'x'\nREGION = 'GB'\n")
    scrivi(D_SYS, "secrets.py", "WIFI_SSID = 'manuale'\nWIFI_PASSWORD = 'm'\nREGION = 'IT'\nTIMEZONE = 1\n")
    reti.allinea_secrets("nuova", "pw-nuova")
    s = ns_di(D_ROOT, "secrets.py")
    assert s == {"WIFI_SSID": "nuova", "WIFI_PASSWORD": "pw-nuova", "KEEP": "x", "REGION": "IT", "TIMEZONE": 1}, s


@test
def allinea_secrets_non_riscrive_se_uguale():
    pulisci()
    scrivi(D_ROOT, "secrets.py", "WIFI_SSID = 'casa'\nWIFI_PASSWORD = 'p'\n")
    p = os.path.join(D_ROOT, "secrets.py")
    prima = os.stat(p).st_mtime_ns
    time.sleep(0.02)
    reti.allinea_secrets("casa", "p")
    assert os.stat(p).st_mtime_ns == prima


@test
def allinea_secrets_system_gia_giusto_nessuna_copia_root():
    pulisci()
    scrivi(D_SYS, "secrets.py", "WIFI_SSID = 'casa'\nWIFI_PASSWORD = 'p'\n")
    reti.allinea_secrets("casa", "p")
    assert not esiste(D_ROOT, "secrets.py")


@test
def svuota_secrets():
    pulisci()
    scrivi(D_SYS, "secrets.py", "WIFI_SSID = 'casa'\nWIFI_PASSWORD = 'p'\nREGION = 'IT'\n")
    reti.svuota_secrets()
    s = ns_di(D_ROOT, "secrets.py")
    assert s == {"WIFI_SSID": "", "WIFI_PASSWORD": "", "REGION": "IT"}, s
    assert reti.ssid_secrets() == ""


@test
def ssid_secrets_root_poi_system():
    pulisci()
    assert reti.ssid_secrets() is None
    scrivi(D_SYS, "secrets.py", "WIFI_SSID = 'sys'\n")
    assert reti.ssid_secrets() == "sys"
    scrivi(D_ROOT, "secrets.py", "WIFI_SSID = 'root'\n")
    assert reti.ssid_secrets() == "root"


@test
def avviso_file_system():
    pulisci()
    assert not reti.avviso_file_system()
    scrivi(D_SYS, "multi_secrets.py", SYS_MULTI)
    assert not reti.avviso_file_system(), "prima dell'importazione non serve"
    reti.carica()
    assert reti.avviso_file_system()
    os.remove(os.path.join(D_SYS, "multi_secrets.py"))
    assert not reti.avviso_file_system()


@test
def reimporta():
    pulisci()
    assert reti.reimporta() is None
    scrivi(D_ROOT, "multi_secrets.py", "NETWORKS = [{'ssid': 'badge', 'password': 'b'}]\n")
    scrivi(D_SYS, "multi_secrets.py", SYS_MULTI)
    r = reti.reimporta()
    assert [x["ssid"] for x in r] == ["casa", "lavoro"], r
    assert ns_di(D_ROOT, "multi_secrets.py")["NETWORKS"] == r


# ---------------------------------------------------------------- rete.py
class FakeWLAN:
    def __init__(self):
        self.connect_calls = []
        self.disconnect_calls = 0
        self.attiva = None
        self._status = 0
        self._connesso = False
        self.scan_result = []

    def active(self, v=None):
        if v is not None:
            self.attiva = v
        return self.attiva

    def connect(self, *args):
        self.connect_calls.append(args)
        self._status = 1
        self._connesso = False

    def disconnect(self):
        self.disconnect_calls += 1
        self._status = 0
        self._connesso = False

    def status(self):
        return self._status

    def isconnected(self):
        return self._connesso

    def imposta(self, status):
        self._status = status
        self._connesso = status == 3

    def ifconfig(self):
        return ("192.168.1.57", "255.255.255.0", "192.168.1.1", "8.8.8.8")

    def scan(self):
        return self.scan_result


class FakeNetwork:
    STA_IF = 0

    def __init__(self):
        self.wlan = FakeWLAN()
        self.creati = 0

    def WLAN(self, _iface):
        self.creati += 1
        return self.wlan


rete = carica_modulo("rete", APP)


def nuovo_collegamento():
    net = FakeNetwork()
    return net.wlan, rete.Collegamento(net)


@test
def collegamento_una_sola_connect_e_esito_ok():
    w, c = nuovo_collegamento()
    assert w.attiva is True
    c.avvia("casa", "pw-casa-1", 8000, 1000)
    assert w.connect_calls == [("casa", "pw-casa-1")], w.connect_calls
    assert c.ssid == "casa"
    assert c.esito(1100) is None
    assert c.esito(2000) is None
    assert len(w.connect_calls) == 1
    w.imposta(3)
    assert c.esito(2100) == "ok"
    assert c.connesso() and c.ip() == "192.168.1.57"


@test
def collegamento_esiti_di_errore():
    for status, atteso in ((-3, "password"), (-2, "non_trovata"), (-1, "fallita")):
        w, c = nuovo_collegamento()
        c.avvia("x", "12345678", 8000, 0)
        w.imposta(status)
        assert c.esito(10) == atteso, (status, c.esito(10))


@test
def collegamento_timeout():
    w, c = nuovo_collegamento()
    c.avvia("x", "12345678", 8000, 0)
    assert c.esito(7999) is None
    assert c.esito(8001) == "fallita"
    assert len(w.connect_calls) == 1


@test
def collegamento_rete_aperta_connect_senza_password():
    w, c = nuovo_collegamento()
    c.avvia("libera", "", 15000, 0)
    assert w.connect_calls == [("libera",)], w.connect_calls


@test
def collegamento_avvia_scollega_prima():
    w, c = nuovo_collegamento()
    c.avvia("a", "12345678", 8000, 0)
    c.avvia("b", "12345678", 8000, 0)
    assert w.disconnect_calls == 2 and len(w.connect_calls) == 2


@test
def livello_segnale_soglie():
    assert [rete.livello(r) for r in (-40, -55, -56, -67, -68, -78, -79, -90)] == [4, 4, 3, 3, 2, 2, 1, 1]


@test
def elabora_scansione():
    grezza = [
        (b"casa", b"m1", 1, -70, 3, False),
        (b"casa", b"m2", 6, -50, 3, False),
        (b"", b"m3", 1, -40, 3, True),
        (b"\xff\xfe", b"m4", 1, -45, 3, False),
        (b"libera", b"m5", 11, -60, 0, False),
        (b"vicino", b"m6", 1, -85, 4, False),
    ]
    r = rete.elabora_scansione(grezza, {"casa"})
    assert [x["ssid"] for x in r] == ["casa", "libera", "vicino"], r
    assert r[0] == {"ssid": "casa", "rssi": -50, "livello": 4, "aperta": False, "nota": True}, r[0]
    assert r[1]["aperta"] is True and r[1]["nota"] is False
    assert r[2]["livello"] == 1


# ---------------------------------------------------------------- tastiera.py
tastiera = carica_modulo("tastiera", APP)


@test
def tastiera_scrive_muovendosi():
    t = tastiera.Tastiera()
    assert (t.riga, t.col) == (0, 0)
    t.muovi(2, 0); t.premi()          # A
    t.muovi(-2, 1); t.premi()         # b
    t.muovi(4, 0); t.premi()          # 1
    t.muovi(1, -1); t.premi()         # !
    assert t.testo == "Ab1!", t.testo


@test
def tastiera_canc_e_limiti():
    t = tastiera.Tastiera()
    t.riga, t.col = 7, tastiera.SPECIALI.index("Canc")
    assert t.premi() is None and t.testo == ""
    t = tastiera.Tastiera("x" * 63)
    t.premi()
    assert len(t.testo) == 63
    t.riga, t.col = 7, tastiera.SPECIALI.index("Canc")
    t.premi()
    assert t.testo == "x" * 62
    t.riga, t.col = 7, 0
    t.premi()
    assert t.testo.endswith(" ") and len(t.testo) == 63


@test
def tastiera_ok_corta_e_annulla():
    t = tastiera.Tastiera("abc12")
    t.riga, t.col = 7, tastiera.SPECIALI.index("OK")
    assert t.premi() == "corta"
    t.testo = "abcd1234"
    assert t.premi() == "ok"
    t.riga, t.col = 7, tastiera.SPECIALI.index("Annulla")
    assert t.premi() == "annulla"
    assert t.testo == "abcd1234"


@test
def tastiera_movimento_circolare_e_riga_speciale():
    t = tastiera.Tastiera()
    t.muovi(0, -1)
    assert (t.riga, t.col) == (0, 12)
    t.riga, t.col = 6, 12
    t.muovi(1, 0)
    assert (t.riga, t.col) == (7, tastiera.SPECIALI.index("Annulla")), (t.riga, t.col)
    t.muovi(-1, 0)
    assert (t.riga, t.col) == (6, 11), (t.riga, t.col)
    t.riga, t.col = 7, 6
    t.muovi(0, 1)
    assert t.col == 0
    t.muovi(1, 0)
    assert t.riga == 0
    t.muovi(-1, 0)
    assert t.riga == 7
    t.riga, t.col = 0, 0
    t.muovi(-1, 0)
    assert (t.riga, t.col) == (7, 0), (t.riga, t.col)


@test
def tastiera_copre_ascii_stampabile():
    tutti = "".join(tastiera.RIGHE) + " \\|`"
    assert sorted(tutti) == [chr(c) for c in range(32, 127)], set(chr(c) for c in range(32, 127)) - set(tutti)


@test
def ripetitore():
    r = tastiera.Ripetitore(("A", "C", "UP", "DOWN"), 400, 100)
    assert r.tasti(["C"], ["C"], 0) == ["C"]
    assert r.tasti([], ["C"], 399) == []
    assert r.tasti([], ["C"], 400) == ["C"]
    assert r.tasti([], ["C"], 450) == []
    assert r.tasti([], ["C"], 500) == ["C"]
    assert r.tasti([], [], 520) == []
    assert r.tasti([], ["C"], 1000) == [], "rilasciato e ritenuto senza nuova pressione: niente"
    assert r.tasti(["B"], ["B"], 1100) == ["B"]
    assert r.tasti([], ["B"], 1600) == [], "B non si ripete"


# ---------------------------------------------------------------- claude_monitor/collegamento.py
class FakeWifiFirmware:
    """Imita il contratto di online/modules/common/wifi.py: connect() con wlan
    gia' esistente farebbe avanzare i retry verso fatal_error -> qui e' un errore."""

    def __init__(self):
        self.wlan = None
        self.connect_calls = 0
        self.disconnect_calls = 0

    def connect(self):
        if self.wlan is not None:
            raise AssertionError("connect() con wlan esistente: rischio fatal_error")
        self.connect_calls += 1
        self.wlan = FakeWLAN()
        self.wlan._status = 1
        return False

    def disconnect(self):
        self.disconnect_calls += 1
        self.wlan = None

    def is_connected(self):
        return self.wlan is not None and self.wlan.isconnected()


collegamento = carica_modulo("collegamento", MONITOR)


@test
def monitor_ssid_vuoto_fallisce_senza_connect():
    w = FakeWifiFirmware()
    c = collegamento.CollegamentoWifi(w, "")
    assert c.tick(0) == "fallito" and w.connect_calls == 0
    c = collegamento.CollegamentoWifi(w, None)
    assert c.tick(0) == "fallito" and w.connect_calls == 0


@test
def monitor_connessione_riuscita():
    w = FakeWifiFirmware()
    c = collegamento.CollegamentoWifi(w, "casa")
    assert c.tick(0) == "attesa"
    assert c.tick(100) == "attesa"
    w.wlan.imposta(3)
    assert c.tick(200) == "connesso"
    assert w.connect_calls == 1


@test
def monitor_timeout_e_errore():
    w = FakeWifiFirmware()
    c = collegamento.CollegamentoWifi(w, "casa", 20000)
    c.tick(0)
    assert c.tick(19999) == "attesa"
    assert c.tick(20001) == "fallito"
    assert c.tick(30000) == "fallito" and w.connect_calls == 1
    w = FakeWifiFirmware()
    c = collegamento.CollegamentoWifi(w, "casa")
    c.tick(0)
    w.wlan.imposta(-3)
    assert c.tick(10) == "fallito" and w.connect_calls == 1


@test
def monitor_caduta_una_riconnessione():
    w = FakeWifiFirmware()
    c = collegamento.CollegamentoWifi(w, "casa")
    c.tick(0)
    w.wlan.imposta(3)
    assert c.tick(10) == "connesso"
    w.wlan.imposta(0)                      # il WiFi cade
    assert c.tick(20) == "attesa"
    assert w.disconnect_calls == 1 and w.connect_calls == 2
    w.wlan.imposta(3)
    assert c.tick(30) == "connesso"
    w.wlan.imposta(0)                      # cade di nuovo: altra riconnessione
    assert c.tick(40) == "attesa" and w.connect_calls == 3
    w.wlan.imposta(-2)                     # questa fallisce
    assert c.tick(50) == "fallito"
    assert c.tick(60000) == "fallito" and w.connect_calls == 3


# ---------------------------------------------------------------- correzioni dopo la revisione finale
@test
def esito_fallito_ferma_il_tentativo_in_corso():
    for status in (-3, None):
        w, c = nuovo_collegamento()
        c.avvia("x", "12345678", 8000, 0)
        prima = w.disconnect_calls
        if status is None:
            assert c.esito(9000) == "fallita"      # timeout
        else:
            w.imposta(status)
            assert c.esito(10) == "password"
        assert w.disconnect_calls == prima + 1, "il chip deve smettere di provare (scan successiva)"


@test
def avvia_con_errore_del_chip_non_solleva():
    w, c = nuovo_collegamento()

    def esplode(*a):
        raise OSError(5)
    w.connect = esplode
    c.avvia("x", "12345678", 8000, 0)
    assert c.esito(1) == "fallita"
    w2, c2 = nuovo_collegamento()
    w2.disconnect = esplode
    c2.avvia("x", "12345678", 8000, 0)
    assert c2.esito(1) == "fallita"


@test
def password_none_e_ssid_non_stringa():
    pulisci()
    scrivi(D_ROOT, "multi_secrets.py",
           "NETWORKS = [{'ssid': 'aperta', 'password': None}, {'ssid': 42, 'password': 'x'}, {'ssid': 'ok'}]\n")
    r, stato, n = reti.carica()
    assert r == [{"ssid": "aperta", "password": ""}, {"ssid": "ok", "password": ""}], r


@test
def reimporta_da_file_corrotto_non_svuota():
    pulisci()
    scrivi(D_ROOT, "multi_secrets.py", "NETWORKS = [{'ssid': 'badge', 'password': 'b'}]\n")
    scrivi(D_SYS, "multi_secrets.py", "NETWORKS = [\n {'ssid'")
    assert reti.reimporta() is None
    assert ns_di(D_ROOT, "multi_secrets.py")["NETWORKS"] == [{"ssid": "badge", "password": "b"}]


@test
def ripetitore_ripetibili_per_schermata():
    r = tastiera.Ripetitore(("A", "C", "UP", "DOWN"), 400, 100)
    assert r.tasti(["C"], ["C"], 0, ("UP", "DOWN")) == ["C"], "la pressione vale sempre"
    assert r.tasti([], ["C"], 450, ("UP", "DOWN")) == [], "ma C tenuto non si ripete qui"
    assert r.tasti([], ["C"], 560) == ["C"], "senza limite si ripete"


# ---------------------------------------------------------------- esecuzione
def main():
    falliti = 0
    for t in TESTS:
        try:
            t()
        except Exception as e:
            falliti += 1
            print("FALLITO", t.__name__, "->", type(e).__name__, e)
    shutil.rmtree(D_ROOT, ignore_errors=True)
    shutil.rmtree(D_SYS, ignore_errors=True)
    if falliti:
        print("{} test falliti su {}".format(falliti, len(TESTS)))
        sys.exit(1)
    print("OK ({} test)".format(len(TESTS)))


main()
