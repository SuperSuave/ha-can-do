"""Select platform for WiCAN integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import WiCANEntity
from .helpers import format_friendly_name, wican_exception_handler

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import WiCANConfigEntry

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 0


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: WiCANConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select platform."""
    entities = [
        WiCANAmbientMoodLightSelectEntity(config_entry),
        WiCANDriverSeatHeaterSelectEntity(config_entry),
    ]
    async_add_entities(entities)


class WiCANAmbientMoodLightSelectEntity(WiCANEntity, SelectEntity, RestoreEntity):
    """Interior Ambient Mood Lighting Select Entity."""

    _attr_has_entity_name = True
    _attr_name = "Mood Light Theme"
    _attr_options = [
        "Electric Blue",
        "Cyan / Aqua Wave",
        "Deep Purple / Violet",
        "Magenta / Neon Pink",
        "Crimson Red",
        "Warm Sunset / Amber",
        "Lime / Mint Glow",
        "Warm White / Champagne",
    ]

    def __init__(self, config_entry: WiCANConfigEntry) -> None:
        """Initialize ambient light select entity."""
        description = EntityDescription(
            key="mood_light_theme",
            name="Mood Light Theme",
            icon="mdi:palette",
        )
        super().__init__(config_entry, description)
        self._attr_unique_id = f"{config_entry.entry_id}_mood_light_theme"
        self._attr_current_option = "Deep Purple / Violet"

    def _handle_coordinator_update(self) -> None:
        """Handle coordinator update."""
        status = self.coordinator.data.get("status", {})
        if "mood_light_theme" in status and status["mood_light_theme"] in self._attr_options:
            self._attr_current_option = status["mood_light_theme"]
        self.async_write_ha_state()

    @wican_exception_handler
    async def async_select_option(self, option: str) -> None:
        """Select a mood light theme."""
        if option not in self._attr_options:
            raise ValueError(f"Invalid option: {option}")

        # Option payload mappings
        payload_map = {
            "Electric Blue": "00 54 F1 0F 00 00 00 00",
            "Cyan / Aqua Wave": "00 64 53 0F 00 00 00 00",
            "Deep Purple / Violet": "80 00 F0 0F 00 00 00 00",
            "Magenta / Neon Pink": "FF 00 10 0F 00 00 00 00",
            "Crimson Red": "FE 88 00 00 00 00 00 00",
            "Warm Sunset / Amber": "FF 50 72 07 00 00 00 00",
            "Lime / Mint Glow": "F7 FC 63 0B 00 00 00 00",
            "Warm White / Champagne": "FE B4 53 0A 00 00 00 00",
        }

        payload = payload_map.get(option, "80 00 F0 0F 00 00 00 00")
        action_payload = {
            "id": "act_interior_ambient_mood_lighting",
            "name": f"Ambient: {option}",
            "type": "can_tx",
            "can_id": "0x4AD",
            "steps": [{"payload": payload, "repeat": 2}],
        }
        success = await self.coordinator.async_execute_action(action_payload)
        if success:
            self._attr_current_option = option
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore select state."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in self._attr_options:
            self._attr_current_option = last_state.state


class WiCANDriverSeatHeaterSelectEntity(WiCANEntity, SelectEntity, RestoreEntity):
    """Driver Seat Heater Level Select Entity."""

    _attr_has_entity_name = True
    _attr_name = "Driver Seat Heater Level"
    _attr_options = ["OFF", "LOW", "MED", "MAX"]

    def __init__(self, config_entry: WiCANConfigEntry) -> None:
        """Initialize seat heater level select entity."""
        description = EntityDescription(
            key="driver_seat_heater_level",
            name="Driver Seat Heater Level",
            icon="mdi:car-seat-heater",
        )
        super().__init__(config_entry, description)
        self._attr_unique_id = f"{config_entry.entry_id}_driver_seat_heater_level"
        self._attr_current_option = "OFF"

    def _handle_coordinator_update(self) -> None:
        """Handle coordinator update."""
        status = self.coordinator.data.get("status", {})
        if "seat_heater_driver" in status and status["seat_heater_driver"] in self._attr_options:
            self._attr_current_option = status["seat_heater_driver"]
        self.async_write_ha_state()

    @wican_exception_handler
    async def async_select_option(self, option: str) -> None:
        """Select seat heater level."""
        if option not in self._attr_options:
            raise ValueError(f"Invalid option: {option}")

        level_map = {
            "OFF": "00 00 00 00 00 00 00 00",
            "LOW": "06 00 00 00 00 00 00 00",
            "MED": "0C 00 00 00 00 00 00 00",
            "MAX": "12 00 00 00 00 00 00 00",
        }

        payload = level_map.get(option, "00 00 00 00 00 00 00 00")
        action_payload = {
            "id": f"act_driver_seat_heater_{option.lower()}",
            "name": f"Driver Seat Heater ({option})",
            "type": "can_tx",
            "can_id": "0x496",
            "steps": [{"payload": payload, "repeat": 2}],
        }
        success = await self.coordinator.async_execute_action(action_payload)
        if success:
            self._attr_current_option = option
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore select state."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in self._attr_options:
            self._attr_current_option = last_state.state
