"""Test su PC (CPython) dei moduli del badge: apps/presentator/protocollo.py,
comandi.py (layout IT/US/UK) e lingua.py (lang/*.json), incluso il file di
esempio dei comandi.

    python -I test_badge.py
"""

import hashlib
import hmac
import json
import os
import re
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(QUI, "..", "..", "apps", "presentator")
LANG = os.path.join(APP, "lang")
sys.path.insert(0, APP)

import protocollo as P  # noqa: E402
import comandi as C  # noqa: E402
import lingua as L  # noqa: E402

errori = 0


def ok(cond, msg):
    global errori
    if not cond:
        errori += 1
        print("FALLITO:", msg)


def rifiutato(fn, arg):
    try:
        fn(arg)
    except C.ErroreComando:
        return True
    return False


# HMAC fatto a mano contro la libreria standard
for k in (b"Jefe", bytes(range(32)), b"x" * 100):
    for m in (b"", b"what do ya want for nothing?", bytes(5000)):
        ok(P.hmac_sha256(k, m) == hmac.new(k, m, hashlib.sha256).digest(), "hmac %r" % k[:4])

# --- file di lingua ----------------------------------------------------------
# stesse chiavi di en.json e stessi segnaposto (%s, %d, %02x) per ogni chiave
SEGNAPOSTO = re.compile(r"%[-0-9]*[sdx]")
with open(os.path.join(LANG, "en.json"), encoding="utf-8") as f:
    base = json.load(f)
for nome in sorted(os.listdir(LANG)):
    with open(os.path.join(LANG, nome), encoding="utf-8") as f:
        testi = json.load(f)
    ok(isinstance(testi.get("_name"), str), "%s: manca _name" % nome)
    ok(set(testi) == set(base), "%s: chiavi diverse da en.json: %s" % (nome, sorted(set(testi) ^ set(base))))
    for k, v in testi.items():
        if k in base:
            ok(SEGNAPOSTO.findall(v) == SEGNAPOSTO.findall(base[k]), "%s/%s: segnaposto diversi" % (nome, k))
ok([c for c, _ in L.disponibili(LANG)] == ["en", "it"], "lingue disponibili")
ok(L.carica("xx", LANG) == "en", "lingua sconosciuta -> inglese")
ok(L.t("st_ready") == "Dongle ready" and L.t("chiave_che_non_esiste") == "chiave_che_non_esiste", "t() inglese")
ok(L.t("st_version", "troppi", "argomenti") == base["st_version"], "t() con segnaposto sbagliati non solleva")
L.carica("it", LANG)
ok(L.t("st_ready") == "Dongle pronto", "t() italiano")

# --- layout di tastiera --------------------------------------------------------
ASCII = [chr(c) for c in range(0x20, 0x7F)]
for codice in C.LAYOUTS:
    m = C.costruisci_layout(codice)
    mancanti = [c for c in ASCII if c not in m]
    previsti = ["`", "~"] if codice == "it" else []
    ok(mancanti == previsti, "%s: caratteri ASCII mancanti %r" % (codice, mancanti))
    usati = {}
    for c, k in m.items():
        ok(k not in usati, "%s: %r e %r sullo stesso tasto %r" % (codice, c, usati.get(k), k))
        usati[k] = c

noti = {
    "it": {"/": (C.SHIFT, 0x24), ":": (C.SHIFT, 0x37), "@": (C.ALTGR, 0x33), "#": (C.ALTGR, 0x34),
           "è": (0, 0x2F), "é": (C.SHIFT, 0x2F), "[": (C.ALTGR, 0x2F), "{": (C.ALTGR | C.SHIFT, 0x2F),
           "à": (0, 0x34), "ò": (0, 0x33), "ù": (0, 0x31), "ì": (0, 0x2E), "-": (0, 0x38),
           "?": (C.SHIFT, 0x2D), "=": (C.SHIFT, 0x27), "€": (C.ALTGR, 0x08), "+": (0, 0x30)},
    "us": {"/": (0, 0x38), ":": (C.SHIFT, 0x33), "@": (C.SHIFT, 0x1F), "#": (C.SHIFT, 0x20),
           '"': (C.SHIFT, 0x34), "~": (C.SHIFT, 0x35), "\\": (0, 0x31), "+": (C.SHIFT, 0x2E),
           "?": (C.SHIFT, 0x38), "^": (C.SHIFT, 0x23)},
    "uk": {"@": (C.SHIFT, 0x34), '"': (C.SHIFT, 0x1F), "£": (C.SHIFT, 0x20), "#": (0, 0x32),
           "~": (C.SHIFT, 0x32), "\\": (0, 0x64), "|": (C.SHIFT, 0x64), "€": (C.ALTGR, 0x21),
           "é": (C.ALTGR, 0x08), "¬": (C.SHIFT, 0x35)},
}
for codice, attesi in noti.items():
    m = C.costruisci_layout(codice)
    for c, k in attesi.items():
        ok(m.get(c) == k, "%s: %r -> %r, atteso %r" % (codice, c, m.get(c), k))

