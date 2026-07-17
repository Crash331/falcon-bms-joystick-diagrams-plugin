"""Parse Falcon BMS DirectInput bindings into Joystick Diagrams profiles.

Falcon BMS stores keyboard definitions and DirectInput assignments in the same
``.key`` file. DirectInput button rows use ``-2`` as their input type, while
POV rows use ``-3``. Button IDs are global, zero-based IDs. Their device width
and DX-shift offset are controlled by Falcon BMS configuration settings.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from joystick_diagrams.input.button import Button
from joystick_diagrams.input.device import Device_
from joystick_diagrams.input.hat import Hat, HatDirection
from joystick_diagrams.input.profile_collection import ProfileCollection

from .bms_axis_parser import BMSAxisParser

BUTTON_LAYOUT_AUTO = "Auto"
BUTTON_LAYOUT_OPTIONS = (BUTTON_LAYOUT_AUTO, "128", "32")
DEFAULT_BUTTONS_PER_DEVICE = 32
DEFAULT_SHIFT_MAGNITUDE = 256
POVS_PER_SHIFT_LAYER = 2

_NUMBER = r"(?:-?\d+|0[xX][0-9a-fA-F]+)"
_DIRECT_INPUT_RE = re.compile(
    rf"^\s*(?P<callback>\S+)"
    rf"\s+(?P<control_id>{_NUMBER})"
    rf"\s+(?P<invocation>{_NUMBER})"
    rf"\s+(?P<input_type>-2|-3)"
    rf"\s+(?P<event_or_direction>{_NUMBER})"
    rf"\s+(?P<combo>{_NUMBER})"
    rf"\s+(?P<sound>{_NUMBER})"
    r'(?:\s+"(?P<label>.*)")?\s*$'
)
_LABEL_RE = re.compile(r'^\s*(?P<callback>\S+)\s+.*\s+"(?P<label>.*)"\s*$')
_HEADER_RE = re.compile(r"^\s*#\s*=+\s*(?P<title>.*?)\s*=+\s*$")
_POV_HEADER_SUFFIX_RE = re.compile(
    r"\s*:\s*POV\s*#\s*\d+\s*$", re.IGNORECASE
)
_CONFIG_SETTING_RE = re.compile(
    r"^\s*set\s+"
    r"(?P<name>g_nButtonsPerDevice|g_nHotasPinkyShiftMagnitude)"
    r"\s+(?P<value>-?\d+)\b",
    re.IGNORECASE,
)
_DEVICE_SORTING_RE = re.compile(
    r'^\s*\{[0-9a-f-]+\}\s+"(?P<name>.+)"\s*$', re.IGNORECASE
)

_POV_DIRECTIONS = {
    0: HatDirection.U,
    1: HatDirection.UR,
    2: HatDirection.R,
    3: HatDirection.DR,
    4: HatDirection.D,
    5: HatDirection.DL,
    6: HatDirection.L,
    7: HatDirection.UL,
}

_POV_DIRECTION_NAMES = {
    HatDirection.U: "Up",
    HatDirection.UR: "Up Right",
    HatDirection.R: "Right",
    HatDirection.DR: "Down Right",
    HatDirection.D: "Down",
    HatDirection.DL: "Down Left",
    HatDirection.L: "Left",
    HatDirection.UL: "Up Left",
}


@dataclass(frozen=True, slots=True)
class ParsedBinding:
    device_name: str
    control_kind: str
    control_id: int
    action: str
    layer: int = 0
    direction: HatDirection | None = None
    event: str | None = None

    @property
    def display_action(self) -> str:
        if self.event:
            return f"{self.action} ({self.event})"
        return self.action


class BMSKeyParser:
    """Parser for one Falcon BMS ``.key`` profile."""

    def __init__(
        self,
        key_file: Path | str,
        *,
        config_dir: Path | str | None = None,
        show_dx_button_numbers: bool = False,
        show_axis_identifiers: bool = False,
        show_pov_identifiers: bool = False,
        button_layout: str = BUTTON_LAYOUT_AUTO,
    ):
        self.key_file = Path(key_file)
        self.config_dir = Path(config_dir) if config_dir else self.key_file.parent
        self.show_dx_button_numbers = show_dx_button_numbers
        self.show_axis_identifiers = show_axis_identifiers
        self.show_pov_identifiers = show_pov_identifiers
        self.button_layout = button_layout
        self._setup_device_guids = BMSAxisParser(self.config_dir).device_guids()

    def process_profiles(self) -> ProfileCollection:
        bindings = self.parse()
        collection = ProfileCollection()
        profile = collection.create_profile(self.key_file.stem)

        grouped = self._group_bindings(bindings)
        devices: OrderedDict[str, Device_] = OrderedDict()

        for binding, actions in grouped:
            device = devices.get(binding.device_name)
            if device is None:
                device = profile.add_device(
                    self.resolve_device_guid(binding.device_name),
                    binding.device_name,
                )
                devices[binding.device_name] = device

            if binding.control_kind == "button":
                control = Button(binding.control_id)
            else:
                if binding.direction is None:  # defensive; parse() always sets this
                    continue
                control = Hat(binding.control_id, binding.direction)

            command = self._format_command(binding, " | ".join(actions))
            if binding.layer == 0:
                device.create_input(control, command)
            else:
                modifier = (
                    "BMS DX Shift"
                    if binding.layer == 1
                    else f"BMS DX Shift {binding.layer}"
                )
                device.add_modifier_to_input(control, {modifier}, command)

        axis_parser = BMSAxisParser(self.config_dir)
        for binding in axis_parser.parse():
            device = devices.get(binding.device_name)
            if device is None:
                device = profile.add_device(
                    self.resolve_device_guid(binding.device_name),
                    binding.device_name,
                )
                devices[binding.device_name] = device
            action = binding.action
            if self.show_axis_identifiers:
                action = self._prefix_identifier(binding.control.identifier, action)
            device.create_input(binding.control, action)

        for setup_profile in axis_parser.setup_profiles():
            if setup_profile.device_name in devices:
                continue
            if not axis_parser.has_assignments(setup_profile):
                continue
            device = profile.get_device(setup_profile.device_guid)
            if device is None:
                device = profile.add_device(
                    setup_profile.device_guid,
                    setup_profile.device_name,
                )
            devices[setup_profile.device_name] = device

        return collection

    def parse(self) -> list[ParsedBinding]:
        lines = self._read_lines()
        labels = self._build_label_catalog(lines)
        buttons_per_device = self.resolve_buttons_per_device()
        shift_magnitude = self.resolve_shift_magnitude()
        configured_device_indices = self._read_device_indices()
        inferred_device_indices: dict[str, int] = {}
        used_device_indices = set(configured_device_indices.values())
        bindings: list[ParsedBinding] = []
        current_device: str | None = None

        for line in lines:
            header_match = _HEADER_RE.match(line)
            if header_match:
                title = header_match.group("title").strip(" =\t")
                if title:
                    device_title = _POV_HEADER_SUFFIX_RE.sub("", title).strip()
                    current_device = self._normalise_device_name(device_title)
                continue

            if line.lstrip().startswith("#"):
                continue

            match = _DIRECT_INPUT_RE.match(line)
            if not match:
                continue

            callback = match.group("callback")
            if callback.casefold() == "simdonothing":
                continue

            raw_control_id = self._parse_number(match.group("control_id"))
            if raw_control_id < 0:
                continue

            invocation = self._parse_number(match.group("invocation"))
            event_or_direction = self._parse_number(
                match.group("event_or_direction")
            )
            input_type = match.group("input_type")
            inline_label = (match.group("label") or "").strip()
            action = inline_label or labels.get(callback) or callback
            event = self._event_name(invocation, event_or_direction, input_type)

            if input_type == "-2":
                expected_device = self._resolve_device_index(
                    current_device,
                    configured_device_indices,
                    inferred_device_indices,
                    used_device_indices,
                )
                layer, physical_button, physical_device = self._decode_button_id(
                    raw_control_id,
                    buttons_per_device,
                    shift_magnitude,
                    expected_device,
                )
                device_name = current_device or (
                    f"BMS DirectInput Device {physical_device + 1}"
                )
                bindings.append(
                    ParsedBinding(
                        device_name=device_name,
                        control_kind="button",
                        control_id=physical_button + 1,
                        action=action,
                        layer=layer,
                        event=event,
                    )
                )
                continue

            direction = _POV_DIRECTIONS.get(event_or_direction)
            if direction is None:
                continue
            bindings.append(
                ParsedBinding(
                    device_name=current_device or "BMS POV Device",
                    control_kind="hat",
                    control_id=(raw_control_id % POVS_PER_SHIFT_LAYER) + 1,
                    action=action,
                    layer=raw_control_id // POVS_PER_SHIFT_LAYER,
                    direction=direction,
                )
            )

        return bindings

    def _read_device_indices(self) -> dict[str, int]:
        """Read the BMS device order used to encode global button IDs."""

        path = self.config_dir / "DeviceSorting.txt"
        if not path.is_file():
            return {}

        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return {}

        indices: dict[str, int] = {}
        device_index = 0
        for line in text.splitlines():
            match = _DEVICE_SORTING_RE.match(line)
            if match:
                name = self._normalise_device_name(match.group("name"))
                indices.setdefault(name.casefold(), device_index)
                device_index += 1
        return indices

    def _resolve_device_index(
        self,
        device_name: str | None,
        configured: dict[str, int],
        inferred: dict[str, int],
        used: set[int],
    ) -> int | None:
        if not device_name:
            return None

        key = self._normalise_device_name(device_name).casefold()
        configured_index = configured.get(key)
        if configured_index is None:
            prefix_matches = {
                index
                for configured_name, index in configured.items()
                if configured_name.startswith(key) or key.startswith(configured_name)
            }
            if len(prefix_matches) == 1:
                configured_index = prefix_matches.pop()
        if configured_index is not None:
            return configured_index

        if key not in inferred:
            index = 0
            while index in used:
                index += 1
            inferred[key] = index
            used.add(index)
        return inferred[key]

    @staticmethod
    def _decode_button_id(
        raw_control_id: int,
        buttons_per_device: int,
        shift_magnitude: int,
        expected_device: int | None,
    ) -> tuple[int, int, int]:
        """Return shift layer, zero-based physical button, and device index."""

        if expected_device is not None:
            device_base = expected_device * buttons_per_device
            base_button = raw_control_id - device_base
            if 0 <= base_button < buttons_per_device:
                return 0, base_button, expected_device

            shifted_button = raw_control_id - device_base - shift_magnitude
            if shift_magnitude > 0 and 0 <= shifted_button < buttons_per_device:
                return 1, shifted_button, expected_device

            return 0, raw_control_id % buttons_per_device, expected_device

        if shift_magnitude > 0 and raw_control_id >= shift_magnitude:
            layer = 1
            physical_control_id = raw_control_id - shift_magnitude
        else:
            layer = 0
            physical_control_id = raw_control_id
        return (
            layer,
            physical_control_id % buttons_per_device,
            physical_control_id // buttons_per_device,
        )

    @staticmethod
    def _normalise_device_name(device_name: str) -> str:
        return re.sub(r"\s+", " ", device_name).strip()

    def resolve_buttons_per_device(self) -> int:
        """Resolve the BMS global button-ID width for each DirectInput device."""

        layout = str(self.button_layout or BUTTON_LAYOUT_AUTO).strip()
        if layout in {"32", "128"}:
            return int(layout)

        configured = self._read_input_config().get("g_nbuttonsperdevice")
        if configured is not None and 32 <= configured <= 128:
            return configured
        return DEFAULT_BUTTONS_PER_DEVICE

    def resolve_shift_magnitude(self) -> int:
        """Resolve the configured offset used by BMS's DX-shift layer."""

        configured = self._read_input_config().get(
            "g_nhotaspinkyshiftmagnitude"
        )
        if configured is None:
            return DEFAULT_SHIFT_MAGNITUDE
        return max(configured, 0)

    @staticmethod
    def device_guid(device_name: str) -> str:
        """Create a stable UUID for key files, which do not store device GUIDs."""

        normalised_name = " ".join(device_name.split()).casefold()
        key = f"joystick-diagrams:falcon-bms:{normalised_name}"
        return str(uuid5(NAMESPACE_URL, key))

    def resolve_device_guid(self, device_name: str) -> str:
        """Use BMS's saved device GUID when available, with a stable fallback."""

        key = self._normalise_device_name(device_name).casefold()
        guid = self._setup_device_guids.get(key)
        if guid is None:
            prefix_matches = {
                candidate_guid
                for candidate_name, candidate_guid in (
                    self._setup_device_guids.items()
                )
                if candidate_name.startswith(key) or key.startswith(candidate_name)
            }
            if len(prefix_matches) == 1:
                guid = prefix_matches.pop()
        return guid or self.device_guid(device_name)

    def _read_lines(self) -> list[str]:
        data = self.key_file.read_bytes()
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252")
        return text.splitlines()

    def _read_input_config(self) -> dict[str, int]:
        """Read effective input settings, with the user cfg overriding the base."""

        try:
            config_paths = {
                path.name.casefold(): path for path in self.config_dir.glob("*.cfg")
            }
        except OSError:
            return {}

        settings: dict[str, int] = {}
        for file_name in ("falcon bms.cfg", "falcon bms user.cfg"):
            path = config_paths.get(file_name)
            if path is None:
                continue
            try:
                text = path.read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                match = _CONFIG_SETTING_RE.match(line)
                if match:
                    settings[match.group("name").casefold()] = int(
                        match.group("value")
                    )
        return settings

    def _format_command(self, binding: ParsedBinding, command: str) -> str:
        if binding.control_kind == "button" and self.show_dx_button_numbers:
            return self._prefix_identifier(f"DX{binding.control_id}", command)
        if binding.control_kind == "hat" and self.show_pov_identifiers:
            direction = _POV_DIRECTION_NAMES.get(binding.direction, "")
            identifier = f"POV {binding.control_id} {direction}".rstrip()
            return self._prefix_identifier(identifier, command)
        return command

    @staticmethod
    def _prefix_identifier(identifier: str, command: str) -> str:
        return f"{identifier} — {command}"

    @staticmethod
    def _build_label_catalog(lines: list[str]) -> dict[str, str]:
        labels: dict[str, str] = {}
        for line in lines:
            if line.lstrip().startswith("#"):
                continue
            match = _LABEL_RE.match(line)
            if not match:
                continue
            callback = match.group("callback")
            label = match.group("label").strip()
            if callback.casefold() != "simdonothing" and label:
                labels.setdefault(callback, label)
        return labels

    @staticmethod
    def _event_name(invocation: int, event_code: int, input_type: str) -> str | None:
        if input_type != "-2":
            return None
        if event_code == 0x42 or invocation == -4:
            return "release"
        if invocation == -2:
            return "press"
        return None

    @staticmethod
    def _parse_number(value: str) -> int:
        return int(value, 0)

    @staticmethod
    def _group_bindings(
        bindings: list[ParsedBinding],
    ) -> list[tuple[ParsedBinding, list[str]]]:
        grouped: OrderedDict[tuple, tuple[ParsedBinding, list[str]]] = OrderedDict()
        for binding in bindings:
            key = (
                binding.device_name,
                binding.control_kind,
                binding.control_id,
                binding.direction,
                binding.layer,
            )
            if key not in grouped:
                grouped[key] = (binding, [])
            actions = grouped[key][1]
            if binding.display_action not in actions:
                actions.append(binding.display_action)
        return list(grouped.values())
