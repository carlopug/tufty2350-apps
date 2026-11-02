#include "proto_core.h"

#include <string.h>

namespace proto {

// --- SHA-256 (FIPS 180-4) ----------------------------------------------------

static const uint32_t K[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
};

static inline uint32_t rotr(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }

Sha256::Sha256() : bufLen_(0), total_(0) {
    static const uint32_t H0[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                                   0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    memcpy(h_, H0, sizeof(h_));
}

void Sha256::block(const uint8_t *p) {
    uint32_t w[64];
    for (int i = 0; i < 16; i++) {
        w[i] = (uint32_t)p[4 * i] << 24 | (uint32_t)p[4 * i + 1] << 16 | (uint32_t)p[4 * i + 2] << 8 | p[4 * i + 3];
    }
    for (int i = 16; i < 64; i++) {
        uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
        uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = h_[0], b = h_[1], c = h_[2], d = h_[3], e = h_[4], f = h_[5], g = h_[6], h = h_[7];
    for (int i = 0; i < 64; i++) {
        uint32_t t1 = h + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i];
        uint32_t t2 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
        h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
    }
    h_[0] += a; h_[1] += b; h_[2] += c; h_[3] += d; h_[4] += e; h_[5] += f; h_[6] += g; h_[7] += h;
}

void Sha256::update(const uint8_t *data, size_t len) {
    total_ += len;
    while (len > 0) {
        size_t n = 64 - bufLen_;
        if (n > len) n = len;
        memcpy(buf_ + bufLen_, data, n);
        bufLen_ += n;
        data += n;
        len -= n;
        if (bufLen_ == 64) {
            block(buf_);
            bufLen_ = 0;
        }
    }
}

void Sha256::finish(uint8_t out[32]) {
    uint64_t bits = total_ * 8;
    uint8_t pad = 0x80;
    update(&pad, 1);
    uint8_t zero = 0;
    while (bufLen_ != 56) update(&zero, 1);
    uint8_t len[8];
    for (int i = 0; i < 8; i++) len[i] = (uint8_t)(bits >> (56 - 8 * i));
    update(len, 8);
    for (int i = 0; i < 8; i++) {
        out[4 * i] = h_[i] >> 24; out[4 * i + 1] = h_[i] >> 16; out[4 * i + 2] = h_[i] >> 8; out[4 * i + 3] = h_[i];
    }
}

void sha256(const uint8_t *data, size_t len, uint8_t out[32]) {
    Sha256 s;
    s.update(data, len);
    s.finish(out);
}

void hmacSha256(const uint8_t *key, size_t keyLen, const uint8_t *a, size_t aLen,
                const uint8_t *b, size_t bLen, uint8_t out[32]) {
    uint8_t k[64] = {0};
    if (keyLen > 64) {
        sha256(key, keyLen, k);
    } else {
        memcpy(k, key, keyLen);
    }
    uint8_t pad[64];
    for (int i = 0; i < 64; i++) pad[i] = k[i] ^ 0x36;
    uint8_t inner[32];
    Sha256 si;
    si.update(pad, 64);
    si.update(a, aLen);
    si.update(b, bLen);
    si.finish(inner);
    for (int i = 0; i < 64; i++) pad[i] = k[i] ^ 0x5c;
    Sha256 so;
    so.update(pad, 64);
    so.update(inner, 32);
    so.finish(out);
}

bool selfTest() {
    static const uint8_t atteso[32] = {
        0x5b, 0xdc, 0xc1, 0x46, 0xbf, 0x60, 0x75, 0x4e, 0x6a, 0x04, 0x24, 0x26, 0x08, 0x95, 0x75, 0xc7,
        0x5a, 0x00, 0x3f, 0x08, 0x9d, 0x27, 0x39, 0x83, 0x9d, 0xec, 0x58, 0xb9, 0x64, 0xec, 0x38, 0x43};
    const char *key = "Jefe";
    const char *msg = "what do ya want for nothing?";
    uint8_t out[32];
    hmacSha256((const uint8_t *)key, 4, (const uint8_t *)msg, strlen(msg), nullptr, 0, out);
    return memcmp(out, atteso, 32) == 0;
}

// --- ricostruzione -------------------------------------------------------------

static uint32_t le32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

void Ricevitore::reset() {
    len_ = 0;
    totale_ = 0;
    atteso_ = 0;
    attivo_ = false;
}

uint32_t Ricevitore::contatore() const { return len_ >= 8 ? le32(buf_ + 4) : 0; }

int Ricevitore::aggiungi(const uint8_t *pezzo, size_t len) {
    if (len < 2) return ESITO_FORMATO;
    uint8_t testa = pezzo[0];
    if (testa & 0x80) {
        reset();
        attivo_ = true;
    }
    if (!attivo_) return SERVE_ALTRO;  // scarta fino al prossimo inizio (errore gia' segnalato)
    if ((testa & 0x7F) != atteso_) {
        attivo_ = false;
        return ESITO_FORMATO;
    }
    atteso_ = (atteso_ + 1) & 0x7F;
    size_t n = len - 1;
    if (len_ + n > cap_) {
        attivo_ = false;
        return ESITO_TROPPO_LUNGO;
    }
    memcpy(buf_ + len_, pezzo + 1, n);
    len_ += n;
    if (len_ >= 2 && (buf_[0] != 'P' || buf_[1] != 'R')) {
        attivo_ = false;
        return ESITO_FORMATO;
    }
    if (totale_ == 0 && len_ >= TESTA_LEN) {
        size_t payload = (size_t)buf_[8] | (size_t)buf_[9] << 8;
        if (payload > MAX_PAYLOAD) {
            attivo_ = false;
            return ESITO_TROPPO_LUNGO;
        }
        totale_ = TESTA_LEN + payload + CODA_LEN;
        if (totale_ > cap_) {
            attivo_ = false;
            return ESITO_TROPPO_LUNGO;
        }
    }
    if (totale_ != 0 && len_ >= totale_) {
        attivo_ = false;
        return len_ == totale_ ? (int)COMPLETO : (int)ESITO_FORMATO;
    }
    return SERVE_ALTRO;
}

// --- verifica -------------------------------------------------------------------

uint8_t verifica(Sessione &s, const uint8_t *msg, size_t len, Messaggio &out) {
    if (len < TESTA_LEN + CODA_LEN || msg[0] != 'P' || msg[1] != 'R') return ESITO_FORMATO;
    size_t payload = (size_t)msg[8] | (size_t)msg[9] << 8;
    if (len != TESTA_LEN + payload + CODA_LEN) return ESITO_FORMATO;
    if (msg[len - 2] != 'P' || msg[len - 1] != 'E') return ESITO_FORMATO;
    if (msg[2] != VERSIONE) return ESITO_FORMATO;
    if (!s.attiva) return ESITO_NO_SESSIONE;

    uint8_t mac[32];
    hmacSha256(s.chiave, sizeof(s.chiave), s.nonce, sizeof(s.nonce), msg + 2, TESTA_LEN - 2 + payload, mac);
    const uint8_t *firma = msg + TESTA_LEN + payload;
    uint8_t diff = 0;
    for (size_t i = 0; i < FIRMA_LEN; i++) diff |= mac[i] ^ firma[i];
    if (diff != 0) return ESITO_FIRMA;

    uint32_t contatore = le32(msg + 4);
    if (contatore <= s.ultimoContatore) return ESITO_RIPETUTO;
    uint8_t tipo = msg[3];
    if (tipo != TIPO_MACRO && tipo != TIPO_ANNULLA) return ESITO_FORMATO;
    s.ultimoContatore = contatore;

    out.tipo = tipo;
    out.contatore = contatore;
    out.dati = msg + TESTA_LEN;
    out.len = (uint16_t)payload;
    return ESITO_FATTO;
}

// --- passi ----------------------------------------------------------------------

bool passiValidi(const uint8_t *p, size_t len) {
    size_t i = 0;
    if (len == 0) return false;
    while (i < len) {
        switch (p[i]) {
            case PASSO_TASTO:
            case PASSO_PAUSA:
            case PASSO_MEDIA:
                i += 3;
                break;
            case PASSO_TASTI:
                if (i + 1 >= len || p[i + 1] == 0) return false;
                i += 2 + 2 * (size_t)p[i + 1];
                break;
            default:
                return false;
        }
    }
    return i == len;
}

bool LettorePassi::prossimo(Passo &out) {
    if (restanti_ > 0) {
        out.tipo = PASSO_TASTO;
        out.mod = p_[pos_];
        out.tasto = p_[pos_ + 1];
        out.valore = 0;
        pos_ += 2;
        restanti_--;
        return true;
    }
    if (pos_ >= len_) return false;
    uint8_t tipo = p_[pos_];
    if (tipo == PASSO_TASTI) {
        restanti_ = p_[pos_ + 1];
        pos_ += 2;
        return prossimo(out);
    }
    out.tipo = tipo;
    out.mod = 0;
    out.tasto = 0;
    out.valore = 0;
    if (tipo == PASSO_TASTO) {
        out.mod = p_[pos_ + 1];
        out.tasto = p_[pos_ + 2];
    } else {
        out.valore = (uint16_t)(p_[pos_ + 1] | p_[pos_ + 2] << 8);
    }
    pos_ += 3;
    return true;
}

}  // namespace proto