ok(C.imposta_layout("zz") == "us", "layout sconosciuto -> us")
# "+" per nome: la posizione dipende dal layout
C.imposta_layout("us")
ok(C.passi_combinazioni("CTRL+PLUS") == bytes((1, C.CTRL | C.SHIFT, 0x2E)), "CTRL+PLUS us")
ok(rifiutato(C.coppie_testo, "è"), "us: è non scrivibile")
C.imposta_layout("it")
ok(C.passi_combinazioni("CTRL+PIU") == bytes((1, C.CTRL, 0x30)), "CTRL+PIU it")
ok(len(C.coppie_testo("https://shop.pimoroni.com/products")) == 34, "url")
for cattivo in ("~", "`", "😀"):
    ok(rifiutato(C.coppie_testo, cattivo), "it: carattere %r doveva essere rifiutato" % cattivo)

# combinazioni (indipendenti dal layout)
ok(C.passi_combinazioni("WIN+D") == bytes((1, C.WIN, 0x07)), "WIN+D")
ok(C.passi_combinazioni("ctrl+shift+t") == bytes((1, C.CTRL | C.SHIFT, 0x17)), "ctrl+shift+t")
ok(C.passi_combinazioni("CTRL+C CTRL+V") == bytes((1, 1, 0x06, 1, 1, 0x19)), "due combinazioni")
ok(C.passi_combinazioni("VOLSU") == C.passi_combinazioni("VOLUP") == bytes((4, 0xE9, 0)), "volume")
ok(C.passi_combinazioni("WIN") == bytes((1, C.WIN, 0)), "WIN da solo")
ok(C.passi_combinazioni("F12") == bytes((1, 0, 0x45)), "F12")
for cattivo in ("CTRL+", "PIPPO+A", "CTRL+VOLSU", "CTRL+QUALCOSA"):
    ok(rifiutato(C.passi_combinazioni, cattivo), "combinazione %r doveva essere rifiutata" % cattivo)

# --- file dei comandi -------------------------------------------------------------


def carica_file(nome):
    with open(os.path.join(APP, nome), encoding="utf-8") as f:
        return C.carica(f.read())


def senza_errori(nome, gruppi, err):
    ok(err is None, "%s: %s" % (nome, err))
    for g in gruppi:
        for c in g["comandi"]:
            ok(c["errore"] is None, "%s %s / %s: %s" % (nome, g["nome"], c["nome"], c["errore"]))


# l'esempio pubblico deve funzionare con tutti i layout
for codice in C.LAYOUTS:
    C.imposta_layout(codice)
    gruppi, err = carica_file("comandi.example.json")
    senza_errori("comandi.example.json [%s]" % codice, gruppi, err)
print("comandi.example.json: %d gruppi, %d comandi" % (len(gruppi), sum(len(g["comandi"]) for g in gruppi)))
# l'esempio italiano e il file personale (se c'e') con il layout italiano
C.imposta_layout("it")
gruppi, err = carica_file("comandi.example.it.json")
senza_errori("comandi.example.it.json [it]", gruppi, err)
if os.path.exists(os.path.join(APP, "comandi.json")):
    gruppi, err = carica_file("comandi.json")
    senza_errori("comandi.json [it]", gruppi, err)
    print("comandi.json: %d gruppi, %d comandi" % (len(gruppi), sum(len(g["comandi"]) for g in gruppi)))

# chiavi inglesi, italiane e miste danno lo stesso risultato
C.imposta_layout("us")
ita = C.carica('{"gruppi": [{"nome": "g", "comandi": [{"nome": "c", "apri": "notepad", "attesa": 500, "testo": "hi"},'
               ' {"nome": "p", "passi": [["tasti", "WIN+R"], ["pausa", 100], ["testo", "x"]]}]}]}')
eng = C.carica('{"groups": [{"name": "g", "commands": [{"name": "c", "open": "notepad", "wait": 500, "text": "hi"},'
               ' {"name": "p", "steps": [["keys", "WIN+R"], ["pause", 100], ["text", "x"]]}]}]}')
mix = C.carica('{"groups": [{"nome": "g", "comandi": [{"name": "c", "apri": "notepad", "wait": 500, "text": "hi"},'
               ' {"nome": "p", "steps": [["tasti", "WIN+R"], ["pause", 100], ["testo", "x"]]}]}]}')
ok(ita[1] is None and ita == eng == mix, "chiavi inglesi/italiane/miste")

# errori segnalati con la riga giusta, in entrambe le lingue
casi = [
    ('{"groups": [\n {"name": "a",\n  "commands": []\n }\n ,]\n}', 5),   # virgola di troppo
    ('{"groups": [\n {"name": "a"\n  "commands": []}\n]}', 3),            # virgola mancante
    ('{"groups": [\n {"name": "a, \n "commands": []}]}', 2),              # testo non chiuso
    ("{'groups': []}", 1),                                                # apici singoli
]
for lingua, parola in (("en", "line"), ("it", "riga")):
    L.carica(lingua, LANG)
    for testo, riga in casi:
        g, err = C.carica(testo)
        ok(err is not None and ("%s %d:" % (parola, riga)) in err, "[%s] errore JSON %r -> %s" % (lingua, testo[:20], err))
    g, err = C.carica('{"groups": [{"name": "x", "commands": [{"name": "y", "keys": "PIPPO"}, {"name": "z", "url": "http://a"}]}]}')
    ok(err is None and g[0]["comandi"][0]["errore"] and g[0]["comandi"][1]["dati"], "[%s] errore sul singolo comando" % lingua)
L.carica("en", LANG)
g, err = C.carica('{"groups": [{"name": "x", "commands": [{"name": "y", "link": "a"}]}]}')
ok(g[0]["comandi"][0]["errore"] == "unknown field: link", "messaggio d'errore in inglese")

print("errori:", errori)
sys.exit(1 if errori else 0)
