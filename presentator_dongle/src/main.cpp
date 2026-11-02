// Presentator dongle - ponte BLE -> tastiera USB per l'app "Presentator"
// del Tufty 2350 (apps/presentator).
//
// Perche' esiste: il firmware ufficiale del Tufty non supporta
// l'abbinamento BLE, quindi il badge non puo' presentarsi a Windows come
// tastiera Bluetooth. Questo ESP32-S3 fa da BLE central verso il badge
// (servizio GATT non cifrato, nessun abbinamento) e da tastiera USB HID
// standard verso il PC: niente driver, niente software da installare.
//
// Protocollo versione 2 (dettagli in apps/presentator/protocollo.py e
// src/proto_core.h): il badge invia macro di tasti gia' tradotte in codici
// HID per il layout italiano; il dongle le esegue solo se firmate con la
// chiave condivisa (src/chiave.h, generata da tools/genera_chiave.py).
// A ogni collegamento il dongle invia un nonce casuale e un contatore deve
// crescere sempre: messaggi falsi o registrati e ripetuti vengono scartati.
//
// Sicurezza aggiuntiva:
//  - il dongle si "lega" al primo badge Presentator che trova (indirizzo
//    salvato in flash) e da quel momento ignora tutti gli altri;
//    BOOT tenuto premuto 3 s cancella il legame;
//  - la scrittura si interrompe se arriva "annulla", se il badge si scollega
//    (anche il tasto HOME del badge, che lo riavvia) o se la USB si sospende.

#include <Arduino.h>
#include <NimBLEDevice.h>
#include <Preferences.h>
#include "USB.h"
#include "USBHIDConsumerControl.h"
#include "USBHIDKeyboard.h"
#include "esp_random.h"
#include "proto_core.h"

#if __has_include("chiave.h")
#include "chiave.h"
#else
#error "Manca src/chiave.h: generarla con 'python tools/genera_chiave.py' (crea anche apps/presentator/chiave.txt)"
#endif

static const NimBLEUUID SVC_UUID("b3bb28a0-5c30-4245-9c7d-2ee9a9e560f9");
static const NimBLEUUID CMD_UUID("ed860c12-e173-41b6-af88-c33fe321ca13");
static const NimBLEUUID STATUS_UUID("1d2189ac-03a9-42f3-bd51-69a7747e0b4d");

static const int UNBIND_PIN = 0;
static const uint32_t UNBIND_HOLD_MS = 3000;
static const uint32_t KEY_DOWN_MS = 8;
static const uint32_t KEY_UP_MS = 8;

USBHIDKeyboard Keyboard;
USBHIDConsumerControl Consumer;
Preferences prefs;

// Stato condiviso con i callback NimBLE/USB (girano in altri task).
static volatile bool usbMounted = false;
static volatile bool usbSuspended = false;
static volatile bool bleConnected = false;
static volatile bool connectRequested = false;
static volatile bool abortRequested = false;
static NimBLEAddress targetAddr;

static NimBLEClient *client = nullptr;
static NimBLERemoteCharacteristic *statusChr = nullptr;
static int lastUsbSent = -1;

static bool bound = false;
static NimBLEAddress boundAddr;

// --- protocollo ----------------------------------------------------------------

static uint8_t rxBuf[proto::MAX_MESSAGGIO];
static proto::Ricevitore rx(rxBuf, sizeof(rxBuf));
static proto::Sessione session;
static uint8_t fingerprint[4];

// Una sola macro alla volta: il callback BLE la copia qui, loop() la esegue.
enum ExecState : uint8_t { EXEC_IDLE, EXEC_LOADING, EXEC_PENDING, EXEC_RUNNING };
static uint8_t execBuf[proto::MAX_PAYLOAD];
static size_t execLen = 0;
static uint32_t execCounter = 0;
static volatile ExecState execState = EXEC_IDLE;
static portMUX_TYPE execMux = portMUX_INITIALIZER_UNLOCKED;

struct Result {
    uint32_t counter;
    uint8_t code;
};
static QueueHandle_t resultQueue;

static void queueResult(uint32_t counter, uint8_t code) {
    Result r = {counter, code};
    xQueueSend(resultQueue, &r, 0);
}

// --- LED di stato ---------------------------------------------------------

