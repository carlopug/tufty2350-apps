"""Prova reale dei layout di tastiera (Windows): il dongle scrive davvero e si
confronta quello che arriva con quello che doveva arrivare.

    python -I prova_tastiera.py genera FILE.json
        scrive un comandi.json di prova: gruppo "Keyboard test" con una voce per
        layout (it, us, uk) che contiene TUTTI i caratteri che il layout sa
        scrivere. Copiarlo sul badge come apps/presentator/comandi.json
        (salvando prima quello personale).

    python -I prova_tastiera.py ricevi LAYOUT
        apre una finestra che usa il layout indicato solo per se' (senza
        cambiare le impostazioni di Windows), riceve il testo scritto dal dongle
        e lo confronta con quello atteso. Sul badge: impostare lo stesso layout
        (Language and keyboard), aprire "Keyboard test" e inviare la voce LAYOUT.
        Esito anche in prova_tastiera_LAYOUT.txt accanto a questo script.

    python -I prova_tastiera.py confronta
        senza hardware: chiede a Windows quale carattere produce ogni tasto
        (codice HID -> scan code -> ToUnicodeEx con il layout indicato) e lo
        confronta con le tabelle di comandi.py, per tutti e tre i layout.

ATTENZIONE: il dongle scrive nella finestra che ha il fuoco. Durante la prova
la finestra di ricezione deve restare in primo piano.
"""

import ctypes
import json
import os
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(QUI, "..", "..", "apps", "presentator"))

import comandi as C  # noqa: E402

# identificativi dei layout di Windows (KLID)
KLID = {"it": "00000410", "us": "00000409", "uk": "00000809"}
KLF_ACTIVATE = 0x00000001
KLF_SETFORPROCESS = 0x00000100


def caratteri(layout):
    # tutti i caratteri del layout, in ordine, piu' un a capo finale
    m = C.costruisci_layout(layout)
    return "".join(sorted(c for c in m if c not in "\n\t")) + "\n"


def genera(percorso):
    voci = [{"name": codice, "text": caratteri(codice)} for codice in C.LAYOUTS]
    dati = {"groups": [{"name": "Keyboard test", "commands": voci}]}
    with open(percorso, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=1)
    for v in voci:
        print("%s: %d caratteri" % (v["name"], len(v["text"]) - 1))


def ricevi(layout):
    import tkinter as tk

    atteso = caratteri(layout)
    user32 = ctypes.windll.user32
    hkl = user32.LoadKeyboardLayoutW(KLID[layout], KLF_ACTIVATE | KLF_SETFORPROCESS)
    if not hkl:
        sys.exit("impossibile caricare il layout %s" % KLID[layout])

    root = tk.Tk()
    root.title("Presentator keyboard test: %s" % layout.upper())
    root.attributes("-topmost", True)
    tk.Label(root, text="Layout %s attivo per questa finestra.\nSul badge: tastiera %s, "
             "gruppo 'Keyboard test', voce '%s', premi B." % (layout.upper(), layout.upper(), layout),
             font=("Segoe UI", 11), justify="left").pack(padx=10, pady=6, anchor="w")
    testo = tk.Text(root, width=70, height=6, font=("Consolas", 12))
    testo.pack(padx=10, pady=6)
    esito = tk.Label(root, text="In attesa...", font=("Segoe UI", 11, "bold"))
    esito.pack(padx=10, pady=6)
    stato = {"ultimo": None}

    def controlla():
        ricevuto = testo.get("1.0", "end-1c")
        if ricevuto and ricevuto == stato["ultimo"]:  # fermo da un giro: confronta
            righe = ["layout %s: atteso %d caratteri, ricevuti %d" % (layout, len(atteso), len(ricevuto))]
            diversi = [(i, a, b) for i, (a, b) in enumerate(zip(atteso, ricevuto)) if a != b]
            if ricevuto == atteso:
                righe.append("OK: identico")
            else:
                for i, a, b in diversi[:40]:
                    righe.append("pos %d: atteso %r ricevuto %r" % (i, a, b))
                if len(ricevuto) != len(atteso):
                    righe.append("lunghezza diversa; coda ricevuta: %r" % ricevuto[len(atteso) - 5:])
            with open(os.path.join(QUI, "prova_tastiera_%s.txt" % layout), "w", encoding="utf-8") as f:
                f.write("\n".join(righe) + "\n" + "ricevuto: %r\n" % ricevuto)
            print("\n".join(righe))
            esito.config(text=righe[1] if ricevuto == atteso else "DIFFERENZE: %d" % len(diversi),
                         fg="green" if ricevuto == atteso else "red")
            root.after(4000, root.destroy)
            return
        stato["ultimo"] = ricevuto
        root.after(1500, controlla)

    def fuoco():
        user32.ActivateKeyboardLayout(hkl, 0)
        root.focus_force()
        testo.focus_set()

    root.after(200, fuoco)
    root.after(1500, controlla)
    root.mainloop()


