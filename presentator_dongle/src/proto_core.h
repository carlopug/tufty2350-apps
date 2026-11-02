// Protocollo firmato badge <-> dongle (versione 2), parte senza Arduino.
//
// Compila anche sul PC (tools/test_proto.cpp) per provare ricostruzione e
// verifica dei messaggi contro i vettori generati dal codice del badge.
// Il formato e' descritto in apps/presentator/protocollo.py: tenerli allineati.

#pragma once

#include <stddef.h>
#include <stdint.h>

namespace proto {

constexpr uint8_t VERSIONE = 2;
constexpr uint8_t TIPO_MACRO = 1;
constexpr uint8_t TIPO_ANNULLA = 2;

constexpr uint8_t PASSO_TASTO = 1;
constexpr uint8_t PASSO_PAUSA = 2;
constexpr uint8_t PASSO_TASTI = 3;
constexpr uint8_t PASSO_MEDIA = 4;

constexpr size_t MAX_PAYLOAD = 6000;
constexpr size_t FIRMA_LEN = 16;
constexpr size_t TESTA_LEN = 10;  // 'P' 'R' versione tipo contatore(4) lunghezza(2)
constexpr size_t CODA_LEN = FIRMA_LEN + 2;
constexpr size_t MAX_MESSAGGIO = TESTA_LEN + MAX_PAYLOAD + CODA_LEN;

constexpr uint8_t ST_USB = 1;
constexpr uint8_t ST_HELLO = 2;
constexpr uint8_t ST_ESITO = 3;

constexpr uint8_t ESITO_FATTO = 0x00;
constexpr uint8_t ESITO_IN_CORSO = 0x01;
constexpr uint8_t ESITO_ANNULLATO = 0x02;
constexpr uint8_t ESITO_FORMATO = 0x10;
constexpr uint8_t ESITO_FIRMA = 0x11;
constexpr uint8_t ESITO_RIPETUTO = 0x12;
constexpr uint8_t ESITO_TROPPO_LUNGO = 0x13;
constexpr uint8_t ESITO_OCCUPATO = 0x14;
constexpr uint8_t ESITO_USB = 0x15;
constexpr uint8_t ESITO_PASSO = 0x16;
constexpr uint8_t ESITO_NO_SESSIONE = 0x17;

class Sha256 {
public:
    Sha256();
    void update(const uint8_t *data, size_t len);
    void finish(uint8_t out[32]);

private:
    void block(const uint8_t *p);
    uint32_t h_[8];
    uint8_t buf_[64];
    size_t bufLen_;
    uint64_t total_;
};

void sha256(const uint8_t *data, size_t len, uint8_t out[32]);
// HMAC-SHA256 su (a || b): evita di copiare nonce e messaggio in un buffer unico
void hmacSha256(const uint8_t *key, size_t keyLen, const uint8_t *a, size_t aLen,
                const uint8_t *b, size_t bLen, uint8_t out[32]);
bool selfTest();  // vettore RFC 4231 n. 2

// Ricostruisce un messaggio dai pezzi ricevuti via notify.
class Ricevitore {
public:
    enum { SERVE_ALTRO = 0, COMPLETO = 1 };  // altrimenti un codice ESITO_*
    Ricevitore(uint8_t *buf, size_t cap) : buf_(buf), cap_(cap) { reset(); }
    int aggiungi(const uint8_t *pezzo, size_t len);
    void reset();
    const uint8_t *dati() const { return buf_; }
    size_t dimensione() const { return len_; }
    uint32_t contatore() const;  // 0 se non ancora ricevuto

private:
    uint8_t *buf_;
    size_t cap_;
    size_t len_;
    size_t totale_;
    uint8_t atteso_;
    bool attivo_;
};

struct Sessione {
    uint8_t chiave[32];
    uint8_t nonce[8];
    uint32_t ultimoContatore;
    bool attiva;
};

struct Messaggio {
    uint8_t tipo;
    uint32_t contatore;
    const uint8_t *dati;
    uint16_t len;
};

// ESITO_FATTO se il messaggio e' integro, firmato e nuovo (aggiorna il contatore).
uint8_t verifica(Sessione &s, const uint8_t *msg, size_t len, Messaggio &out);

// Controlla che i passi siano ben formati prima di eseguirne anche uno solo.
bool passiValidi(const uint8_t *p, size_t len);

struct Passo {
    uint8_t tipo;    // PASSO_TASTO, PASSO_PAUSA o PASSO_MEDIA (i PASSO_TASTI sono espansi)
    uint8_t mod;
    uint8_t tasto;
    uint16_t valore;  // ms per la pausa, uso HID per i tasti multimediali
};

class LettorePassi {
public:
    LettorePassi(const uint8_t *p, size_t len) : p_(p), len_(len), pos_(0), restanti_(0) {}
    bool prossimo(Passo &out);

private:
    const uint8_t *p_;
    size_t len_;
    size_t pos_;
    uint8_t restanti_;
};

}  // namespace proto
