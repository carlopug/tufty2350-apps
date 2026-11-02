"""Genera la chiave segreta condivisa tra badge e dongle.

    python genera_chiave.py            (rifiuta di sovrascrivere chiavi esistenti)
    python genera_chiave.py --forza    (nuova chiave: vanno aggiornati ENTRAMBI)

Scrive:
  apps/presentator/chiave.txt     da copiare sul badge insieme all'app
  presentator_dongle/src/chiave.h compilata nel firmware del dongle
Entrambi i file sono esclusi da git. Dopo una nuova chiave: ricaricare il
firmware del dongle E ricopiare chiave.txt sul badge.
"""

import hashlib
import os
import secrets
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
TXT = os.path.normpath(os.path.join(QUI, "..", "..", "apps", "presentator", "chiave.txt"))
HDR = os.path.normpath(os.path.join(QUI, "..", "src", "chiave.h"))

if (os.path.exists(TXT) or os.path.exists(HDR)) and "--forza" not in sys.argv:
    sys.exit("Chiave gia' presente (%s / %s). Usa --forza per crearne una nuova." % (TXT, HDR))

chiave = secrets.token_bytes(32)
impronta = hashlib.sha256(chiave).hexdigest()[:8]

with open(TXT, "w") as f:
    f.write(chiave.hex() + "\n")

with open(HDR, "w") as f:
    f.write("// Generato da tools/genera_chiave.py: NON mettere in git.\n")
    f.write("// Impronta (primi 4 byte di SHA-256): %s\n" % impronta)
    f.write("#pragma once\n#include <stdint.h>\n")
    f.write("static const uint8_t PRESENTATOR_KEY[32] = {\n    ")
    f.write(", ".join("0x%02x" % b for b in chiave))
    f.write("\n};\n")

print("Chiave creata, impronta %s" % impronta)
print("  badge : %s" % TXT)
print("  dongle: %s" % HDR)
