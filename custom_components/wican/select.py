"""Select platform for WiCAN integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .entity import WiCANEntity
from .helpers import format_friendly_name, wican_exception_handler

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import WiCANConfigEntry

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 0

DYNAMIC_SELECT_ENTITIES: dict[str, dict[str, Any]] = {}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: WiCANConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select platform."""
    DYNAMIC_SELECT_ENTITIES[config_entry.entry_id] = {}

    catalog = config_entry.runtime_data.coordinator.data.get("cando_catalog")
    entities = []

    if catalog:
        entries = catalog.get("entries", catalog) if isinstance(catalog, dict) else catalog
        if isinstance(entries, list):
            mood_match = [item for item in entries if isinstance(item, dict) and ("ambient" in item.get("id", "") or "mood" in item.get("id", "")) and "options" in item]
            seat_match = [item for item in entries if isinstance(item, dict) and "seat_heater" in item.get("id", "")]

            registered = DYNAMIC_SELECT_ENTITIES[config_entry.entry_id]
            if mood_match:
                e = WiCANAmbientMoodLightSelectEntity(config_entry, mood_match[0])
                registered["mood"] = e
                entities.append(e)
            if seat_match:
                e = WiCANDriverSeatHeaterSelectEntity(config_entry, seat_match)
                registered["seat"] = e
                entities.append(e)

    if entities:
        async_add_entities(entities)

    @callback
    def handle_catalog_update(webhook_id, data):
        if webhook_id != config_entry.runtime_data.webhook_id:
            return
        cat = data.get("cando_catalog")
        if not cat:
            return
        cat_entries = cat.get("entries", cat) if isinstance(cat, dict) else cat
        if not isinstance(cat_entries, list):
            return

        mood_match = [item for item in cat_entries if isinstance(item, dict) and ("ambient" in item.get("id", "") or "mood" in item.get("id", "")) and "options" in item]
        seat_match = [item for item in cat_entries if isinstance(item, dict) and "seat_heater" in item.get("id", "")]

        registered = DYNAMIC_SELECT_ENTITIES[config_entry.entry_id]
        new_entities = []
        if mood_match:
            if "mood" in registered:
                registered["mood"]._action_def = mood_match[0]
            else:
                e = WiCANAmbientMoodLightSelectEntity(config_entry, mood_match[0])
                registered["mood"] = e
                new_entities.append(e)

        if seat_match:
            if "seat" in registered:
                registered["seat"]._action_defs = seat_match
            else:
                e = WiCANDriverSeatHeaterSelectEntity(config_entry, seat_match)
                registered["seat"] = e
                new_entities.append(e)

        if new_entities:
            async_add_entities(new_entities)

    unsub = async_dispatcher_connect(hass, DOMAIN, handle_catalog_update)
    config_entry.async_on_unload(unsub)


class WiCANAmbientMoodLightSelectEntity(WiCANEntity, SelectEntity, RestoreEntity):
    """Interior Ambient Mood Lighting Select Entity."""

    _attr_has_entity_name = True
    _attr_name = "Mood Light Theme"

    def __init__(self, config_entry: WiCANConfigEntry, action_def: dict[str, Any] | None = None) -> None:
        """Initialize ambient light select entity."""
        description = EntityDescription(
            key="mood_light_theme",
            name="Mood Light Theme",
            icon="mdi:palette",
        )
        super().__init__(config_entry, description)
        self._action_def = action_def or {}
        self._attr_unique_id = f"{config_entry.entry_id}_mood_light_theme"

        options_list = []
        if action_def and "options" in action_def:
            for opt in action_def.get("options", []):
                if isinstance(opt, dict) and "label" in opt:
                    options_list.append(opt["label"])

        self._attr_options = options_list or []
        self._attr_current_option = self._attr_options[0] if self._attr_options else None

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

        matched_opt = None
        if self._action_def and "options" in self._action_def:
            matched_opt = next((o for o in self._action_def["options"] if isinstance(o, dict) and o.get("label") == option), None)

        if not matched_opt and not self._action_def:
            _LOGGER.warning("No ambient light theme action defined in catalog for this vehicle")
            return

        payload = matched_opt.get("payload") if matched_opt else None

        action_payload = dict(self._action_def)
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

    def __init__(self, config_entry: WiCANConfigEntry, action_defs: list[dict[str, Any]] | None = None) -> None:
        """Initialize seat heater level select entity."""
        description = EntityDescription(
            key="driver_seat_heater_level",
            name="Driver Seat Heater Level",
            icon="mdi:car-seat-heater",
        )
        super().__init__(config_entry, description)
        self._action_defs = action_defs or []
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

        action_def = next((a for a in self._action_defs if option.lower() in a.get("id", "").lower()), None)
        if not action_def:
            _LOGGER.warning("No seat heater action defined in catalog for this vehicle")
            return

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
