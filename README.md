# Falcon BMS parser plugin for Joystick Diagrams

This parser imports Falcon BMS DirectInput button and POV assignments from a
`.key` file and exposes them as a Joystick Diagrams profile.

## Install

1. Open Joystick Diagrams and go to its parser plugins page.
2. Install `dist/falcon_bms_plugin.zip` (or select the `falcon_bms_plugin`
   folder when developing locally).
3. Configure **Falcon BMS Key File** and select the active file from
   `Falcon BMS 4.38\User\Config`.
4. Run the parser, then assign the appropriate hardware template to each
   discovered device.

## What is imported

- Active DirectInput button rows (`-2`), translated from BMS's zero-based,
  global button IDs to one-based physical button IDs.
- POV rows (`-3`) and all eight directions.
- BMS DX-shifted button/POV layers as Joystick Diagrams modifiers.
- Press/release pairs, combined on the same physical control.
- Human-readable action labels from the callback definitions earlier in the
  same key file.
- Device names from Alternative Launcher hardware section headers. Stable,
  deterministic UUIDs are generated because `.key` files do not contain USB
  device GUIDs.

Keyboard shortcuts and analog axes are intentionally excluded. Falcon BMS does
not store analog axis assignments in the `.key` file.

The button calculation follows Falcon BMS 4.38's 16-device layout (128 buttons
per device, 2,048 global button IDs per shift layer). BMS stores button IDs
zero-based, while Joystick Diagrams templates label them one-based.

## Development and verification

The plugin targets the Joystick Diagrams 2.2 parser API and uses only Python's
standard library plus packages already supplied by Joystick Diagrams.

Run the tests with a Joystick Diagrams checkout on `PYTHONPATH`:

```powershell
$env:PYTHONPATH = "C:\path\to\joystick-diagrams"
python -m unittest discover -v
```

The installable ZIP must contain exactly one top-level directory named
`falcon_bms_plugin`, matching Joystick Diagrams' plugin installer contract.

## License

This project is licensed under the [GNU General Public License v2.0](LICENSE).