# codice HID -> scan code PS/2 (set 1) dei tasti usati dalle tabelle
_SCAN = dict(zip(range(0x04, 0x1E), (0x1E, 0x30, 0x2E, 0x20, 0x12, 0x21, 0x22, 0x23, 0x17, 0x24, 0x25,
                                     0x26, 0x32, 0x31, 0x18, 0x19, 0x10, 0x13, 0x1F, 0x14, 0x16, 0x2F,
                                     0x11, 0x2D, 0x15, 0x2C)))
_SCAN.update(zip(range(0x1E, 0x28), range(0x02, 0x0C)))
_SCAN.update({0x28: 0x1C, 0x2B: 0x0F, 0x2C: 0x39, 0x2D: 0x0C, 0x2E: 0x0D, 0x2F: 0x1A, 0x30: 0x1B,
              0x31: 0x2B, 0x32: 0x2B, 0x33: 0x27, 0x34: 0x28, 0x35: 0x29, 0x36: 0x33, 0x37: 0x34,
              0x38: 0x35, 0x64: 0x56})


def confronta():
    user32 = ctypes.windll.user32
    errori = 0
    for layout in C.LAYOUTS:
        hkl = user32.LoadKeyboardLayoutW(KLID[layout], 0)
        if not hkl:
            print("%s: layout %s non disponibile" % (layout, KLID[layout]))
            errori += 1
            continue
        n = 0
        for car, (mod, hid) in sorted(C.costruisci_layout(layout).items()):
            stato = (ctypes.c_ubyte * 256)()
            if mod & C.SHIFT:
                stato[0x10] = stato[0xA0] = 0x80
            if mod & C.ALTGR:  # AltGr = Ctrl + Alt destro
                stato[0x11] = stato[0xA2] = stato[0x12] = stato[0xA5] = 0x80
            scan = _SCAN[hid]
            vk = user32.MapVirtualKeyExW(scan, 3, hkl)  # MAPVK_VSC_TO_VK_EX
            buf = ctypes.create_unicode_buffer(8)
            r = user32.ToUnicodeEx(vk, scan, stato, buf, 8, 0, hkl)
            if r < 0:  # tasto morto: svuota lo stato e segnala
                user32.ToUnicodeEx(vk, scan, stato, buf, 8, 0, hkl)
            ottenuto = buf.value[:r] if r > 0 else ("<morto>" if r < 0 else "")
            if car == "\n":
                ottenuto = ottenuto.replace("\r", "\n")
            n += 1
            if ottenuto != car:
                errori += 1
                print("%s: %r (mod %02x, HID %02x) -> Windows scrive %r" % (layout, car, mod, hid, ottenuto))
        print("%s: %d caratteri controllati" % (layout, n))
    print("errori:", errori)
    return errori


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "confronta":
        sys.exit(1 if confronta() else 0)
    if len(sys.argv) == 3 and sys.argv[1] == "genera":
        genera(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == "ricevi" and sys.argv[2] in KLID:
        ricevi(sys.argv[2])
    else:
        sys.exit(__doc__)
