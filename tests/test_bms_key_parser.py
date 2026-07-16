from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from falcon_bms_plugin.bms_key_parser import BMSKeyParser


SAMPLE_KEY = '''
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
'''


class BMSKeyParserTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.key_file = Path(self.temp_dir.name) / "Pilot.key"
        self.key_file.write_text(SAMPLE_KEY, encoding="utf-8")

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

    def test_builds_a_profile_collection(self):
        collection = BMSKeyParser(self.key_file).process_profiles()

        self.assertEqual(1, len(collection))
        profile = collection.get_profile("Pilot")
        self.assertIsNotNone(profile)
        self.assertEqual(2, len(profile.devices))

        throttle = next(
            device
            for device in profile.devices.values()
            if device.name == "WINCTRL Orion Throttle Base II"
        )
        self.assertEqual(
            "LEFT WALL: CANOPY - Open",
            throttle.inputs["buttons"]["BUTTON_69"].command,
        )
        self.assertEqual(
            "LEFT WALL: CANOPY - Close (press) | "
            "LEFT WALL: CANOPY - Close (release)",
            throttle.inputs["buttons"]["BUTTON_71"].command,
        )

        stick = next(
            device
            for device in profile.devices.values()
            if device.name == "WINCTRL Orion Joystick Base Metal 2"
        )
        self.assertEqual(
            ["BUTTON_32", "BUTTON_33", "BUTTON_34", "BUTTON_35"],
            list(stick.inputs["buttons"]),
        )
        up = stick.inputs["hats"]["POV_1_U"]
        self.assertEqual("STICK: TRIM - Nose Up", up.command)
        self.assertEqual(1, len(up.modifiers))
        self.assertEqual({"BMS DX Shift"}, up.modifiers[0].modifiers)

    def test_device_guid_is_stable_and_case_insensitive(self):
        first = BMSKeyParser.device_guid("WINCTRL Orion Throttle")
        second = BMSKeyParser.device_guid("winctrl orion throttle")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()

