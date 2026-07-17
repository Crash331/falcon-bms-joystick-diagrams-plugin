"""Joystick Diagrams entry point for the Falcon BMS parser plugin."""

import sys
from pathlib import Path

from pydantic import Field

from joystick_diagrams.input.profile_collection import ProfileCollection
from joystick_diagrams.plugins.plugin_interface import PluginInterface
from joystick_diagrams.plugins.plugin_settings import PluginMeta, PluginSettings

# Joystick Diagrams validates an upgraded plugin in the same process that may
# already have loaded the previous version. Its user-plugin loader replaces
# ``main`` but leaves child modules cached, so explicitly discard our small
# dependency chain before importing it from the newly installed directory.
for _child_module in ("version", "bms_axis_parser", "bms_key_parser"):
    sys.modules.pop(f"{__package__}.{_child_module}", None)

from .version import __version__
from .bms_key_parser import BMSKeyParser


BUTTON_LAYOUT_OPTIONS = ("Auto", "128", "32")


class FalconBMSSettings(PluginSettings):
    key_file: Path | None = Field(
        default=None,
        title="Falcon BMS Key File",
        description=(
            "Select the active .key file. Axis mappings and BMS input settings "
            "come from the optional config folder below, or from the key file's "
            "folder when that setting is blank."
        ),
        json_schema_extra={
            "is_folder": False,
            "default_path": r"C:\Falcon BMS 4.38\User\Config",
            "extensions": [".key"],
        },
    )
    config_folder: Path | None = Field(
        default=None,
        title="BMS Config Folder (Optional)",
        description=(
            "Folder containing Falcon BMS User.cfg, DeviceSorting.txt, and "
            "Setup.v*.xml. Leave blank to use the selected key file's folder."
        ),
        json_schema_extra={
            "is_folder": True,
            "default_path": r"C:\Falcon BMS 4.38\User\Config",
            "required": False,
        },
    )
    show_dx_button_numbers: bool = Field(
        default=False,
        title="Show DX Button Numbers",
        description=(
            'Prefix button actions with the physical button, e.g. "DX53 — '
            'Weapon Release". Re-run plugins to apply changes.'
        ),
    )
    show_axis_identifiers: bool = Field(
        default=False,
        title="Show Axis Identifiers",
        description=(
            'Prefix axis actions with the template key, e.g. "AXIS_RY — '
            'Throttle". Re-run plugins to apply changes.'
        ),
    )
    show_pov_identifiers: bool = Field(
        default=False,
        title="Show POV Identifiers",
        description=(
            'Prefix POV actions with the hat and direction, e.g. "POV 1 Up — '
            'Trim Nose Up". Re-run plugins to apply changes.'
        ),
    )
    button_layout: str = Field(
        default="Auto",
        title="Button Layout",
        description=(
            "Auto reads g_nButtonsPerDevice from the BMS config. Choose 128 or "
            "32 only to override detection. Re-run plugins to apply changes."
        ),
        json_schema_extra={"options": list(BUTTON_LAYOUT_OPTIONS)},
    )


class ParserPlugin(PluginInterface):
    plugin_meta = PluginMeta(
        name="Falcon BMS",
        version=__version__,
        icon_path="img/falcon_bms.svg",
    )
    plugin_settings_model = FalconBMSSettings

    def process(self) -> ProfileCollection:
        key_file = self.get_setting("key_file")
        if key_file is None:
            return ProfileCollection()

        key_path = Path(key_file)
        if key_path.suffix.casefold() != ".key":
            raise self.file_type_invalid("Falcon BMS profiles must use a .key file.")
        if not key_path.is_file():
            raise self.file_not_valid_exception(
                f"Falcon BMS key file does not exist: {key_path}"
            )

        configured_folder = self.get_setting("config_folder")
        config_dir = Path(configured_folder) if configured_folder else key_path.parent
        if not config_dir.is_dir():
            raise self.directory_not_valid_exception(
                f"Falcon BMS config folder does not exist: {config_dir}"
            )

        return BMSKeyParser(
            key_path,
            config_dir=config_dir,
            show_dx_button_numbers=bool(
                self.get_setting("show_dx_button_numbers")
            ),
            show_axis_identifiers=bool(self.get_setting("show_axis_identifiers")),
            show_pov_identifiers=bool(self.get_setting("show_pov_identifiers")),
            button_layout=str(self.get_setting("button_layout") or "Auto"),
        ).process_profiles()


if __name__ == "__main__":
    ParserPlugin()