static void setLed(bool on) {
#if defined(STATUS_LED_PIN)
#if defined(STATUS_LED_ACTIVE_LOW)
    digitalWrite(STATUS_LED_PIN, on ? LOW : HIGH);
#else
    digitalWrite(STATUS_LED_PIN, on ? HIGH : LOW);
#endif
#elif defined(STATUS_RGB_PIN)
    // verde tenue quando collegato, spento altrimenti
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    rgbLedWrite(STATUS_RGB_PIN, 0, on ? 24 : 0, 0);
#else
    neopixelWrite(STATUS_RGB_PIN, 0, on ? 24 : 0, 0);
#endif
#else
    (void)on;
#endif
}

static void updateLed() {
    if (bleConnected) {
        setLed(true);
    } else {
        // lampeggio lento mentre cerca il badge
        setLed((millis() / 500) % 2 == 0);
    }
}

// --- USB -------------------------------------------------------------------

static void usbEvent(void *, esp_event_base_t base, int32_t id, void *) {
    if (base != ARDUINO_USB_EVENTS) return;
    switch (id) {
        case ARDUINO_USB_STARTED_EVENT: usbMounted = true; usbSuspended = false; break;
        case ARDUINO_USB_STOPPED_EVENT: usbMounted = false; break;
        case ARDUINO_USB_SUSPEND_EVENT: usbSuspended = true; break;
        case ARDUINO_USB_RESUME_EVENT: usbSuspended = false; break;
        default: break;
    }
}

static bool usbReady() { return usbMounted && !usbSuspended; }

static bool mustStop() { return abortRequested || !bleConnected || !usbReady(); }

static void releaseAll() {
    KeyReport none = {};
    Keyboard.sendReport(&none);
    Consumer.release();
}

// Pausa interrompibile.
static bool waitMs(uint32_t ms) {
    uint32_t start = millis();
    while (millis() - start < ms) {
        if (mustStop()) return false;
        delay(ms - (millis() - start) > 5 ? 5 : 1);
    }
    return true;
}

static bool tapKey(uint8_t mod, uint8_t key) {
    KeyReport r = {};
    r.modifiers = mod;
    r.keys[0] = key;
    Keyboard.sendReport(&r);
    delay(KEY_DOWN_MS);
    KeyReport none = {};
    Keyboard.sendReport(&none);
    return waitMs(KEY_UP_MS);
}

static bool tapMedia(uint16_t usage) {
    Consumer.press(usage);
    delay(30);
    Consumer.release();
    return waitMs(30);
}

// Esegue i passi gia' validati: true se completati, false se interrotti.
static bool runMacro(const uint8_t *p, size_t len) {
    proto::LettorePassi it(p, len);
    proto::Passo s;
    size_t keys = 0;
    while (it.prossimo(s)) {
        if (mustStop()) return false;
        bool ok = true;
        switch (s.tipo) {
            case proto::PASSO_TASTO: ok = tapKey(s.mod, s.tasto); keys++; break;
            case proto::PASSO_PAUSA: ok = waitMs(s.valore); break;
            case proto::PASSO_MEDIA: ok = tapMedia(s.valore); break;
        }
        if (!ok) return false;
    }
    Serial.printf("macro eseguita: %u tasti\n", (unsigned)keys);
    return true;
}

// --- BLE -------------------------------------------------------------------

static void loadBinding() {
    String addr = prefs.getString("addr", "");
    if (addr.length() > 0) {
        boundAddr = NimBLEAddress(std::string(addr.c_str()), prefs.getUChar("type", 0));
        bound = true;
        Serial.printf("legato al badge %s\n", addr.c_str());
    }
}

static void saveBinding(const NimBLEAddress &addr) {
    prefs.putString("addr", addr.toString().c_str());
    prefs.putUChar("type", addr.getType());
    boundAddr = addr;
    bound = true;
    Serial.printf("nuovo legame con il badge %s\n", addr.toString().c_str());
}

static void clearBinding() {
    prefs.remove("addr");
    prefs.remove("type");
    bound = false;
    Serial.println("legame cancellato: il prossimo badge Presentator trovato verra' usato");
}

class ScanCallbacks : public NimBLEScanCallbacks {
    void onResult(const NimBLEAdvertisedDevice *dev) override {
        if (connectRequested || bleConnected) return;
        if (!dev->isAdvertisingService(SVC_UUID)) return;
        if (bound && !(dev->getAddress() == boundAddr)) return;
        targetAddr = dev->getAddress();
        connectRequested = true;
        NimBLEDevice::getScan()->stop();
    }
};

