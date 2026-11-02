"""Prova apps/wifi_config (e la schermata "senza WiFi" di claude_monitor) nel
simulatore https://try.badgewa.re/ con Playwright, rete finta (sim_network.py).

    PYTHONIOENCODING=utf-8 python prova_wifi_config.py CARTELLA_FOTO [scenario ...]

Senza scenari li prova tutti. Lanciare senza "python -I" (Playwright e' nel
site-packages utente). Metodo: skill badgeware-framework, "Test automatici nel
simulatore".
"""
import base64
import importlib.util
import os
import sys
from collections import deque

from playwright.sync_api import sync_playwright

QUI = os.path.dirname(os.path.abspath(__file__))
APP = os.path.normpath(os.path.join(QUI, "..", "..", "apps", "wifi_config"))
FILE_APP = ["__init__.py", "reti.py", "rete.py", "tastiera.py", "ui.py"]
HOOK = open(os.path.join(QUI, "hook.js"), encoding="utf-8").read()

_spec = importlib.util.spec_from_file_location("tastiera_pc", os.path.join(APP, "tastiera.py"))
tastiera = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tastiera)

SCAN = [("CasaRossi", -50, 3), ("FASTWEB-7A21", -62, 3), ("Rete-Ospiti-Molto-Lunga-Piano-3", -63, 3), ("Scuola-Ospiti", -65, 0),
        ("iPhone di Alex", -72, 3), ("TIM-48712933", -75, 3), ("Vodafone-Free", -85, 0),
        ("DIRECT-HP-Printer", -88, 3), ("Ufficio-5G", -89, 3), ("Ospiti-Bar", -91, 0)]


def multi(*coppie):
    return "NETWORKS = [\n" + "".join("    {!r},\n".format({"ssid": s, "password": p}) for s, p in coppie) + "]\n"


RUNNER = '''
import os, sys
D = "/wifi_config"
for d in (D, "/wc_root", "/sys_finto"):
    try:
        os.mkdir(d)
    except OSError:
        pass
for f in %(file)r:
    if f in os.listdir("/"):
        try:
            os.remove(D + "/" + f)
        except OSError:
            pass
        os.rename("/" + f, D + "/" + f)
for d in ("/wc_root", "/sys_finto"):
    for f in os.listdir(d):
        os.remove(d + "/" + f)
for path, testo in %(file_dati)r:
    with open(path, "w") as f:
        f.write(testo)
os.chdir(D)
if D not in sys.path:
    sys.path.insert(0, D)
for m in ("reti", "rete", "tastiera", "ui", "network", "sim_network"):
    sys.modules.pop(m, None)
import sim_network
sim_network.CONNETTIBILI = %(connettibili)r
sim_network.SCAN = %(scan)r
sys.modules["network"] = sim_network
import reti
reti.ROOT = "/wc_root/"
reti.SYSTEM = "/sys_finto/"
G = dict(globals())
G["__name__"] = "wifi_config"
with open("__init__.py") as f:
    exec(f.read(), G)
'''

A, B, C, SU, GIU = "ArrowLeft", "Space", "ArrowRight", "ArrowUp", "ArrowDown"
_TASTO = {(0, -1): A, (0, 1): C, (-1, 0): SU, (1, 0): GIU}


def percorso_tastiera(da, a):
    """Sequenza di tasti piu' corta (BFS sulle mosse vere di tastiera.py)."""
    if da == a:
        return []
    visti = {da: None}
    coda = deque([da])
    while coda:
        pos = coda.popleft()
        for mossa, tasto in _TASTO.items():
            t = tastiera.Tastiera()
            t.riga, t.col = pos
            t.muovi(*mossa)
            nuovo = (t.riga, t.col)
            if nuovo not in visti:
                visti[nuovo] = (pos, tasto)
                if nuovo == a:
                    tasti = []
                    while visti[nuovo]:
                        nuovo, k = visti[nuovo]
                        tasti.append(k)
                    return tasti[::-1]
                coda.append(nuovo)
    raise ValueError(a)


