// Test sul PC di src/proto_core.cpp contro i vettori di genera_vettori.py.
//   g++ -std=c++17 -I../src test_proto.cpp ../src/proto_core.cpp -o test_proto

#include <stdio.h>
#include <string.h>

#include "proto_core.h"
#include "vettori.h"

using namespace proto;

static uint8_t buf[MAX_MESSAGGIO];

int main() {
    int errori = 0, controlli = 0;
    if (!selfTest()) {
        printf("FALLITO: HMAC RFC 4231\n");
        errori++;
    }
    controlli++;

    Ricevitore rx(buf, sizeof(buf));
    Sessione s;
    memcpy(s.chiave, CHIAVE_TEST, 32);
    memcpy(s.nonce, NONCE_TEST, 8);
    s.attiva = true;
    s.ultimoContatore = 0;
    Messaggio m = {};
    bool haMessaggio = false;
    int passo = 0;

    size_t i = 0;
    while (i < sizeof(SCRIPT)) {
        uint8_t op = SCRIPT[i++];
        passo++;
        if (op == 3) {
            s.ultimoContatore = 0;
            rx.reset();
            continue;
        }
        size_t n = SCRIPT[i] | SCRIPT[i + 1] << 8;
        const uint8_t *dati = SCRIPT + i + 2;
        i += 2 + n;
        controlli++;
        if (op == 1) {
            int r = rx.aggiungi(dati, n);
            if (r != Ricevitore::SERVE_ALTRO) {
                printf("FALLITO passo %d: pezzo intermedio -> %d\n", passo, r);
                errori++;
            }
        } else if (op == 2) {
            uint8_t atteso = SCRIPT[i++];
            int r = rx.aggiungi(dati, n);
            uint8_t esito = (uint8_t)r;
            haMessaggio = false;
            if (r == Ricevitore::COMPLETO) {
                esito = verifica(s, rx.dati(), rx.dimensione(), m);
                haMessaggio = esito == ESITO_FATTO;
            }
            if (esito != atteso) {
                printf("FALLITO passo %d: esito 0x%02x, atteso 0x%02x\n", passo, esito, atteso);
                errori++;
            }
        } else if (op == 4) {
            bool valido = SCRIPT[i++] != 0;
            if (!haMessaggio || m.len != n || memcmp(m.dati, dati, n) != 0) {
                printf("FALLITO passo %d: dati diversi da quelli inviati\n", passo);
                errori++;
            } else if (passiValidi(m.dati, m.len) != valido) {
                printf("FALLITO passo %d: passiValidi() != %d\n", passo, valido);
                errori++;
            } else if (valido) {
                // il lettore deve consumare tutti i dati
                LettorePassi lp(m.dati, m.len);
                Passo p;
                int k = 0;
                while (lp.prossimo(p)) k++;
                if (k == 0) {
                    printf("FALLITO passo %d: nessun passo letto\n", passo);
                    errori++;
                }
            }
        } else {
            printf("script corrotto all'offset %zu\n", i);
            return 2;
        }
    }
    printf("%d controlli, %d errori\n", controlli, errori);
    return errori ? 1 : 0;
}
