"""Joystick Diagrams entry point for the Falcon BMS parser plugin."""

from pathlib import Path

from pydantic import Field

from joystick_diagrams.input.profile_collection import ProfileCollection
from joystick_diagrams.plugins.plugin_interface import PluginInterface
from joystick_diagrams.plugins.plugin_settings import PluginMeta, PluginSettings

from .bms_key_parser import BMSKeyParser


class FalconBMSSettings(PluginSettings):
    key_file: Path | None = Field(
        default=None,
        title="Falcon BMS Key File",
        description="Select a .key file from Falcon BMS User\\Config.",
        json_schema_extra={
            "is_folder": False,
            "default_path": r"C:\\Falcon BMS 4.38\\User\\Config",
            "extensions": [".key"],
        },
    )


class ParserPlugin(PluginInterface):
    plugin_meta = PluginMeta(
        name="Falcon BMS",
        version="0.1.1",
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

        return BMSKeyParser(key_path).process_profiles()


if __name__ == "__main__":
    ParserPlugin()

