# WiFi on the Tufty 2350: the `wifi_config` app

Quick reference for how the badge's WiFi networks are managed. The on-screen texts are in
Italian; English translations are given in brackets.

## In short

- **`wifi_config` is the only network manager.** It does four things:
  - tries the known networks;
  - lets you switch network;
  - adds a new network (scan + virtual keyboard);
  - deletes a network or re-imports the list.
- **The other apps** connect only through `secrets.py` (`wifi.connect()` with no arguments).
  `wifi_config` keeps that file in sync with the last network that worked.
- **`claude_monitor`** never reboots the badge when it cannot connect. Instead it shows
  "Usa Wifi Config per gestire le reti WiFi" ("use WiFi Config to manage WiFi networks").

## Files

| File | Role |
|---|---|
| `apps/wifi_config/__init__.py` | the app: state machine for the screens |
| `apps/wifi_config/reti.py` | known-network list, import, backup, `secrets.py` |
| `apps/wifi_config/rete.py` | connect and scan using `network.WLAN` directly |
| `apps/wifi_config/tastiera.py` | grid virtual keyboard, plus key repeat when a button is held |
| `apps/wifi_config/ui.py` | colours and UI pieces (same palette as `claude_monitor`) |
| `apps/claude_monitor/collegamento.py` | `claude_monitor`'s connection logic, without `fatal_error()` |
| `dev_checks/check_wifi_config.py` | desktop tests of the logic (39) |
| `dev_checks/simulatore_wifi/` | screen tests in the simulator (`prova_wifi_config.py`, fake network in `sim_network.py`) |

## The badge's two volumes

| Volume | Filesystem | Written by | Notes |
|---|---|---|---|
| `/system` | FAT, 12 MB | **the PC** in Disk Mode (USB drive) | read-only for code running on the badge |
| `/` | LittleFS, 1 MB | **code** on the badge | not visible in Disk Mode |

| File | Where | Contents |
|---|---|---|
| `/multi_secrets.py` | `/` | **single source of truth**: `NETWORKS = [{"ssid", "password"}, ...]`. The last successful network is first; open networks have password `""`. |
| `/multi_secrets.py.bak` | `/` | previous valid version, written before every change |
| `/secrets.py` | `/` | keys from the drive's `secrets.py` (REGION, TIMEZONE...) plus `WIFI_SSID`/`WIFI_PASSWORD` of the network in use |
| `<drive>/multi_secrets.py` | `/system` | **initial list only**: imported the first time, or with "Reimporta" (re-import) |
| `<drive>/secrets.py` | `/system` | REGION, TIMEZONE... (always read) and, at the start, the first network |

The firmware's `secrets` module reads `/secrets.py` first, then `/system/secrets.py`.

`multi_secrets.py` on the drive has the same format as the root copy:

```python
NETWORKS = [
    {"ssid": "HomeNetwork", "password": "home-password"},
    {"ssid": "PhoneHotspot", "password": "hotspot-password"},
]
```

## How the app works

1. **Notice.** While `<drive>/multi_secrets.py` exists, the app says it is no longer used and
   can be deleted. After the first import it also shows how many networks were imported.
2. **Try the known networks** in order: 8 s per network, a single `connect()` call each.
3. **Success.** A "connected to X / IP" menu appears with: change network, add network,
   delete network, re-import from `multi_secrets`.
4. **All networks failed.** The app asks whether to add a new network. The choices are:
   - scan;
   - manage the known networks (the same menu, in its "not connected" version);
   - no.

**Add network:**
- The scan shows each network with its signal strength (4 bars), a star if it is already
  known, and "aperta" (open) or a padlock.
- **Open network:** the badge connects at once.
- **Known network:** the keyboard opens with the saved password already typed in.
- **Any other network:** the keyboard opens empty.
- The badge then tries to connect for 15 s:
  - **Success:** the network goes to the top of the list and into `secrets.py`.
  - **Failure:** you are back on the keyboard with the password still typed, and the reason:
    wrong password, network not found, or connection failed.
- If you were connected to another network and leave without success, the badge reconnects
  to it.

**Keyboard:**
- The grid has 7 rows: lowercase, uppercase, digits and symbols. A last row has space,
  `\`, `|`, `` ` ``, Canc (delete), OK and Annulla (cancel).
- **A/C** move left/right, **UP/DOWN** change row, **B** types the selected key. Holding a
  button repeats it.
- The password is shown in clear and must be 8 to 63 characters long.

**Delete network:**
- You must confirm.
- If you delete the network in use, the badge tries the others. If none works, `secrets.py`
  is **cleared**, so a deleted network cannot stay usable.

## Recipes

- **First setup:** put your networks in `<drive>/multi_secrets.py` (or a single network in
  `<drive>/secrets.py`) and open WiFi Config: they are imported. Then delete
  `<drive>/multi_secrets.py`.
- **New network while away:** WiFi Config → add network (or the scan offered after a failure).
- **Changed password:** add network → pick the network (it has a star) → fix the password → OK.
- **Start again from the drive file:**
  1. Put `<drive>/multi_secrets.py` back.
  2. Choose re-import. It replaces the badge's list, after you confirm.
- **REGION/TIMEZONE:** change them in `<drive>/secrets.py`. They are picked up at the next
  successful connection.
- **Damaged list:** the badge tries the `.bak` copy. If that cannot be read either, the badge
  shows a "damaged list" message and leaves the file alone until you add a network or
  re-import.

## Why `network.WLAN` directly (and not `wifi.connect()`)

The firmware's `wifi.py` has a retry problem. Once `wifi.wlan` exists, every later
`wifi.connect()` call advances some internal retry counters. When they run out, it calls
`fatal_error()`, which **reboots the badge**. It also offers no scan function. So:

- `wifi_config` uses `network.WLAN(network.STA_IF)`, with a single `connect()` per attempt and
  its own timeout;
- `claude_monitor` calls `wifi.connect()` **once** per attempt, always after
  `wifi.disconnect()`, then reads `is_connected()` / `wlan.status()`. If the network drops,
  it retries once, then shows the "use WiFi Config" message.

CYW43 status codes:
- `3`: connected;
- `-3`: wrong password. This is not always reliable: sometimes only a timeout arrives;
- `-2`: network not found;
- `-1`: failed.

## Tests

```sh
python dev_checks/check_wifi_config.py        # OK (39 tests)
# simulator (Playwright)
PYTHONIOENCODING=utf-8 python dev_checks/simulatore_wifi/prova_wifi_config.py <output_dir> [scenario ...]
```

Simulator scenarios: `avvio_ok`, `password`, `corta_annulla`, `aperta`, `nota_salvata`,
`gestisci_no`, `avviso`, `danneggiato`, `vuoto`, `monitor`.

The simulator has no real network, so confirm real WiFi behaviour (timings, error codes) on
the badge.

## Installing on the badge

In Disk Mode:
- copy `apps/wifi_config/*.py` and `icon.png` to `<drive>\apps\wifi_config\`;
- copy `apps/claude_monitor/` to `<drive>\apps\claude_monitor\`.

## Known limits

- HOME reboots the badge (it is a hardware interrupt). While a connection attempt is running,
  there is no other way to cancel it.
- Hidden networks and WPA-Enterprise are not supported.
- Passwords are stored in clear in the files, which is normal for Badgeware. Anyone who mounts
  the badge can read them.
- The network scan freezes the screen for a couple of seconds; a spinner is shown first.
