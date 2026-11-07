"""Prova apps/presentator nel simulatore https://try.badgewa.re/ con Playwright.

    PYTHONIOENCODING=utf-8 python prova_simulatore.py CARTELLA_SCREENSHOT [scenario ...]

Senza scenari li prova tutti, in inglese (tastiera US, comandi.example.json)
e in italiano (tastiera IT, comandi.json personale se c'e'). Per ogni
schermata salva un PNG del badge, con la lingua nel nome del file.
Serve Playwright per Python con Chromium (gia' presente su questo PC);
lanciare senza "python -I", altrimenti il pacchetto utente non si trova.
Il Bluetooth e' simulato da sim_bluetooth.py (dongle finto).
"""

import base64
import os
import sys

from playwright.sync_api import sync_playwright

QUI = os.path.dirname(os.path.abspath(__file__))
APP = os.path.normpath(os.path.join(QUI, "..", "..", "..", "apps", "presentator"))
FILE_APP = ["__init__.py", "comandi.py", "protocollo.py", "lingua.py", "comandi.json", "chiave.txt",
            "lang/en.json", "lang/it.json"]
# lingua dell'interfaccia -> layout della tastiera e file dei comandi usati
LINGUE = {"en": ("us", "comandi.example.json"), "it": ("it", "comandi.json")}


def percorsi_app():
    """Percorsi da caricare nel simulatore. comandi.json e' personale (escluso
    da git): se manca si carica comandi.example.json con il nome comandi.json."""
    import shutil
    import tempfile
    percorsi = []
    for f in FILE_APP:
        p = os.path.join(APP, f)
        if f == "comandi.json" and not os.path.exists(p):
            tmp = os.path.join(tempfile.mkdtemp(), "comandi.json")
            shutil.copy(os.path.join(APP, "comandi.example.json"), tmp)
            p = tmp
        if f == "chiave.txt" and not os.path.exists(p):
            sys.exit("chiave.txt mancante: lancia prima presentator_dongle/tools/genera_chiave.py")
        percorsi.append(p)
    return percorsi

JSON_ROTTO = '{"gruppi": [\n  {"nome": "Siti",\n   "comandi": [\n     {"nome": "Google" "url": "https://www.google.it"}\n   ]}\n]}\n'
JSON_VOCI_ERRATE = ('{"gruppi": [{"nome": "Prove", "comandi": ['
                    '{"nome": "Valida", "tasti": "WIN+D"},'
                    '{"nome": "Tasto sconosciuto", "tasti": "CTRL+PIPPO"},'
                    '{"nome": "Carattere tilde", "testo": "a~b"},'
                    '{"nome": "Campo sbagliato", "link": "https://x.it"}]}]}\n')

# codice eseguito nell'editor del simulatore: sposta i file in /presentator,
# prepara lo scenario e avvia l'app con il bluetooth finto
RUNNER = '''
import os, sys
D = "/presentator"
try:
    os.mkdir(D)
except OSError:
    pass
try:
    os.mkdir(D + "/lang")
except OSError:
    pass
for f in ("__init__.py", "comandi.py", "protocollo.py", "lingua.py", "comandi.json", "chiave.txt",
          "sim_bluetooth.py", "en.json", "it.json"):
    if f in os.listdir("/"):
        dest = D + ("/lang/" if f in ("en.json", "it.json") else "/") + f
        try:
            os.remove(dest)
        except OSError:
            pass
        os.rename("/" + f, dest)
os.chdir(D)
State.save("presentator", {"lingua": %(lingua)r, "layout": %(layout)r})
if D not in sys.path:
    sys.path.insert(0, D)
if "comandi_ok.json" not in os.listdir():
    with open("comandi.json") as a, open("comandi_ok.json", "w") as b:
        b.write(a.read())
JSON = %(json)r
with open("comandi_ok.json") as a:
    ok = a.read()
with open("comandi.json", "w") as b:
    b.write(JSON if JSON else ok)
if %(senza_chiave)r:
    if "chiave.txt" in os.listdir():
        os.rename("chiave.txt", "chiave.bak")
elif "chiave.bak" in os.listdir():
    os.rename("chiave.bak", "chiave.txt")
for m in ("comandi", "protocollo", "lingua", "bluetooth", "sim_bluetooth"):
    sys.modules.pop(m, None)
import sim_bluetooth
sim_bluetooth.SCENARIO = %(scenario)r
sys.modules["bluetooth"] = sim_bluetooth
_vero_run = run
def _run(f):
    def g():
        sim_bluetooth.tick()
        f()
    _vero_run(g)
G = dict(globals())
G["run"] = _run
G["__name__"] = "presentator"
with open("__init__.py") as f:
    exec(f.read(), G)
'''