def posizione(car):
    if car in tastiera.SPECIALI:
        return (tastiera.RIGA_SPECIALE, tastiera.SPECIALI.index(car))
    if car == " ":
        return (tastiera.RIGA_SPECIALE, 0)
    for r, riga in enumerate(tastiera.RIGHE):
        if car in riga:
            return (r, riga.index(car))
    return (tastiera.RIGA_SPECIALE, tastiera.SPECIALI.index(car))


class Sim:
    def __init__(self, pg, out):
        self.pg = pg
        self.out = out
        self.n = 0
        self.cursore = (0, 0)

    def avvia(self, file_dati=(), connettibili=None, scan=SCAN, attesa=300):
        codice = RUNNER % {"file": FILE_APP + ["sim_network.py"], "file_dati": list(file_dati),
                           "connettibili": connettibili or {}, "scan": scan}
        self.pg.evaluate("c => { const e = monaco.editor.getEditors()[0]; e.setValue(c); e.focus(); }", codice)
        self.pg.keyboard.press("F5")
        self.pg.wait_for_timeout(attesa + 1200)
        self.fuoco()
        self.cursore = (0, 0)

    def fuoco(self):
        self.pg.mouse.click(self.badge_x, self.badge_y)
        self.pg.wait_for_timeout(150)

    def tasto(self, k, volte=1, pausa=200):
        for _ in range(volte):
            self.pg.keyboard.down(k)
            self.pg.wait_for_timeout(80)
            self.pg.keyboard.up(k)
            self.pg.wait_for_timeout(pausa)

    def attendi(self, ms):
        self.pg.wait_for_timeout(ms)

    def scrivi(self, testo, partenza=(0, 0)):
        self.cursore = partenza
        for car in testo:
            self.vai_a(posizione(car))
            self.tasto(B, pausa=120)

    def vai_a(self, pos):
        for k in percorso_tastiera(self.cursore, pos):
            self.tasto(k, pausa=90)
        self.cursore = pos

    def foto(self, nome, attesa=250):
        self.pg.wait_for_timeout(attesa)
        self.n += 1
        percorso = os.path.join(self.out, "%02d_%s.png" % (self.n, nome))
        url = self.pg.evaluate("() => window.__fbPng(2)")
        with open(percorso, "wb") as f:
            f.write(base64.b64decode(url.split(",")[1]))
        print("  ", os.path.basename(percorso))

    def uscita(self):
        txt = self.pg.locator("body").inner_text()
        i = txt.rfind("OUTPUT")
        return txt[i:] if i >= 0 else ""


NOTE_TRE = multi(("Scuola-Lab", "lab12345"), ("CasaRossi", "casa1234"), ("iPhone di Alex", "hot12345"))
OK_CASA = {"CasaRossi": "casa1234", "iPhone di Alex": "hot12345"}
SOLO_LAB = [("/wc_root/multi_secrets.py", multi(("Scuola-Lab", "lab12345")))]


def scenario_avvio_ok(s):
    s.avvia([("/wc_root/multi_secrets.py", NOTE_TRE)], OK_CASA, attesa=0)
    s.foto("prova_reti_note", 100)
    s.attendi(2600)
    s.foto("menu_connesso")
    s.tasto(B)
    s.foto("cambia_rete_lista", 600)
    s.tasto(GIU)
    s.tasto(GIU)
    s.foto("cambia_rete_iphone")
    s.tasto(B)
    s.foto("cambia_in_corso", 200)
    s.attendi(1800)
    s.foto("menu_connesso_iphone")
    s.tasto(GIU, 2)
    s.tasto(B)
    s.attendi(600)
    s.tasto(GIU, 2)
    s.foto("elimina_lista")
    s.tasto(B)
    s.foto("elimina_conferma")
    s.tasto(C)
    s.tasto(B)
    s.foto("eliminata_messaggio")
    s.tasto(B)
    s.tasto(GIU, 3)
    s.tasto(B)
    s.foto("reimporta_conferma")
    s.tasto(C)
    s.tasto(B)
    s.foto("reimporta_nessun_file")


