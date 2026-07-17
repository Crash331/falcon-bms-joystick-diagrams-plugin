# Falcon BMS parser plugin for Joystick Diagrams

Version 0.3.1 fixes upgrades from v0.2 in a running Joystick Diagrams session.
The application can otherwise retain v0.2 parser modules while validating the
new files, which caused a `BUTTON_LAYOUT_OPTIONS` import error in v0.3.0.

This community parser imports Falcon BMS DirectInput button, POV, shifted, and
analog-axis assignments, then exposes them as a Joystick Diagrams profile. It is
hardware-independent and can work with any DirectInput HOTAS represented in the
selected BMS configuration.

## Install

1. Download `falcon_bms_plugin.zip` from the
   [latest GitHub release](https://github.com/Crash331/falcon-bms-joystick-diagrams-plugin/releases/latest).
2. In Joystick Diagrams, open **Settings → Parser Plugins** and install the ZIP.
3. Enable **Falcon BMS**, open its setup panel, and select the active `.key`
   file.
4. Select any optional display settings, then run the plugin.
5. Assign the appropriate hardware template to each discovered device.

Restart Joystick Diagrams after replacing an older plugin version so the new
Python code and settings model are loaded.

## Version 0.3 settings

| Setting | Default | Purpose |
|---|---|---|
| **Falcon BMS Key File** | Not set | Required active `.key` profile. |
| **Show DX Button Numbers** | Off | Prefixes button labels, for example `DX53 — Weapon Release`. |
| **Show Axis Identifiers** | Off | Prefixes axis labels, for example `AXIS_RY — Throttle`. |
| **Show POV Identifiers** | Off | Prefixes hat labels, for example `POV 1 Up — Trim Nose Up`. |
| **Button Layout** | Auto | Auto reads `g_nButtonsPerDevice`; `128` and `32` are manual overrides. |
| **BMS Config Folder (Optional)** | Blank | Supplies BMS cfg, `DeviceSorting.txt`, and `Setup.v*.xml` files when they are not beside the selected key file. |

When the optional config folder is blank, the plugin uses the selected key
file's folder. If a folder was previously chosen and the app does not offer a
clear button, select the key file's own folder to restore the same behavior.

The three identifier options only change the text written to the diagram. They
do not affect which template field receives a binding. Re-run plugins after
changing an option.

## What is imported

- Active DirectInput button rows (`-2`), translated from BMS's zero-based,
  global button IDs to one-based physical button IDs.
- POV rows (`-3`) and all eight directions.
- BMS DX-shifted button and POV layers as Joystick Diagrams modifiers.
- Press/release pairs, combined on the same physical control.
- Human-readable action labels from callback definitions in the key file.
- Analog axis assignments from Alternative Launcher's per-device
  `Setup.v*.xml` files, matched to active devices through
  `DeviceSorting.txt`.
- Stable, deterministic device UUIDs, because `.key` files do not contain USB
  device GUIDs.

Keyboard shortcuts are intentionally excluded. Falcon BMS does not store analog
axis assignments in the `.key` file, and its `axismapping.dat` is binary, so
axis import requires the Alternative Launcher setup XML files.

## Button layouts and DX shift

In **Auto** mode, the plugin reads `g_nButtonsPerDevice` from
`falcon bms.cfg` and then applies any override in `Falcon BMS User.cfg`.
Values from 32 through 128 are accepted. If the setting is absent or invalid,
Auto falls back to BMS's legacy default of 32. Choose the explicit 32 or 128
option only when automatic detection does not match a legacy or hand-edited setup.

DX-shifted bindings use the separate `g_nHotasPinkyShiftMagnitude` setting.
If it is absent, the BMS default of 256 is used. POV shifting continues to use
BMS's separate two-POV offset.

## Version 0.2 backup

The exact v0.2.0 package is preserved both in
[`dist/archive/v0.2.0/falcon_bms_plugin.zip`](dist/archive/v0.2.0/falcon_bms_plugin.zip)
and in the
[v0.2.0 GitHub release](https://github.com/Crash331/falcon-bms-joystick-diagrams-plugin/releases/tag/v0.2.0).

SHA-256:

```text
CFAD5E4C516B3279173F3FDFA70483C73D6483D6AD4D0FCC762DE88B02734514
```

## Development and verification

The plugin targets the Joystick Diagrams 2.2 parser API and uses only Python's
standard library plus packages already supplied by Joystick Diagrams.

Run the tests with a Joystick Diagrams checkout on `PYTHONPATH`:

```powershell
$env:PYTHONPATH = "C:\path\to\joystick-diagrams"
python -m unittest discover -v
```

The installable ZIP contains exactly one top-level directory named
`falcon_bms_plugin`, matching the Joystick Diagrams installer contract. The
archive also includes the GPL-2.0 license.

## License

This project is licensed under the [GNU General Public License v2.0](LICENSE).
