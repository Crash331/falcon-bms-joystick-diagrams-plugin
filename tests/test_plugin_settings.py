from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from joystick_diagrams.exceptions import DirectoryNotValidError

from falcon_bms_plugin import __version__
from falcon_bms_plugin.main import FalconBMSSettings, ParserPlugin


class FalconBMSSettingsTests(unittest.TestCase):
    def test_v030_settings_schema_and_defaults(self):
        settings = FalconBMSSettings()
        self.assertIsNone(settings.key_file)
        self.assertIsNone(settings.config_folder)
        self.assertFalse(settings.show_dx_button_numbers)
        self.assertFalse(settings.show_axis_identifiers)
        self.assertFalse(settings.show_pov_identifiers)
        self.assertEqual("Auto", settings.button_layout)

        fields = FalconBMSSettings.model_fields
        self.assertIs(fields["show_dx_button_numbers"].annotation, bool)
        self.assertIs(fields["show_axis_identifiers"].annotation, bool)
        self.assertIs(fields["show_pov_identifiers"].annotation, bool)
        self.assertIs(fields["button_layout"].annotation, str)
        self.assertEqual(
            ["Auto", "128", "32"],
            fields["button_layout"].json_schema_extra["options"],
        )
        self.assertEqual(
            {
                "is_folder": True,
                "default_path": r"C:\Falcon BMS 4.38\User\Config",
                "required": False,
            },
            fields["config_folder"].json_schema_extra,
        )

    def test_v020_persisted_settings_gain_backward_compatible_defaults(self):
        old_key_path = Path(r"C:\Profiles\Pilot.key")
        settings = FalconBMSSettings.model_validate({"key_file": old_key_path})

        self.assertEqual(old_key_path, settings.key_file)
        self.assertIsNone(settings.config_folder)
        self.assertFalse(settings.show_dx_button_numbers)
        self.assertFalse(settings.show_axis_identifiers)
        self.assertFalse(settings.show_pov_identifiers)
        self.assertEqual("Auto", settings.button_layout)

    def test_plugin_metadata_uses_single_version_source(self):
        self.assertEqual("0.3.1", __version__)
        self.assertEqual(__version__, ParserPlugin.plugin_meta.version)
        self.assertEqual("Falcon BMS", ParserPlugin.plugin_meta.name)

    def test_optional_config_folder_does_not_block_ready_state(self):
        plugin = ParserPlugin()
        plugin._plugin_settings = FalconBMSSettings(
            key_file=Path(r"C:\Profiles\Pilot.key")
        )
        self.assertTrue(plugin.ready)

    def test_missing_or_file_config_folder_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            key_file = root / "Pilot.key"
            key_file.write_text("", encoding="utf-8")
            file_path = root / "not-a-folder.txt"
            file_path.write_text("", encoding="utf-8")

            for invalid_path in (root / "missing", file_path):
                with self.subTest(path=invalid_path):
                    plugin = ParserPlugin()
                    plugin._plugin_settings = FalconBMSSettings(
                        key_file=key_file,
                        config_folder=invalid_path,
                    )
                    with self.assertRaises(DirectoryNotValidError):
                        plugin.process()

    def test_process_applies_display_and_layout_settings(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            key_file = root / "Pilot.key"
            key_file.write_text(
                '#======== Test Device ========\n'
                'Action 160 -1 -2 0 0x0 0 "Mapped Action"\n',
                encoding="utf-8",
            )
            root.joinpath("Falcon BMS User.cfg").write_text(
                "set g_nButtonsPerDevice 32\n"
                "set g_nHotasPinkyShiftMagnitude 2048\n",
                encoding="utf-8",
            )

            plugin = ParserPlugin()
            plugin._plugin_settings = FalconBMSSettings(
                key_file=key_file,
                show_dx_button_numbers=True,
                button_layout="128",
            )
            profile = plugin.process().get_profile("Pilot")
            self.assertIsNotNone(profile)
            device = next(iter(profile.devices.values()))
            self.assertEqual(
                "DX33 — Mapped Action",
                device.inputs["buttons"]["BUTTON_33"].command,
            )


if __name__ == "__main__":
    unittest.main()