# Cattura del display: il simulatore carica il framebuffer (160x120 o 320x240,
# RGBA) come texture WebGL; lo intercetto e lo converto in PNG ingrandito,
# senza la prospettiva del badge 3D.
HOOK = """
(() => {
  for (const C of [window.WebGLRenderingContext, window.WebGL2RenderingContext]) {
    if (!C) continue;
    const orig = C.prototype.texSubImage2D;
    C.prototype.texSubImage2D = function(...a) {
      const src = a[a.length - 1];
      if (src instanceof Uint8Array && a.length >= 9) {
        const w = a[4], h = a[5];
        if ((w == 160 && h == 120) || (w == 320 && h == 240))
          window.__fb = {w, h, data: src.slice()};
      }
      return orig.apply(this, a);
    };
  }
  window.__fbPng = (scala) => {
    const f = window.__fb; if (!f) return null;
    const n = f.data.length / (f.w * f.h);
    const c = document.createElement('canvas'); c.width = f.w; c.height = f.h;
    const ctx = c.getContext('2d'); const img = ctx.createImageData(f.w, f.h);
    for (let i = 0; i < f.w * f.h; i++) {
      img.data[4*i] = f.data[n*i]; img.data[4*i+1] = f.data[n*i+1];
      img.data[4*i+2] = f.data[n*i+2]; img.data[4*i+3] = 255;
    }
    ctx.putImageData(img, 0, 0);
    const k = scala * 320 / f.w;
    const g = document.createElement('canvas'); g.width = f.w * k; g.height = f.h * k;
    const gx = g.getContext('2d'); gx.imageSmoothingEnabled = false;
    gx.drawImage(c, 0, 0, g.width, g.height);
    return g.toDataURL('image/png');
  };
})();
"""


class Sim:
    def __init__(self, pg, out):
        self.pg = pg
        self.out = out
        self.n = 0
        self.lingua = "en"

    def avvia(self, scenario="ok", json=None, senza_chiave=False):
        layout, file_comandi = LINGUE[self.lingua]
        if json is None:
            if not os.path.exists(os.path.join(APP, file_comandi)):
                file_comandi = "comandi.example.json"  # comandi.json e' personale
            with open(os.path.join(APP, file_comandi), encoding="utf-8") as f:
                json = f.read()
        codice = RUNNER % {"scenario": scenario, "json": json, "senza_chiave": senza_chiave,
                           "lingua": self.lingua, "layout": layout}
        # F5 nell'editor esegue (il pulsante Run cambia icona dopo il primo avvio)
        self.pg.evaluate("c => { const e = monaco.editor.getEditors()[0]; e.setValue(c); e.focus(); }", codice)
        self.pg.keyboard.press("F5")
        self.pg.wait_for_timeout(3500)
        self.fuoco()

    def fuoco(self):
        self.pg.mouse.click(self.badge_x, self.badge_y)
        self.pg.wait_for_timeout(200)

    def tasto(self, k, volte=1, pausa=250):
        # tenuto 80 ms: un press istantaneo puo' cadere tra due frame dell'app
        for _ in range(volte):
            self.pg.keyboard.down(k)
            self.pg.wait_for_timeout(80)
            self.pg.keyboard.up(k)
            self.pg.wait_for_timeout(pausa)

    def tieni(self, k, ms=900):
        self.pg.keyboard.down(k)
        self.pg.wait_for_timeout(ms)
        self.pg.keyboard.up(k)
        self.pg.wait_for_timeout(250)

    def foto(self, nome, attesa=300):
        self.pg.wait_for_timeout(attesa)
        self.n += 1
        percorso = os.path.join(self.out, "%s_%02d_%s.png" % (self.lingua, self.n, nome))
        url = self.pg.evaluate("() => window.__fbPng(2)")
        with open(percorso, "wb") as f:
            f.write(base64.b64decode(url.split(",")[1]))
        print("  ", os.path.basename(percorso))

    def uscita(self):
        txt = self.pg.locator("body").inner_text()
        i = txt.rfind("OUTPUT")
        return txt[i:] if i >= 0 else ""


A, B, C, SU, GIU = "ArrowLeft", "Space", "ArrowRight", "ArrowUp", "ArrowDown"


