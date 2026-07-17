from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from falcon_bms_plugin.bms_key_parser import BMSKeyParser


class BMSAxisParserTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.config_dir = Path(self.temp_dir.name)
        self.key_file = self.config_dir / "Pilot.key"
        self.key_file.write_text("", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_imports_axes_from_active_alternative_launcher_profiles(self):
        throttle_name = (
            "WINCTRL Orion Throttle Base II F15EX HANDLE L F15EX HANDLE R"
        )
        stick_name = "WINCTRL Orion Joystick Base Metal 2 JGRIP-F16"
        self.config_dir.joinpath("DeviceSorting.txt").write_text(
            '{11111111-1111-1111-1111-111111111111} "'
            f'{throttle_name}"\n'
            '{22222222-2222-2222-2222-222222222222} "'
            f'{stick_name}"\n',
            encoding="utf-8",
        )
        self._write_setup_profile(
            self.config_dir,
            throttle_name,
            "11111111-1111-1111-1111-111111111111",
            [
                "Cursor_X",
                "Cursor_Y",
                "",
                "",
                "Throttle",
                "Range_Knob",
                "",
                "Radar_Antenna_Elevation",
            ],
        )
        self._write_setup_profile(
            self.config_dir,
            stick_name,
            "22222222-2222-2222-2222-222222222222",
            ["Roll", "Pitch", "", "Yaw", "", "", "", ""],
        )
        self._write_setup_profile(
            self.config_dir,
            "Disconnected Controller",
            "33333333-3333-3333-3333-333333333333",
            ["Yaw", "", "", "", "", "", "", ""],
        )

        collection = BMSKeyParser(self.key_file).process_profiles()
        profile = collection.get_profile("Pilot")
        self.assertIsNotNone(profile)
        self.assertEqual(2, len(profile.devices))

        throttle = self._device(profile, throttle_name)
        stick = self._device(profile, stick_name)

        self.assertEqual("Radar Cursor X", throttle.inputs["axis"]["AXIS_X"].command)
        self.assertEqual("Radar Cursor Y", throttle.inputs["axis"]["AXIS_Y"].command)
        self.assertEqual("Throttle", throttle.inputs["axis"]["AXIS_RY"].command)
        self.assertEqual("Roll", stick.inputs["axis"]["AXIS_X"].command)
        self.assertEqual("Pitch", stick.inputs["axis"]["AXIS_Y"].command)
        self.assertEqual(
            "Radar Antenna Elevation",
            throttle.inputs["axis_slider"]["AXIS_SLIDER_2"].command,
        )

    def test_axis_identifier_option_prefixes_axes_and_sliders(self):
        device_name = "Test Throttle"
        self.config_dir.joinpath("DeviceSorting.txt").write_text(
            f'{{11111111-1111-1111-1111-111111111111}} "{device_name}"\n',
            encoding="utf-8",
        )
        self._write_setup_profile(
            self.config_dir,
            device_name,
            "11111111-1111-1111-1111-111111111111",
            [
                "Cursor_X",
                "",
                "",
                "",
                "Throttle",
                "",
                "",
                "Radar_Antenna_Elevation",
            ],
        )

        profile = BMSKeyParser(
            self.key_file, show_axis_identifiers=True
        ).process_profiles().get_profile("Pilot")
        self.assertIsNotNone(profile)
        device = self._device(profile, device_name)
        self.assertEqual(
            "AXIS_X — Radar Cursor X",
            device.inputs["axis"]["AXIS_X"].command,
        )
        self.assertEqual(
            "AXIS_RY — Throttle",
            device.inputs["axis"]["AXIS_RY"].command,
        )
        self.assertEqual(
            "AXIS_SLIDER_2 — Radar Antenna Elevation",
            device.inputs["axis_slider"]["AXIS_SLIDER_2"].command,
        )

    def test_optional_config_folder_controls_layout_and_axes(self):
        profiles_dir = self.config_dir / "profiles"
        external_dir = self.config_dir / "external-config"
        profiles_dir.mkdir()
        external_dir.mkdir()
        key_file = profiles_dir / "Portable.key"
        key_file.write_text(
            '#======== Test Device ========\n'
            'Action 160 -1 -2 0 0x0 0 "Mapped Action"\n',
            encoding="utf-8",
        )

        self._write_input_config(profiles_dir, 32)
        self._write_input_config(external_dir, 128)
        for config_dir, assignment in (
            (profiles_dir, "Roll"),
            (external_dir, "Pitch"),
        ):
            config_dir.joinpath("DeviceSorting.txt").write_text(
                '{11111111-1111-1111-1111-111111111111} "Test Device"\n',
                encoding="utf-8",
            )
            self._write_setup_profile(
                config_dir,
                "Test Device",
                "11111111-1111-1111-1111-111111111111",
                [assignment, "", "", "", "", "", "", ""],
            )

        local_profile = BMSKeyParser(
            key_file, show_axis_identifiers=True
        ).process_profiles().get_profile("Portable")
        self.assertIsNotNone(local_profile)
        local_device = self._device(local_profile, "Test Device")
        self.assertIn("BUTTON_1", local_device.inputs["buttons"])
        self.assertEqual(
            "AXIS_X — Roll",
            local_device.inputs["axis"]["AXIS_X"].command,
        )

        external_profile = BMSKeyParser(
            key_file,
            config_dir=external_dir,
            show_axis_identifiers=True,
        ).process_profiles().get_profile("Portable")
        self.assertIsNotNone(external_profile)
        external_device = self._device(external_profile, "Test Device")
        self.assertIn("BUTTON_33", external_device.inputs["buttons"])
        self.assertEqual(
            "AXIS_X — Pitch",
            external_device.inputs["axis"]["AXIS_X"].command,
        )

    @staticmethod
    def _write_input_config(config_dir, buttons_per_device):
        config_dir.joinpath("Falcon BMS User.cfg").write_text(
            f"set g_nButtonsPerDevice {buttons_per_device}\n"
            "set g_nHotasPinkyShiftMagnitude 2048\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_setup_profile(config_dir, name, guid, assignments):
        axes = "".join(
            f"<AxAssgn><AxisName>{assignment}</AxisName></AxAssgn>"
            for assignment in assignments
        )
        path = config_dir / f"Setup.v100.{name} {{{guid}}}.xml"
        path.write_text(
            f"<JoyAssgn><axis>{axes}</axis></JoyAssgn>", encoding="utf-8"
        )

    @staticmethod
    def _device(profile, name):
        return next(
            device for device in profile.devices.values() if device.name == name
        )


if __name__ == "__main__":
    unittest.main()