def scenario_password(s):
    s.avvia(SOLO_LAB, {"FASTWEB-7A21": "giusta123"})
    s.attendi(800)
    s.foto("nessuna_rete")
    s.tasto(B)
    s.foto("elenco_reti", 400)
    s.tasto(GIU, 2)
    s.foto("elenco_ssid_lungo")
    s.tasto(B)
    s.foto("tastiera_ssid_lungo")
    s.vai_a(posizione("Annulla"))
    s.tasto(B)
    s.tasto(SU)
    s.foto("elenco_fastweb")
    s.tasto(B)
    s.foto("tastiera_vuota")
    s.scrivi("giusta12")
    s.foto("tastiera_scritta")
    s.vai_a(posizione("OK"))
    s.foto("tastiera_su_OK")
    s.tasto(B)
    s.foto("prova_password", 150)
    s.attendi(1500)
    s.foto("password_errata")
    s.scrivi("3", s.cursore)
    s.vai_a(posizione("OK"))
    s.tasto(B)
    s.attendi(2000)
    s.foto("connesso_nuova_rete")


def scenario_corta_annulla(s):
    s.avvia(SOLO_LAB, {})
    s.attendi(800)
    s.tasto(B)
    s.attendi(400)
    s.tasto(GIU)
    s.tasto(B)
    s.scrivi("abc")
    s.vai_a(posizione("OK"))
    s.tasto(B)
    s.foto("password_corta")
    s.vai_a(posizione("Canc"))
    s.tasto(B)
    s.foto("dopo_canc")
    s.vai_a(posizione("Annulla"))
    s.tasto(B)
    s.foto("annulla_torna_elenco")
    s.tasto(GIU, 7)
    s.foto("elenco_scorrimento")
    s.tasto(A)
    s.foto("indietro_nessuna_rete")


def scenario_aperta(s):
    s.avvia(SOLO_LAB, {"Scuola-Ospiti": ""})
    s.attendi(800)
    s.tasto(B)
    s.attendi(400)
    s.tasto(GIU, 3)
    s.foto("elenco_aperta")
    s.tasto(B)
    s.foto("collegamento_aperta", 150)
    s.attendi(1800)
    s.foto("connesso_aperta")


def scenario_nota_salvata(s):
    s.avvia([("/wc_root/multi_secrets.py", multi(("CasaRossi", "vecchia99")))], {"CasaRossi": "casa1234"})
    s.attendi(1200)
    s.tasto(B)
    s.attendi(400)
    s.tasto(B)
    s.foto("tastiera_password_salvata")


def scenario_gestisci_no(s):
    s.avvia(SOLO_LAB, {})
    s.attendi(800)
    s.tasto(GIU)
    s.tasto(B)
    s.foto("menu_non_connesso")
    s.tasto(B)
    s.foto("collega_rete_nota", 600)
    s.avvia(SOLO_LAB, {})
    s.attendi(800)
    s.tasto(GIU, 2)
    s.tasto(B)
    s.foto("non_connesso")


def scenario_avviso(s):
    s.avvia([("/sys_finto/multi_secrets.py", NOTE_TRE),
             ("/sys_finto/secrets.py", "WIFI_SSID = 'Telefono'\nWIFI_PASSWORD = 'tel12345'\nREGION = 'IT'\n")],
            OK_CASA)
    s.foto("avviso_importazione")
    s.tasto(B)
    s.attendi(3000)
    s.foto("dopo_avviso_connesso")


def scenario_danneggiato(s):
    s.avvia([("/wc_root/multi_secrets.py", "NETWORKS = [\n {'ssid'")], {})
    s.foto("elenco_danneggiato")
    s.tasto(B)
    s.foto("menu_dopo_danneggiato")


def scenario_vuoto(s):
    s.avvia([], {})
    s.foto("nessuna_rete_salvata")


