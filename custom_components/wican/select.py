"""Select platform for WiCAN integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import WiCANEntity
from .helpers import wican_exception_handler

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

    def __init__(self, config_entry: WiCANConfigEntry) -> None:
        """Initialize ambient light select entity."""
        description = EntityDescription(
            key="mood_light_theme",
            name="Mood Light Theme",
            icon="mdi:palette",
        )
        super().__init__(config_entry, description)
        self._attr_unique_id = f"{config_entry.entry_id}_mood_light_theme"

        self._attr_options = [
            "Electric Blue",
            "Cyan / Aqua Wave",
            "Deep Purple / Violet",
            "Magenta / Neon Pink",
            "Crimson Red",
            "Warm Sunset / Amber",
            "Lime / Mint Glow",
            "Warm White / Champagne",
        ]
        self._attr_current_option = self._attr_options[0]

    def _get_catalog_actions(self) -> list[dict[str, Any]]:
        catalog = self.coordinator.data.get("cando_catalog")
        if not catalog:
            return []
        entries = catalog.get("entries", catalog) if isinstance(catalog, dict) else catalog if isinstance(catalog, list) else []
        return [item for item in entries if isinstance(item, dict)]

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

        actions = self._get_catalog_actions()
        action_def = next((a for a in actions if "ambient" in a.get("id", "").lower() or "mood" in a.get("id", "").lower()), None)

        matched_opt = None
        if action_def and "options" in action_def:
            matched_opt = next((o for o in action_def["options"] if isinstance(o, dict) and o.get("label") == option), None)

        payload = matched_opt.get("payload") if matched_opt else None

        action_payload = dict(action_def) if action_def else {
            "id": "act_interior_ambient_mood_lighting",
            "name": f"Ambient: {option}",
            "type": "can_tx",
            "can_id": "0x4AD",
        }
        if payload:
            action_payload["steps"] = [{"payload": payload, "repeat": 2}]

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

    def _get_catalog_actions(self) -> list[dict[str, Any]]:
        catalog = self.coordinator.data.get("cando_catalog")
        if not catalog:
            return []
        entries = catalog.get("entries", catalog) if isinstance(catalog, dict) else catalog if isinstance(catalog, list) else []
        return [item for item in entries if isinstance(item, dict)]

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

        actions = self._get_catalog_actions()
        action_def = next((a for a in actions if option.lower() in a.get("id", "").lower()), None)
        if not action_def:
            level_map = {
                "OFF": "00 00 00 00 00 00 00 00",
                "LOW": "06 00 00 00 00 00 00 00",
                "MED": "0C 00 00 00 00 00 00 00",
                "MAX": "12 00 00 00 00 00 00 00",
            }
            action_def = {
                "id": f"act_driver_seat_heater_{option.lower()}",
                "name": f"Driver Seat Heater ({option})",
                "type": "can_tx",
                "can_id": "0x496",
                "steps": [{"payload": level_map.get(option, "00 00 00 00 00 00 00 00"), "repeat": 2}],
            }

        success = await self.coordinator.async_execute_action(action_def)
        if success:
            self._attr_current_option = option
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore select state."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in self._attr_options:
            self._attr_current_option = last_state.state
