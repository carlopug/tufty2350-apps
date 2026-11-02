"""Test su PC (CPython) dei moduli del badge: apps/presentator/protocollo.py
e comandi.py, incluso il comandi.json di esempio.

    python -I test_badge.py
"""

import hashlib
import hmac
import os
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(QUI, "..", "..", "apps", "presentator")
sys.path.insert(0, APP)

import protocollo as P  # noqa: E402
import comandi as C  # noqa: E402

errori = 0


def ok(cond, msg):
    global errori
    if not cond:
        errori += 1
        print("FALLITO:", msg)


# HMAC fatto a mano contro la libreria standard
for k in (b"Jefe", bytes(range(32)), b"x" * 100):
    for m in (b"", b"what do ya want for nothing?", bytes(5000)):
        ok(P.hmac_sha256(k, m) == hmac.new(k, m, hashlib.sha256).digest(), "hmac %r" % k[:4])

# layout italiano: alcuni tasti noti
attesi = {
    "a": (0, 0x04), "A": (C.SHIFT, 0x04), "1": (0, 0x1E), "!": (C.SHIFT, 0x1E),
    "/": (C.SHIFT, 0x24), ":": (C.SHIFT, 0x37), "@": (C.ALTGR, 0x33), "#": (C.ALTGR, 0x34),
    "è": (0, 0x2F), "é": (C.SHIFT, 0x2F), "[": (C.ALTGR, 0x2F), "{": (C.ALTGR | C.SHIFT, 0x2F),
    "à": (0, 0x34), "ò": (0, 0x33), "ù": (0, 0x31), "ì": (0, 0x2E), "-": (0, 0x38),
    "_": (C.SHIFT, 0x38), "?": (C.SHIFT, 0x2D), "=": (C.SHIFT, 0x27), "€": (C.ALTGR, 0x08),
    "\n": (0, 0x28),
}
for c, k in attesi.items():
    ok(C.LAYOUT.get(c) == k, "layout %r -> %r, atteso %r" % (c, C.LAYOUT.get(c), k))
ok(len(C.coppie_testo("https://shop.pimoroni.com/products")) == 34, "url")
for cattivo in ("~", "`", "😀"):
    try:
        C.coppie_testo(cattivo)
        ok(False, "carattere %r doveva essere rifiutato" % cattivo)
    except C.ErroreComando:
        pass

# combinazioni
ok(C.passi_combinazioni("WIN+D") == bytes((1, C.WIN, 0x07)), "WIN+D")
ok(C.passi_combinazioni("ctrl+shift+t") == bytes((1, C.CTRL | C.SHIFT, 0x17)), "ctrl+shift+t")
ok(C.passi_combinazioni("CTRL+C CTRL+V") == bytes((1, 1, 0x06, 1, 1, 0x19)), "due combinazioni")
ok(C.passi_combinazioni("VOLSU") == bytes((4, 0xE9, 0)), "volume")
ok(C.passi_combinazioni("WIN") == bytes((1, C.WIN, 0)), "WIN da solo")
ok(C.passi_combinazioni("F12") == bytes((1, 0, 0x45)), "F12")
for cattivo in ("CTRL+", "PIPPO+A", "CTRL+VOLSU", "CTRL+QUALCOSA"):
    try:
        C.passi_combinazioni(cattivo)
        ok(False, "combinazione %r doveva essere rifiutata" % cattivo)
    except C.ErroreComando:
        pass

# il file di esempio (e quello personale, se c'e') deve caricarsi senza errori
for nome in ("comandi.example.json", "comandi.json"):
    percorso = os.path.join(APP, nome)
    if nome == "comandi.json" and not os.path.exists(percorso):
        continue
    with open(percorso, encoding="utf-8") as f:
        gruppi, err = C.carica(f.read())
    ok(err is None, "%s: %s" % (nome, err))
    for g in gruppi:
        for c in g["comandi"]:
            ok(c["errore"] is None, "%s %s / %s: %s" % (nome, g["nome"], c["nome"], c["errore"]))
    print("%s: %d gruppi, %d comandi" % (nome, len(gruppi), sum(len(g["comandi"]) for g in gruppi)))

# errori segnalati con la riga giusta
casi = [
    ('{"gruppi": [\n {"nome": "a",\n  "comandi": []\n }\n ,]\n}', 5),   # virgola di troppo
    ('{"gruppi": [\n {"nome": "a"\n  "comandi": []}\n]}', 3),             # virgola mancante
    ('{"gruppi": [\n {"nome": "a, \n "comandi": []}]}', 2),               # testo non chiuso
    ("{'gruppi': []}", 1),                                                # apici singoli
]
for testo, riga in casi:
    g, err = C.carica(testo)
    ok(err is not None and ("riga %d:" % riga) in err, "errore JSON %r -> %s" % (testo[:20], err))

g, err = C.carica('{"gruppi": [{"nome": "x", "comandi": [{"nome": "y", "tasti": "PIPPO"}, {"nome": "z", "url": "http://a"}]}]}')
ok(err is None and g[0]["comandi"][0]["errore"] and g[0]["comandi"][1]["dati"], "errore sul singolo comando")

# testo a schermo
ok(C.per_schermo("Perché è già") == "Perche' e' gia'", "per_schermo")

print("errori:", errori)
sys.exit(1 if errori else 0)