# claude_monitor senza WiFi: app vera con wifi/secrets finti e stub per OAuth/server
RUNNER_MONITOR = '''
import os, sys
D = "/claude_monitor"
try:
    os.mkdir(D)
except OSError:
    pass
for src, dst in (("cm_init.py", "__init__.py"), ("collegamento.py", "collegamento.py")):
    if src in os.listdir("/"):
        try:
            os.remove(D + "/" + dst)
        except OSError:
            pass
        os.rename("/" + src, D + "/" + dst)
os.chdir(D)
if D not in sys.path:
    sys.path.insert(0, D)
class _M:
    pass
class _Wlan:
    def status(self):
        return %(status)d
w = _M()
w.wlan = None
def _c():
    w.wlan = _Wlan()
    return False
w.connect = _c
w.disconnect = lambda: setattr(w, "wlan", None)
w.is_connected = lambda: False
w.ip = lambda: None
sec = _M()
sec.WIFI_SSID = %(ssid)r
class _Client:
    def has_credentials(self):
        return True
class _Server:
    def __init__(self, port):
        pass
    def stop(self):
        pass
oa = _M(); oa.ClaudeClient = _Client
ls = _M(); ls.LoginServer = _Server
lt = _M()
lt.rome_utc_offset_seconds = lambda ts: 3600
lt.format_local = lambda ts, off: "12:00"
lt.shift_and_format = lambda iso, off: "12:00"
for nome, mod in (("wifi", w), ("secrets", sec), ("claude_oauth", oa), ("login_server", ls), ("localtime", lt)):
    sys.modules[nome] = mod
sys.modules.pop("collegamento", None)
G = dict(globals())
G["__name__"] = "claude_monitor"
with open("__init__.py") as f:
    # la cartella /system/apps/claude_monitor esiste solo sul badge vero
    exec(f.read().replace('os.chdir("/system/apps/claude_monitor")', 'pass'), G)
'''


def scenario_monitor(s):
    for nome, codice in (("ssid_vuoto", RUNNER_MONITOR % {"status": 1, "ssid": ""}),
                         ("password_errata", RUNNER_MONITOR % {"status": -3, "ssid": "CasaRossi"})):
        s.pg.evaluate("c => { const e = monaco.editor.getEditors()[0]; e.setValue(c); e.focus(); }", codice)
        s.pg.keyboard.press("F5")
        s.attendi(2000)
        s.foto("claude_monitor_" + nome)


SCENARI = {"avvio_ok": scenario_avvio_ok, "password": scenario_password,
           "corta_annulla": scenario_corta_annulla, "aperta": scenario_aperta,
           "nota_salvata": scenario_nota_salvata, "gestisci_no": scenario_gestisci_no,
           "avviso": scenario_avviso, "danneggiato": scenario_danneggiato, "vuoto": scenario_vuoto,
           "monitor": scenario_monitor}


def main():
    out = sys.argv[1]
    scelti = sys.argv[2:] or list(SCENARI)
    os.makedirs(out, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--enable-gpu", "--use-angle=d3d11", "--ignore-gpu-blocklist"])
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        pg.add_init_script(HOOK)
        pg.goto("https://try.badgewa.re/", wait_until="networkidle", timeout=60000)
        pg.wait_for_timeout(3000)
        monitor = os.path.normpath(os.path.join(APP, "..", "claude_monitor"))
        extra = [{"name": "cm_init.py", "mimeType": "text/x-python",
                  "buffer": open(os.path.join(monitor, "__init__.py"), "rb").read()},
                 {"name": "collegamento.py", "mimeType": "text/x-python",
                  "buffer": open(os.path.join(monitor, "collegamento.py"), "rb").read()}]
        pg.set_input_files("#fp-upload-input",
                           [os.path.join(APP, f) for f in FILE_APP] + [os.path.join(QUI, "sim_network.py")])
        pg.wait_for_timeout(1500)
        pg.set_input_files("#fp-upload-input", extra)
        pg.wait_for_timeout(2000)
        s = Sim(pg, out)
        box = pg.locator("canvas").last.bounding_box()
        s.badge_x = box["x"] + box["width"] / 2
        s.badge_y = box["y"] + box["height"] / 2
        s.avvia([], {})  # il primo avvio dopo l'upload non trova ancora i moduli spostati
        for nome in scelti:
            print("scenario", nome)
            SCENARI[nome](s)
            errori = [r for r in s.uscita().splitlines() if "Error" in r or "Traceback" in r]
            if errori:
                print("   ERRORI NELL'OUTPUT:", errori)
        print(s.uscita()[-2000:])
        b.close()


main()
