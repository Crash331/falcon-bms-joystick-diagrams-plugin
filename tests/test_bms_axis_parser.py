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
            stick_name,
            "22222222-2222-2222-2222-222222222222",
            ["Roll", "Pitch", "", "Yaw", "", "", "", ""],
        )
        self._write_setup_profile(
            "Disconnected Controller",
            "33333333-3333-3333-3333-333333333333",
            ["Yaw", "", "", "", "", "", "", ""],
        )

        collection = BMSKeyParser(self.key_file).process_profiles()
        profile = collection.get_profile("Pilot")
        self.assertIsNotNone(profile)
        self.assertEqual(2, len(profile.devices))

        throttle = next(
            device
            for device in profile.devices.values()
            if device.name == throttle_name
        )
        stick = next(
            device for device in profile.devices.values() if device.name == stick_name
        )

        self.assertEqual("Radar Cursor X", throttle.inputs["axis"]["AXIS_X"].command)
        self.assertEqual("Radar Cursor Y", throttle.inputs["axis"]["AXIS_Y"].command)
        self.assertEqual("Throttle", throttle.inputs["axis"]["AXIS_RY"].command)
        self.assertEqual("Roll", stick.inputs["axis"]["AXIS_X"].command)
        self.assertEqual("Pitch", stick.inputs["axis"]["AXIS_Y"].command)
        self.assertEqual(
            "Radar Antenna Elevation",
            throttle.inputs["axis_slider"]["AXIS_SLIDER_2"].command,
        )

    def _write_setup_profile(self, name, guid, assignments):
        axes = "".join(
            f"<AxAssgn><AxisName>{assignment}</AxisName></AxAssgn>"
            for assignment in assignments
        )
        path = self.config_dir / f"Setup.v100.{name} {{{guid}}}.xml"
        path.write_text(
            f"<JoyAssgn><axis>{axes}</axis></JoyAssgn>", encoding="utf-8"
        )


if __name__ == "__main__":
    unittest.main()