class ClientCallbacks : public NimBLEClientCallbacks {
    void onConnect(NimBLEClient *) override { Serial.println("BLE collegato"); }
    void onDisconnect(NimBLEClient *, int reason) override {
        bleConnected = false;
        statusChr = nullptr;
        session.attiva = false;
        rx.reset();
        Serial.printf("BLE scollegato (motivo %d)\n", reason);
    }
};

static ScanCallbacks scanCallbacks;
static ClientCallbacks clientCallbacks;

// Gira nel task di NimBLE: ricostruisce e verifica, l'esecuzione la fa loop().
static void onNotify(NimBLERemoteCharacteristic *, uint8_t *data, size_t len, bool) {
    int r = rx.aggiungi(data, len);
    if (r == proto::Ricevitore::SERVE_ALTRO) return;
    if (r != proto::Ricevitore::COMPLETO) {
        queueResult(rx.contatore(), (uint8_t)r);
        Serial.printf("messaggio scartato: 0x%02x\n", r);
        return;
    }
    proto::Messaggio m;
    uint8_t code = proto::verifica(session, rx.dati(), rx.dimensione(), m);
    if (code != proto::ESITO_FATTO) {
        queueResult(rx.contatore(), code);
        Serial.printf("messaggio rifiutato: 0x%02x\n", code);
        return;
    }
    if (m.tipo == proto::TIPO_ANNULLA) {
        abortRequested = true;
        queueResult(m.contatore, proto::ESITO_FATTO);
        return;
    }
    if (!proto::passiValidi(m.dati, m.len)) {
        queueResult(m.contatore, proto::ESITO_PASSO);
        return;
    }
    if (!usbReady()) {
        queueResult(m.contatore, proto::ESITO_USB);
        return;
    }
    bool accepted = false;
    portENTER_CRITICAL(&execMux);
    if (execState == EXEC_IDLE) {
        execState = EXEC_LOADING;  // loop() non la tocca finche' non e' PENDING
        accepted = true;
    }
    portEXIT_CRITICAL(&execMux);
    if (!accepted) {
        queueResult(m.contatore, proto::ESITO_OCCUPATO);
        return;
    }
    memcpy(execBuf, m.dati, m.len);
    execLen = m.len;
    execCounter = m.contatore;
    abortRequested = false;
    __sync_synchronize();
    execState = EXEC_PENDING;  // pubblicato dopo la copia
}

static void startScan() {
    NimBLEScan *scan = NimBLEDevice::getScan();
    if (!scan->isScanning()) {
        scan->start(0, false, true);  // scansione continua
    }
}

static bool writeStatus(const uint8_t *v, size_t len) {
    return statusChr != nullptr && statusChr->writeValue(v, len, true);
}

static void sendHello() {
    uint8_t v[14];
    v[0] = proto::ST_HELLO;
    v[1] = proto::VERSIONE;
    memcpy(v + 2, session.nonce, 8);
    memcpy(v + 10, fingerprint, 4);
    writeStatus(v, sizeof(v));
}

static void connectToBadge() {
    connectRequested = false;
    if (client == nullptr) {
        client = NimBLEDevice::createClient();
        client->setClientCallbacks(&clientCallbacks, false);
        client->setConnectTimeout(5000);
        // intervallo 15 ms, nessuna latenza, timeout supervisione 4 s
        client->setConnectionParams(12, 12, 0, 400);
    }
    Serial.printf("collegamento a %s...\n", targetAddr.toString().c_str());
    if (!client->connect(targetAddr)) {
        Serial.println("collegamento fallito");
        return;
    }
    NimBLERemoteService *svc = client->getService(SVC_UUID);
    NimBLERemoteCharacteristic *cmdChr = svc ? svc->getCharacteristic(CMD_UUID) : nullptr;
    NimBLERemoteCharacteristic *stChr = svc ? svc->getCharacteristic(STATUS_UUID) : nullptr;
    if (cmdChr == nullptr || stChr == nullptr || !cmdChr->canNotify()) {
        Serial.println("servizio Presentator non valido, scollego");
        client->disconnect();
        return;
    }
    // nuova sessione prima di ricevere qualunque notify
    rx.reset();
    esp_fill_random(session.nonce, sizeof(session.nonce));
    session.ultimoContatore = 0;
    session.attiva = true;
    if (!cmdChr->subscribe(true, onNotify)) {
        Serial.println("iscrizione alle notifiche fallita, scollego");
        client->disconnect();
        return;
    }
    statusChr = stChr;
    lastUsbSent = -1;
    bleConnected = true;
    if (!bound) saveBinding(targetAddr);
    sendHello();
    Serial.printf("sessione avviata, MTU %u\n", client->getMTU());
}

