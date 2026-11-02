# Presentator dongle case

Two-piece case for an ESP32-S3 Supermini **without soldered headers**.
Outside size: 21.7 × 25.4 × 7.1 mm.

| File | Contents |
|---|---|
| `case_presentator.py` | parametric model (FreeCAD 1.0), with all dimensions at the top |
| `base.stl` | bottom, already oriented for printing |
| `lid.stl` | lid, upside down for printing (outer face on the bed) |
| `case.step` | assembly, for FreeCAD or any other CAD |
| `preview/*.png` | cross-sections through BOOT, the USB axis and the buttons; top view of the lid |

To regenerate after changing the dimensions:

    freecadcmd case_presentator.py

On Windows, `freecadcmd` is usually `C:\Program Files\FreeCAD 1.0\bin\freecadcmd.exe`.

The script checks for collisions against a dummy board and measures the clearance between the
pins and the buttons. If a check fails, it prints `ESITO: PROBLEMI` ("result: problems").

## How it works

- **Base:**
  - the board lies flat on the floor, which takes the force when the buttons are pressed;
  - four through-holes make room for the soldered tabs of the USB-C connector, which stick
    out under the PCB;
  - the USB edge of the PCB rests against the front wall, and the connector ends flush with
    the outside, so the cable plugs all the way in.
- **Lid:**
  - two lips on the long sides press on the pad strip and hold the board without touching
    any component;
  - two small hooks snap into the base;
  - to open the case, lever it at the notch on the back.
- **Buttons:**
  - BOOT and RST are pressed through two flexible tabs cut into the lid, each with a pin
    underneath;
  - at rest the pin sits 0.35 mm above the button (`NUB_GAP`). Never set this gap to zero:
    a button pressed all the time keeps the dongle stuck in reset or in download mode.
- **LED:** a hole above the RGB LED shows the status. Blinking means searching, steady means
  connected.
- **Antenna:** the end opposite the USB connector is plastic only.

## Printing (tested: Anet A8, Cura, PLA)

- 0.4 mm nozzle, 0.2 mm layers, 100% infill (the parts are tiny).
- No supports: both parts are already oriented.
- The lid prints with its outer face on the bed, so the slots, recesses and labels are all on
  the first layer.
  - In Cura, set "Initial Layer Horizontal Expansion" to about -0.1/-0.15 mm. Otherwise
    elephant's foot fuses the tabs to the lid.
- Print **only the lid** first, and check that the 0.7 mm slots around the tabs are open. If
  they closed up, open them with a craft knife or increase `SLOT`.
- The 2.6 mm labels have strokes as wide as the nozzle and can blur. If they come out
  unreadable, remove them with `LABEL_DEPTH = 0`.
- If the lid is too tight or too loose, adjust `LIP_FIT` (clearance) and `SNAP` (hooks).

## Testing after assembly

1. Close the lid and plug in the USB cable. The PC must show an HID keyboard and the dongle's
   serial port.

   If it shows "USB JTAG/serial debug unit" or nothing at all, a pin is pressing BOOT or
   RST: increase `BTN_H` or `NUB_GAP`.
2. Hold BOOT through its tab and press RST once. "USB JTAG/serial debug unit" must appear
   (upload mode).
3. Press RST once on its own. The HID keyboard must come back.

Do not use the 3-second BOOT hold as a test: it erases the bond with the badge.

## Dimensions to check with calipers

Measured with calipers on the board used here: `PCB_L` 23.6, `PCB_W` 18, `PCB_T` 1.16,
`USB_OVERHANG` 1.6, `BOOT_X` 4.75, `BTN_H` 1.5 mm.

These are still estimates, taken from the scale drawing on espboards.dev. Check them if the
test fails:

- `BTN_Y` (8.7): distance from the USB edge to the button centres;
- `RST_X`: assumed symmetric to BOOT (18 - 4.75 = 13.25);
- `USB_H` (3.26): height of the USB connector above the PCB (standard value).

Supermini boards are cloned by many makers, and dimensions vary. Measure your board before
reusing the case.
