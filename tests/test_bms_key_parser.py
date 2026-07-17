from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from falcon_bms_plugin.bms_key_parser import BMSKeyParser


SAMPLE_KEY = """
SimCanopyOpen 115 0 0x10 4 0 0 1 "LEFT WALL: CANOPY - Open"
SimCanopyClose 115 0 0x11 4 0 0 1 "LEFT WALL: CANOPY - Close"
SimTrimUp -1 0 0XFFFFFFFF 0 0 0 1 "STICK: TRIM - Nose Up"
SimTrimRight -1 0 0XFFFFFFFF 0 0 0 1 "STICK: TRIM - Right Wing Down"
SimTMSUp -1 0 0XFFFFFFFF 0 0 0 1 "STICK: TMS Up"
SimTMSRight -1 0 0XFFFFFFFF 0 0 0 1 "STICK: TMS Right"
SimTMSDown -1 0 0XFFFFFFFF 0 0 0 1 "STICK: TMS Down"
SimTMSLeft -1 0 0XFFFFFFFF 0 0 0 1 "STICK: TMS Left"
#======== WINCTRL Orion Throttle Base II ========
SimCanopyOpen 68 -1 -2 0 0x0 115
SimCanopyClose 70 -2 -2 0 0x0 115
SimCanopyClose 70 -2 -2 0x42 0x0 115
# SimIgnored 71 -1 -2 0 0x0 0
SimDoNothing 72 -1 -2 0 0x0 0
#======== WINCTRL Orion Joystick Base Metal 2 ========
SimTMSUp 159 -1 -2 0 0x0 -1
SimTMSRight 160 -1 -2 0 0x0 -1
SimTMSDown 161 -1 -2 0 0x0 -1
SimTMSLeft 162 -1 -2 0 0x0 -1
#======== WINCTRL Orion Joystick Base Metal 2 : POV #0 ========
SimTrimUp 0 -1 -3 0 0x0 0
SimTrimRight 0 -1 -3 2 0x0 0
SimTrimUp 2 -1 -3 0 0x0 0
"""


class BMSKeyParserTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.config_dir = Path(self.temp_dir.name)
        self.key_file = self.config_dir / "Pilot.key"
        self.key_file.write_text(SAMPLE_KEY, encoding="utf-8")
        self.config_dir.joinpath("Falcon BMS User.cfg").write_text(
            "set g_nButtonsPerDevice 128\n"
            "set g_nHotasPinkyShiftMagnitude 256\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parses_buttons_labels_events_and_povs(self):
        bindings = BMSKeyParser(self.key_file).parse()

        self.assertEqual(10, len(bindings))
        self.assertEqual("WINCTRL Orion Throttle Base II", bindings[0].device_name)
        self.assertEqual(69, bindings[0].control_id)
        self.assertEqual("LEFT WALL: CANOPY - Open", bindings[0].action)
        self.assertEqual("press", bindings[1].event)
        self.assertEqual("release", bindings[2].event)

        tms = bindings[3:7]
        self.assertEqual([32, 33, 34, 35], [binding.control_id for binding in tms])

        pov = bindings[7:]
        self.assertEqual([1, 1, 1], [binding.control_id for binding in pov])
        self.assertEqual([0, 0, 1], [binding.layer for binding in pov])
        self.assertEqual(["U", "R", "U"], [binding.direction.name for binding in pov])

    def test_builds_a_profile_collection_with_default_labels(self):
        collection = BMSKeyParser(self.key_file).process_profiles()

        self.assertEqual(1, len(collection))
        profile = collection.get_profile("Pilot")
        self.assertIsNotNone(profile)
        self.assertEqual(2, len(profile.devices))

        throttle = self._device(profile, "WINCTRL Orion Throttle Base II")
        self.assertEqual(
            "LEFT WALL: CANOPY - Open",
            throttle.inputs["buttons"]["BUTTON_69"].command,
        )
        self.assertEqual(
            "LEFT WALL: CANOPY - Close (press) | "
            "LEFT WALL: CANOPY - Close (release)",
            throttle.inputs["buttons"]["BUTTON_71"].command,
        )

        stick = self._device(profile, "WINCTRL Orion Joystick Base Metal 2")
        self.assertEqual(
            ["BUTTON_32", "BUTTON_33", "BUTTON_34", "BUTTON_35"],
            list(stick.inputs["buttons"]),
        )
        up = stick.inputs["hats"]["POV_1_U"]
        self.assertEqual("STICK: TRIM - Nose Up", up.command)
        self.assertEqual(1, len(up.modifiers))
        self.assertEqual({"BMS DX Shift"}, up.modifiers[0].modifiers)

    def test_auto_layout_reads_cfg_and_user_cfg_overrides_base(self):
        self.config_dir.joinpath("falcon bms.cfg").write_text(
            "set g_nButtonsPerDevice 128\n"
            "set g_nHotasPinkyShiftMagnitude 2048\n",
            encoding="utf-8",
        )
        self.config_dir.joinpath("Falcon BMS User.cfg").write_text(
            "// set g_nButtonsPerDevice 128\n"
            "set g_nButtonsPerDevice 32 // LAUNCHER OVERRIDE\n",
            encoding="utf-8",
        )

        parser = BMSKeyParser(self.key_file)
        self.assertEqual(32, parser.resolve_buttons_per_device())
        tms = parser.parse()[3:7]
        self.assertEqual([32, 1, 2, 3], [binding.control_id for binding in tms])

    def test_manual_layout_overrides_cfg_and_auto_uses_bms_default(self):
        self.config_dir.joinpath("Falcon BMS User.cfg").write_text(
            "set g_nButtonsPerDevice 32\n"
            "set g_nHotasPinkyShiftMagnitude 2048\n",
            encoding="utf-8",
        )

        forced = BMSKeyParser(self.key_file, button_layout="128")
        self.assertEqual(128, forced.resolve_buttons_per_device())
        self.assertEqual(
            [32, 33, 34, 35],
            [binding.control_id for binding in forced.parse()[3:7]],
        )

        self.config_dir.joinpath("Falcon BMS User.cfg").unlink()
        fallback = BMSKeyParser(self.key_file, button_layout="Unknown old value")
        self.assertEqual(32, fallback.resolve_buttons_per_device())

        self.config_dir.joinpath("Falcon BMS User.cfg").write_text(
            "set g_nButtonsPerDevice 999\n",
            encoding="utf-8",
        )
        self.assertEqual(32, BMSKeyParser(self.key_file).resolve_buttons_per_device())

    def test_shift_magnitude_is_independent_of_button_layout(self):
        self.config_dir.joinpath("Falcon BMS User.cfg").write_text(
            "set g_nButtonsPerDevice 128\n"
            "set g_nHotasPinkyShiftMagnitude 256\n",
            encoding="utf-8",
        )
        self._write_device_sorting("Device A", "Device B")
        self.key_file.write_text(
            """
#======== Device A ========
BaseA 31 -1 -2 0 0x0 0 "Base A"
ShiftA 287 -1 -2 0 0x0 0 "Shift A"
#======== Device B ========
BaseB 159 -1 -2 0 0x0 0 "Base B"
ShiftB 415 -1 -2 0 0x0 0 "Shift B"
""",
            encoding="utf-8",
        )

        parser = BMSKeyParser(self.key_file, show_dx_button_numbers=True)
        bindings = parser.parse()
        self.assertEqual([32] * 4, [binding.control_id for binding in bindings])
        self.assertEqual([0, 1, 0, 1], [binding.layer for binding in bindings])

        profile = parser.process_profiles().get_profile("Pilot")
        self.assertIsNotNone(profile)
        devices = (("Device A", "Base A"), ("Device B", "Base B"))
        for device_name, base_action in devices:
            input_ = self._device(profile, device_name).inputs["buttons"]["BUTTON_32"]
            self.assertEqual(f"DX32 — {base_action}", input_.command)
            self.assertEqual(1, len(input_.modifiers))
            self.assertEqual({"BMS DX Shift"}, input_.modifiers[0].modifiers)
            self.assertTrue(input_.modifiers[0].command.startswith("DX32 — "))

    def test_device_header_disambiguates_overlapping_shift_and_base_ids(self):
        self.config_dir.joinpath("Falcon BMS User.cfg").write_text(
            "set g_nButtonsPerDevice 128\n"
            "set g_nHotasPinkyShiftMagnitude 128\n",
            encoding="utf-8",
        )
        self._write_device_sorting("Device A", "Device B")
        self.key_file.write_text(
            """
#======== Device A ========
BaseA 31 -1 -2 0 0x0 0 "Base A"
ShiftA 159 -1 -2 0 0x0 0 "Shift A"
#======== Device B ========
BaseB 159 -1 -2 0 0x0 0 "Base B"
ShiftB 287 -1 -2 0 0x0 0 "Shift B"
""",
            encoding="utf-8",
        )

        bindings = BMSKeyParser(self.key_file).parse()
        self.assertEqual([32, 32, 32, 32], [item.control_id for item in bindings])
        self.assertEqual([0, 1, 0, 1], [item.layer for item in bindings])

    def test_identifier_options_prefix_once_and_are_type_specific(self):
        parser = BMSKeyParser(
            self.key_file,
            show_dx_button_numbers=True,
            show_pov_identifiers=True,
        )
        profile = parser.process_profiles().get_profile("Pilot")
        self.assertIsNotNone(profile)

        throttle = self._device(profile, "WINCTRL Orion Throttle Base II")
        grouped = throttle.inputs["buttons"]["BUTTON_71"].command
        self.assertEqual(
            "DX71 — LEFT WALL: CANOPY - Close (press) | "
            "LEFT WALL: CANOPY - Close (release)",
            grouped,
        )
        self.assertEqual(1, grouped.count("DX71"))

        stick = self._device(profile, "WINCTRL Orion Joystick Base Metal 2")
        self.assertEqual(
            "DX32 — STICK: TMS Up",
            stick.inputs["buttons"]["BUTTON_32"].command,
        )
        self.assertEqual(
            "POV 1 Up — STICK: TRIM - Nose Up",
            stick.inputs["hats"]["POV_1_U"].command,
        )

    def test_all_pov_direction_identifiers(self):
        directions = [
            "Up",
            "Up Right",
            "Right",
            "Down Right",
            "Down",
            "Down Left",
            "Left",
            "Up Left",
        ]
        rows = "\n".join(
            f'Action{index} 0 -1 -3 {index} 0x0 0 "Action {index}"'
            for index in range(8)
        )
        self.key_file.write_text(
            f"#======== Hat Device : POV #0 ========\n{rows}\n",
            encoding="utf-8",
        )

        profile = BMSKeyParser(
            self.key_file, show_pov_identifiers=True
        ).process_profiles().get_profile("Pilot")
        self.assertIsNotNone(profile)
        device = self._device(profile, "Hat Device")
        for direction_key, direction_name, index in zip(
            ("U", "UR", "R", "DR", "D", "DL", "L", "UL"),
            directions,
            range(8),
        ):
            self.assertEqual(
                f"POV 1 {direction_name} — Action {index}",
                device.inputs["hats"][f"POV_1_{direction_key}"].command,
            )

    def test_device_guid_is_stable_and_case_insensitive(self):
        first = BMSKeyParser.device_guid("WINCTRL Orion Throttle")
        second = BMSKeyParser.device_guid("winctrl orion throttle")
        self.assertEqual(first, second)

    def _write_device_sorting(self, *device_names):
        rows = ["# Active DirectInput devices", ""]
        for index, name in enumerate(device_names, start=1):
            guid = f"{index:08d}-1111-1111-1111-111111111111"
            rows.append(f'{{{guid}}} "{name}"')
        self.config_dir.joinpath("DeviceSorting.txt").write_text(
            "\n".join(rows) + "\n", encoding="utf-8"
        )

    @staticmethod
    def _device(profile, name):
        return next(
            device for device in profile.devices.values() if device.name == name
        )


if __name__ == "__main__":
    unittest.main()