static void reportUsbStatus() {
    if (!bleConnected || statusChr == nullptr) return;
    int status = usbReady() ? 1 : 0;
    if (status == lastUsbSent) return;
    uint8_t v[2] = {proto::ST_USB, (uint8_t)status};
    if (writeStatus(v, sizeof(v))) {
        lastUsbSent = status;
    }
}

static void flushResults() {
    Result r;
    while (bleConnected && xQueueReceive(resultQueue, &r, 0) == pdTRUE) {
        uint8_t v[6] = {proto::ST_ESITO, (uint8_t)r.counter, (uint8_t)(r.counter >> 8),
                        (uint8_t)(r.counter >> 16), (uint8_t)(r.counter >> 24), r.code};
        writeStatus(v, sizeof(v));
    }
    if (!bleConnected) xQueueReset(resultQueue);
}

static void runPending() {
    if (execState != EXEC_PENDING) return;
    execState = EXEC_RUNNING;
    if (execLen > 40) {
        // solo per le macro lunghe: i comandi della presentazione restano immediati
        queueResult(execCounter, proto::ESITO_IN_CORSO);
        flushResults();
    }
    bool done = runMacro(execBuf, execLen);
    releaseAll();
    if (!done) Serial.println("macro interrotta");
    queueResult(execCounter, done ? proto::ESITO_FATTO : proto::ESITO_ANNULLATO);
    abortRequested = false;
    execState = EXEC_IDLE;
}

static void checkUnbindButton() {
    static uint32_t pressedSince = 0;
    if (digitalRead(UNBIND_PIN) == LOW) {
        if (pressedSince == 0) pressedSince = millis();
        if (millis() - pressedSince >= UNBIND_HOLD_MS) {
            pressedSince = 0;
            clearBinding();
            if (client && client->isConnected()) client->disconnect();
            for (int i = 0; i < 6; i++) { setLed(i % 2 == 0); delay(120); }
            while (digitalRead(UNBIND_PIN) == LOW) delay(10);
        }
    } else {
        pressedSince = 0;
    }
}

// --- setup/loop ---------------------------------------------------------------

void setup() {
    pinMode(UNBIND_PIN, INPUT_PULLUP);
#if defined(STATUS_LED_PIN)
    pinMode(STATUS_LED_PIN, OUTPUT);
#endif
    setLed(false);

    resultQueue = xQueueCreate(8, sizeof(Result));
    memcpy(session.chiave, PRESENTATOR_KEY, sizeof(session.chiave));
    session.attiva = false;
    uint8_t h[32];
    proto::sha256(session.chiave, sizeof(session.chiave), h);
    memcpy(fingerprint, h, sizeof(fingerprint));

    USB.onEvent(usbEvent);
    USB.productName("Presentator Dongle");
    USB.manufacturerName("tufty2350-apps");
    Keyboard.begin();
    Consumer.begin();
    USB.begin();
    Serial.begin(115200);

    prefs.begin("presentator", false);
    loadBinding();

    NimBLEDevice::init("Presentator Dongle");
    NimBLEDevice::setMTU(247);
    NimBLEScan *scan = NimBLEDevice::getScan();
    scan->setScanCallbacks(&scanCallbacks, false);
    scan->setActiveScan(true);   // il nome sta nella scan response
    scan->setInterval(100);
    scan->setWindow(80);
    startScan();
}

void loop() {
    static bool bannerShown = false;
    if (!bannerShown && millis() > 3000) {
        // stampato in ritardo per dare tempo di aprire il monitor seriale
        bannerShown = true;
        Serial.printf("Presentator dongle, protocollo v%u, HMAC self-test %s, impronta chiave %02x%02x%02x%02x\n",
                      proto::VERSIONE, proto::selfTest() ? "OK" : "FALLITO",
                      fingerprint[0], fingerprint[1], fingerprint[2], fingerprint[3]);
    }

    checkUnbindButton();

    if (connectRequested) {
        connectToBadge();
    }
    if (!bleConnected && !connectRequested) {
        startScan();
    }

    runPending();
    flushResults();
    reportUsbStatus();
    updateLed();
    delay(5);
}