def scenario_ok(s):
    s.avvia("ok")
    s.foto("menu")
    s.tasto(GIU)
    s.foto("menu_seconda_voce")
    s.tasto(SU)
    s.tasto(B)
    s.foto("presentazione")
    s.tasto(C, 3)
    s.foto("presentazione_avanti_toast", 50)
    s.tieni(SU)
    s.pg.wait_for_timeout(2500)
    s.foto("presentazione_avviata_timer")
    s.tasto(B)
    s.foto("presentazione_schermo_nero")
    s.tasto(B)
    s.tieni(A)
    s.foto("ritorno_menu")
    s.tasto(GIU)
    s.tasto(B)
    s.foto("gruppi")
    s.tasto(GIU, 2)
    s.tasto(B)
    s.foto("voci_scorciatoie")
    s.tasto(GIU, 6)
    s.foto("voci_scorciatoie_fondo")
    s.tasto(A)
    s.tasto(SU)
    s.tasto(B)
    s.foto("voci_testi")
    s.tasto(B, pausa=600)
    s.foto("invio_in_corso", 0)
    s.tasto(A, pausa=100)
    s.foto("annullamento", 0)
    s.foto("annullato_toast", 800)
    s.tasto(A)
    s.tasto(SU)
    s.tasto(B)
    s.tasto(GIU)
    s.tasto(B, pausa=200)
    s.foto("sito_in_corso", 300)
    s.foto("sito_fatto", 2600)


def scenario_impostazioni(s):
    s.avvia("ok")
    s.tasto(GIU, 2)
    s.foto("menu_impostazioni")
    s.tasto(B)
    s.foto("impostazioni")
    s.tasto(B)
    s.foto("impostazioni_lingua_cambiata")
    s.tasto(B)  # torna alla lingua di partenza
    s.tasto(GIU)
    s.foto("impostazioni_tastiera")
    s.tasto(B)
    s.foto("impostazioni_tastiera_cambiata")
    s.tasto(A)
    s.foto("menu_dopo_impostazioni")


def scenario_stati(s):
    for scen, nome in (("nodongle", "attesa_dongle"), ("chiave", "chiave_diversa"),
                       ("versione", "versione_diversa"), ("nousb", "usb_non_pronta")):
        s.avvia(scen)
        s.foto("stato_" + nome)
        if scen == "nousb":
            s.tasto(B)
            s.tasto(C)
            s.foto("stato_usb_non_pronta_comando", 50)
    s.avvia("ok", senza_chiave=True)
    s.foto("stato_chiave_mancante")


def scenario_json(s):
    s.avvia("ok", json=JSON_ROTTO)
    s.tasto(GIU)
    s.tasto(B)
    s.foto("json_errore")
    s.avvia("ok", json=JSON_VOCI_ERRATE)
    s.tasto(GIU)
    s.tasto(B)
    s.tasto(B)
    s.foto("voci_errate_valida")
    s.tasto(GIU)
    s.foto("voci_errate_tasto")
    s.tasto(B, pausa=100)
    s.foto("voci_errate_invio_rifiutato", 0)
    s.tasto(GIU)
    s.foto("voci_errate_tilde")
    s.tasto(GIU)
    s.foto("voci_errate_campo")


SCENARI = {"ok": scenario_ok, "impostazioni": scenario_impostazioni,
           "stati": scenario_stati, "json": scenario_json}


def main():
    out = sys.argv[1]
    scelti = sys.argv[2:] or list(SCENARI)
    os.makedirs(out, exist_ok=True)
    with sync_playwright() as p:
        # senza GPU Chromium headless usa SwiftShader: il simulatore va a ~1 fps e
        # perde i tasti; con la GPU (ANGLE D3D11) va a 60 fps
        b = p.chromium.launch(args=["--enable-gpu", "--use-angle=d3d11", "--ignore-gpu-blocklist"])
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        pg.add_init_script(HOOK)
        pg.goto("https://try.badgewa.re/", wait_until="networkidle", timeout=60000)
        pg.wait_for_timeout(3000)
        pg.set_input_files("#fp-upload-input",
                           percorsi_app() + [os.path.join(QUI, "sim_bluetooth.py")])
        # tutti gli scenari in ogni lingua (i file in lang/ arrivano nella radice
        # del simulatore e il runner li sposta in /presentator/lang)
        pg.wait_for_timeout(2000)
        s = Sim(pg, out)
        # zona del badge: area a destra sopra il pannello OUTPUT
        box = pg.locator("canvas").last.bounding_box()
        s.badge_x = box["x"] + box["width"] / 2
        s.badge_y = box["y"] + box["height"] / 2
        # il primo avvio dopo l'upload non trova ancora i moduli appena
        # spostati in /presentator: un giro a vuoto prima degli scenari
        s.avvia("ok")
        for lingua in LINGUE:
            s.lingua = lingua
            s.n = 0
            for nome in scelti:
                print("scenario", lingua, nome)
                SCENARI[nome](s)
                errori = [r for r in s.uscita().splitlines() if "Error" in r or "Traceback" in r]
                if errori:
                    print("   ERRORI NELL'OUTPUT:", errori)
        print(s.uscita()[-1500:])
        b.close()


main()
