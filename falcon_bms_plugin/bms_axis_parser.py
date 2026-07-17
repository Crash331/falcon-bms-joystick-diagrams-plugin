"""Parse Falcon BMS Alternative Launcher axis assignments."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from joystick_diagrams.input.axis import Axis, AxisDirection, AxisSlider

PHYSICAL_AXES = ("X", "Y", "Z", "RX", "RY", "RZ", "SLIDER0", "SLIDER1")

_AXIS_DISPLAY_NAMES = {
    "Cursor_X": "Radar Cursor X",
    "Cursor_Y": "Radar Cursor Y",
    "Radar_Antenna_Elevation": "Radar Antenna Elevation",
}
_SETUP_PROFILE_RE = re.compile(
    r"^Setup\.v\d+\.(?P<name>.+?)\s+\{(?P<guid>[0-9a-f-]+)\}\.xml$",
    re.IGNORECASE,
)
_DEVICE_SORTING_RE = re.compile(
    r'^\s*\{[0-9a-f-]+\}\s+"(?P<name>.+)"\s*$', re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class ParsedAxisBinding:
    device_name: str
    control: Axis | AxisSlider
    action: str


@dataclass(frozen=True, slots=True)
class SetupProfile:
    device_name: str
    device_guid: str
    path: Path


class BMSAxisParser:
    """Parser for saved devices in a Falcon BMS User\\Config directory."""

    def __init__(self, config_dir: Path | str):
        self.config_dir = Path(config_dir)

    def parse(self) -> list[ParsedAxisBinding]:
        bindings: list[ParsedAxisBinding] = []
        for setup_profile in self.setup_profiles():
            try:
                root = ET.parse(setup_profile.path).getroot()
            except (ET.ParseError, OSError):
                continue

            for physical_axis, node in zip(
                PHYSICAL_AXES, root.findall("./axis/AxAssgn")
            ):
                assigned_axis = (node.findtext("AxisName") or "").strip()
                if not assigned_axis:
                    continue
                action = _AXIS_DISPLAY_NAMES.get(
                    assigned_axis, assigned_axis.replace("_", " ")
                )
                bindings.append(
                    ParsedAxisBinding(
                        device_name=setup_profile.device_name,
                        control=self.axis_control(physical_axis),
                        action=action,
                    )
                )

        return bindings

    def setup_profiles(self) -> list[SetupProfile]:
        """Return active devices first, followed by disconnected saved devices."""

        active_devices = self._read_device_sorting()
        setup_files: dict[str, SetupProfile] = {}

        for path in self.config_dir.glob("Setup.v*.xml"):
            match = _SETUP_PROFILE_RE.match(path.name)
            if not match:
                continue
            device_name = self.normalise_device_name(match.group("name"))
            normalised = device_name.casefold()
            try:
                device_guid = str(UUID(match.group("guid")))
            except ValueError:
                continue
            existing = setup_files.get(normalised)
            if (
                existing is None
                or path.stat().st_mtime > existing.path.stat().st_mtime
            ):
                setup_files[normalised] = SetupProfile(
                    device_name=device_name,
                    device_guid=device_guid,
                    path=path,
                )

        ordered_keys = list(
            dict.fromkeys(
                name.casefold()
                for name in active_devices
                if name.casefold() in setup_files
            )
        )
        ordered_key_set = set(ordered_keys)
        ordered_keys.extend(
            key for key in sorted(setup_files) if key not in ordered_key_set
        )
        return [setup_files[key] for key in ordered_keys]

    def device_guids(self) -> dict[str, str]:
        return {
            profile.device_name.casefold(): profile.device_guid
            for profile in self.setup_profiles()
        }

    @staticmethod
    def has_assignments(profile: SetupProfile) -> bool:
        """Return whether a saved setup contains any axis or callback mapping."""

        try:
            root = ET.parse(profile.path).getroot()
        except (ET.ParseError, OSError):
            return False

        if any((node.text or "").strip() for node in root.findall(".//AxisName")):
            return True
        return any(
            (node.text or "").strip().casefold() not in {"", "simdonothing"}
            for node in root.findall(".//Callback/string")
        )

    def _read_device_sorting(self) -> list[str]:
        path = self.config_dir / "DeviceSorting.txt"
        if not path.is_file():
            return []

        names: list[str] = []
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for line in text.splitlines():
            match = _DEVICE_SORTING_RE.match(line)
            if match:
                names.append(self.normalise_device_name(match.group("name")))
        return names

    @staticmethod
    def axis_control(physical_axis: str) -> Axis | AxisSlider:
        if physical_axis.startswith("SLIDER"):
            return AxisSlider(int(physical_axis.removeprefix("SLIDER")) + 1)
        return Axis(AxisDirection[physical_axis])

    @staticmethod
    def normalise_device_name(device_name: str) -> str:
        return re.sub(r"\s+", " ", device_name).strip()