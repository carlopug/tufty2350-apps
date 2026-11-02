# Modulo "bluetooth" finto per provare apps/presentator nel simulatore
# https://try.badgewa.re/ (che non ha il Bluetooth). Simula il dongle:
# si collega, invia saluto con l'impronta della chiave e stato USB, riceve i
# pezzi dei messaggi e risponde con gli esiti. Non verifica le firme (lo fa
# gia' tools/test_proto.cpp): serve a vedere grafica e flusso dell'app.
#
# SCENARIO (impostato da prova_simulatore.py prima di avviare l'app):
#   "ok"         dongle pronto
#   "nodongle"   nessun dongle: resta "In attesa del dongle..."
#   "chiave"     impronta diversa: "Chiave diversa dal dongle"
#   "versione"   protocollo vecchio: "Versione dongle diversa"
#   "nousb"      dongle collegato ma USB del PC non pronta

import hashlib
import time

SCENARIO = "ok"
DURATA_MACRO_MS = 2500   # le macro lunghe restano "in corso" per questo tempo

_ble = None


def UUID(s):
    # MicroPython non ha __bytes__: l'app fa bytes(UUID), quindi restituisco bytes
    return bytes.fromhex(s.replace("-", ""))


def tick():
    if _ble is not None:
        _ble._tick()


def _u32(v):
    return bytes((v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF))


class BLE:
    def __init__(self):
        global _ble
        _ble = self
        self.vals = {}
        self.cb = None
        self.eventi = []
        self.buf = b""
        self.in_corso = None
        self.collegato = False

    # --- API usate dall'app ---
    def active(self, *a):
        return True

    def config(self, *a, **k):
        if a and a[0] == "mac":
            return (0, b"\x28\xcd\xc1\x19\x41\xdb")
        return None

    def irq(self, cb):
        self.cb = cb

    def gatts_register_services(self, servizi):
        return ((1, 2),)

    def gatts_set_buffer(self, *a):
        pass

    def gatts_write(self, h, v):
        self.vals[h] = bytes(v)

    def gatts_read(self, h):
        return self.vals.get(h, b"")

    def gap_advertise(self, *a, **k):
        if SCENARIO != "nodongle" and not self.collegato:
            self._dopo(1200, self._collega)

    def gap_disconnect(self, conn):
        pass

    def gatts_notify(self, conn, h, dati):
        self._ricevi(bytes(dati))

    # --- simulazione del dongle ---
    def _dopo(self, ms, fn):
        self.eventi.append((time.ticks_add(time.ticks_ms(), ms), fn))

    def _tick(self):
        ora = time.ticks_ms()
        pronti = [e for e in self.eventi if time.ticks_diff(ora, e[0]) >= 0]
        self.eventi = [e for e in self.eventi if time.ticks_diff(ora, e[0]) < 0]
        for _, fn in pronti:
            fn()

    def _stato(self, valore):
        self.vals[2] = valore
        self.cb(3, (0, 2))

    def _collega(self):
        self.collegato = True
        self.cb(1, (0, 0, b"\x00" * 6))
        self.cb(21, (0, 247))
        self._dopo(400, self._saluto)

    def _saluto(self):
        try:
            with open("chiave.txt") as f:
                h = "".join(f.read().split())
            chiave = bytes([int(h[i:i + 2], 16) for i in range(0, 64, 2)])
            impronta = hashlib.sha256(chiave).digest()[:4]
        except Exception:
            impronta = b"\x00\x00\x00\x00"
        if SCENARIO == "chiave":
            impronta = b"\xde\xad\xbe\xef"
        versione = 1 if SCENARIO == "versione" else 2
        self._stato(bytes((2, versione)) + bytes(range(8)) + impronta)
        self._dopo(300, lambda: self._stato(bytes((1, 0 if SCENARIO == "nousb" else 1))))

    def _esito(self, contatore, codice):
        self._stato(b"\x03" + _u32(contatore) + bytes((codice,)))

    def _ricevi(self, pezzo):
        if pezzo[0] & 0x80:
            self.buf = b""
        self.buf += pezzo[1:]
        if len(self.buf) < 10:
            return
        lung = self.buf[8] | self.buf[9] << 8
        if len(self.buf) < 10 + lung + 18:
            return
        tipo = self.buf[3]
        contatore = self.buf[4] | self.buf[5] << 8 | self.buf[6] << 16 | self.buf[7] << 24
        self.buf = b""
        if tipo == 2:  # annulla
            self._esito(contatore, 0)
            if self.in_corso is not None:
                c = self.in_corso
                self.in_corso = None
                self.eventi = []  # niente "fatto" per la macro interrotta
                self._dopo(300, lambda: self._esito(c, 0x02))
            return
        if lung > 40:
            self.in_corso = contatore
            self._dopo(100, lambda: self._esito(contatore, 0x01))
            self._dopo(DURATA_MACRO_MS, lambda: self._fine(contatore))
        else:
            self._dopo(50, lambda: self._esito(contatore, 0x00))

    def _fine(self, contatore):
        if self.in_corso == contatore:
            self.in_corso = None
            self._esito(contatore, 0x00)
