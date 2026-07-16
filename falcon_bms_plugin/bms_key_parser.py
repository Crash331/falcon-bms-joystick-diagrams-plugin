"""Parse Falcon BMS DirectInput bindings into Joystick Diagrams profiles.

Falcon BMS stores keyboard definitions and DirectInput assignments in the same
``.key`` file. DirectInput button rows use ``-2`` as their input type, while
POV rows use ``-3``. Button IDs are global, zero-based IDs: 128 buttons per
device and (in current BMS) 16 devices per DX shift layer.
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

BUTTONS_PER_DEVICE = 128
DEVICES_PER_SHIFT_LAYER = 16
BUTTONS_PER_SHIFT_LAYER = BUTTONS_PER_DEVICE * DEVICES_PER_SHIFT_LAYER
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

    def __init__(self, key_file: Path | str):
        self.key_file = Path(key_file)

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
                    self.device_guid(binding.device_name), binding.device_name
                )
                devices[binding.device_name] = device

            if binding.control_kind == "button":
                control = Button(binding.control_id)
            else:
                if binding.direction is None:  # defensive; parse() always sets this
                    continue
                control = Hat(binding.control_id, binding.direction)

            command = " | ".join(actions)
            if binding.layer == 0:
                device.create_input(control, command)
            else:
                modifier = (
                    "BMS DX Shift"
                    if binding.layer == 1
                    else f"BMS DX Shift {binding.layer}"
                )
                device.add_modifier_to_input(control, {modifier}, command)

        for binding in BMSAxisParser(self.key_file.parent).parse():
            device = devices.get(binding.device_name)
            if device is None:
                device = profile.add_device(
                    self.device_guid(binding.device_name), binding.device_name
                )
                devices[binding.device_name] = device
            device.create_input(binding.control, binding.action)

        return collection

    def parse(self) -> list[ParsedBinding]:
        lines = self._read_lines()
        labels = self._build_label_catalog(lines)
        bindings: list[ParsedBinding] = []
        current_device: str | None = None

        for line in lines:
            header_match = _HEADER_RE.match(line)
            if header_match:
                title = header_match.group("title").strip(" =\t")
                if title:
                    device_title = _POV_HEADER_SUFFIX_RE.sub("", title).strip()
                    current_device = re.sub(r"\s+", " ", device_title)
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
                physical_device = (
                    raw_control_id % BUTTONS_PER_SHIFT_LAYER
                ) // BUTTONS_PER_DEVICE
                device_name = current_device or (
                    f"BMS DirectInput Device {physical_device + 1}"
                )
                bindings.append(
                    ParsedBinding(
                        device_name=device_name,
                        control_kind="button",
                        control_id=(raw_control_id % BUTTONS_PER_DEVICE) + 1,
                        action=action,
                        layer=raw_control_id // BUTTONS_PER_SHIFT_LAYER,
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

    @staticmethod
    def device_guid(device_name: str) -> str:
        """Create a stable UUID for key files, which do not store device GUIDs."""

        normalised_name = " ".join(device_name.split()).casefold()
        key = f"joystick-diagrams:falcon-bms:{normalised_name}"
        return str(uuid5(NAMESPACE_URL, key))

    def _read_lines(self) -> list[str]:
        data = self.key_file.read_bytes()
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252")
        return text.splitlines()

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

