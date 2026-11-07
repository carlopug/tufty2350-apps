"""Genera tools/vettori.h: messaggi di prova prodotti dal codice del badge
(apps/presentator/protocollo.py) da far verificare a src/proto_core.cpp.

    python genera_vettori.py && g++ -std=c++17 -I../src test_proto.cpp ../src/proto_core.cpp -o test_proto && ./test_proto

Script del vettore (byte):
  1 len16 dati            pezzo intermedio: il ricevitore deve chiedere altro
  2 len16 dati esito      ultimo pezzo: esito atteso (ricostruzione + verifica)
  3                       nuova sessione (azzera il contatore del dongle)
  4 len16 dati valido     dati attesi dell'ultimo messaggio verificato + passiValidi()
"""

import os
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(QUI, "..", "..", "apps", "presentator"))

import protocollo as P  # noqa: E402
import comandi as C  # noqa: E402

C.imposta_layout("it")  # i testi di prova contengono lettere accentate italiane

CHIAVE = bytes(range(32))
NONCE = bytes([0xA0 + i for i in range(8)])
PEZZO = 20  # MTU minima BLE: 20 byte utili per notify

script = bytearray()


def u16(n):
    return bytes((n & 0xFF, n >> 8))


def invia(msg, esito, dim=PEZZO):
    pz = P.pezzi(msg, dim)
    for p in pz[:-1]:
        script.extend(b"\x01" + u16(len(p)) + p)
    script.extend(b"\x02" + u16(len(pz[-1])) + pz[-1] + bytes((esito,)))


def invia_pezzi(pz, esito):
    for p in pz[:-1]:
        script.extend(b"\x01" + u16(len(p)) + p)
    script.extend(b"\x02" + u16(len(pz[-1])) + pz[-1] + bytes((esito,)))


def controlla_dati(dati, valido):
    script.extend(b"\x04" + u16(len(dati)) + dati + bytes((1 if valido else 0,)))


def nuova_sessione():
    script.extend(b"\x03")


s = P.Sessione(CHIAVE)
s.avvia(NONCE)
nuova_sessione()

# 1. comando corto della presentazione
d = C.PRESENTAZIONE["avanti"]
invia(s.messaggio(P.TIPO_MACRO, d), P.ESITO_FATTO)
controlla_dati(d, True)

# 2. testo lungo con accenti e caratteri AltGr, pezzi da 20 byte
d = C.compila({"nome": "t", "apri": "notepad",
               "testo": ("Perché è già così? @#[]{} € 100%\n" * 60)[:2000]})
invia(s.messaggio(P.TIPO_MACRO, d), P.ESITO_FATTO)
controlla_dati(d, True)

# 3. stesso testo con MTU grande (244 byte utili)
invia(s.messaggio(P.TIPO_MACRO, d), P.ESITO_FATTO, dim=244)
controlla_dati(d, True)

# 4. firma alterata
m = bytearray(s.messaggio(P.TIPO_MACRO, C.PRESENTAZIONE["indietro"]))
m[-3] ^= 0x01
invia(bytes(m), P.ESITO_FIRMA)

# 5. messaggio ripetuto (replay)
m = s.messaggio(P.TIPO_MACRO, C.PRESENTAZIONE["indietro"])
invia(m, P.ESITO_FATTO)
invia(m, P.ESITO_RIPETUTO)

# 6. pezzo mancante: il ricevitore se ne accorge sul pezzo successivo
m = s.messaggio(P.TIPO_MACRO, C.compila({"nome": "t", "testo": "x" * 100}))
pz = P.pezzi(m, PEZZO)
script.extend(b"\x01" + u16(len(pz[0])) + pz[0])
script.extend(b"\x02" + u16(len(pz[2])) + pz[2] + bytes((P.ESITO_FORMATO,)))

# 7. dopo l'errore un messaggio nuovo passa di nuovo
d = C.PRESENTAZIONE["nero"]
invia(s.messaggio(P.TIPO_MACRO, d), P.ESITO_FATTO)
controlla_dati(d, True)

# 8. firmato con un nonce diverso (sessione vecchia)
vecchia = P.Sessione(CHIAVE)
vecchia.avvia(bytes(8))
vecchia.contatore = 1000
invia(vecchia.messaggio(P.TIPO_MACRO, C.PRESENTAZIONE["fine"]), P.ESITO_FIRMA)

# 9. firmato con un'altra chiave
altra = P.Sessione(bytes(32))
altra.avvia(NONCE)
altra.contatore = 2000
invia(altra.messaggio(P.TIPO_MACRO, C.PRESENTAZIONE["fine"]), P.ESITO_FIRMA)

# 10. dati oltre il limite: dichiarati nella testata, rifiutati subito
corpo = bytes((P.VERSIONE, P.TIPO_MACRO)) + bytes((50, 0, 0, 0)) + u16(P.MAX_PAYLOAD + 1)
invia_pezzi(P.pezzi(b"PR" + corpo + b"\x01\x00\x28", PEZZO), P.ESITO_TROPPO_LUNGO)

# 11. passo sconosciuto con firma valida: la verifica passa, passiValidi() no
d = b"\x09\x00\x00"
invia(s.messaggio(P.TIPO_MACRO, d), P.ESITO_FATTO)
controlla_dati(d, False)

# 12. annulla (dati vuoti)
invia(s.messaggio(P.TIPO_ANNULLA, b""), P.ESITO_FATTO)

# 13. nuova sessione: il contatore riparte, il vecchio nonce non vale piu'
nuova_sessione()
s.avvia(NONCE)  # stesso nonce solo per il test: il dongle ne genera uno nuovo ogni volta
d = C.PRESENTAZIONE["avvio_qui"]
invia(s.messaggio(P.TIPO_MACRO, d), P.ESITO_FATTO)
controlla_dati(d, True)

righe = ["// Generato da genera_vettori.py: non modificare a mano.", "#pragma once", "#include <stdint.h>",
         "static const uint8_t CHIAVE_TEST[32] = {%s};" % ", ".join(str(b) for b in CHIAVE),
         "static const uint8_t NONCE_TEST[8] = {%s};" % ", ".join(str(b) for b in NONCE),
         "static const uint8_t SCRIPT[] = {"]
for i in range(0, len(script), 24):
    righe.append("    " + ", ".join(str(b) for b in script[i:i + 24]) + ",")
righe.append("};")
with open(os.path.join(QUI, "vettori.h"), "w") as f:
    f.write("\n".join(righe) + "\n")
print("vettori.h: %d byte di script" % len(script))
