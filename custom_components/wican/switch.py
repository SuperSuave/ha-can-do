"""Switch platform for WiCAN integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .entity import CANDoEntity
from .helpers import extract_catalog_entries, format_friendly_name, wican_exception_handler

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import WiCANConfigEntry

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 0

DYNAMIC_SWITCH_ENTITIES: dict[str, dict[str, WiCANSteeringWheelHeaterSwitchEntity]] = {}


def _is_steering_wheel_heater_action(item: dict) -> bool:
    ha_domain = str(item.get("ha_domain", "")).lower()
    if ha_domain == "switch":
        return True
    act_id = str(item.get("id", "")).lower()
    return "steering_wheel_heater" in act_id or "steering_heater" in act_id or "heater" in act_id


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: WiCANConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch platform."""
    DYNAMIC_SWITCH_ENTITIES[config_entry.entry_id] = {}

    catalog = config_entry.runtime_data.coordinator.data.get("cando_catalog")
    entries = extract_catalog_entries(catalog)
    matching = [item for item in entries if _is_steering_wheel_heater_action(item)]
    has_steering_heater = len(matching) > 0

    if has_steering_heater:
        entity = WiCANSteeringWheelHeaterSwitchEntity(config_entry, matching)
        DYNAMIC_SWITCH_ENTITIES[config_entry.entry_id]["steering_heater"] = entity
        async_add_entities([entity])

    @callback
    def handle_catalog_update(webhook_id, data):
        if webhook_id != config_entry.runtime_data.webhook_id:
            return
        cat = data.get("cando_catalog")
        if not cat:
            return
        cat_entries = extract_catalog_entries(cat)

        matching = [item for item in cat_entries if _is_steering_wheel_heater_action(item)]
        registered = DYNAMIC_SWITCH_ENTITIES[config_entry.entry_id]
        if matching:
            if "steering_heater" in registered:
                registered["steering_heater"]._action_defs = matching
            else:
                entity = WiCANSteeringWheelHeaterSwitchEntity(config_entry, matching)
                registered["steering_heater"] = entity
                async_add_entities([entity])

    unsub = async_dispatcher_connect(hass, DOMAIN, handle_catalog_update)
    config_entry.async_on_unload(unsub)


class WiCANSteeringWheelHeaterSwitchEntity(CANDoEntity, SwitchEntity, RestoreEntity):
    """Steering Wheel Heater Switch Entity."""

    _attr_has_entity_name = True
    _attr_name = "Steering Wheel Heater"

    def __init__(self, config_entry: WiCANConfigEntry, action_defs: list[dict[str, Any]] | None = None) -> None:
        """Initialize steering wheel heater switch entity."""
        description = EntityDescription(
            key="steering_wheel_heater",
            name="Steering Wheel Heater",
            icon="mdi:steering",
        )
        super().__init__(config_entry, description)
        self._action_defs = action_defs or []
        self._attr_unique_id = f"{config_entry.entry_id}_steering_wheel_heater"
        self._attr_is_on = False

    def _get_catalog_actions(self) -> list[dict[str, Any]]:
        catalog = self.coordinator.data.get("cando_catalog")
        return extract_catalog_entries(catalog)

    def _handle_coordinator_update(self) -> None:
        """Handle coordinator update."""
        status = self.coordinator.data.get("status", {})
        if "steering_heater" in status:
            self._attr_is_on = bool(status["steering_heater"])
        self.async_write_ha_state()

    @wican_exception_handler
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on steering wheel heater."""
        actions = self._get_catalog_actions()
        on_def = next((a for a in actions if "steering" in a.get("id", "").lower() and ("on" in a.get("id", "").lower() or "start" in a.get("id", "").lower())), None)
        if not on_def:
            on_def = next((a for a in actions if "steering" in a.get("id", "").lower()), None)

        if not on_def:
            _LOGGER.warning("Steering wheel heater action not defined in catalog for this vehicle")
            return

        success = await self.coordinator.async_execute_action(on_def)
        if success:
            self._attr_is_on = True
            self.async_write_ha_state()

    @wican_exception_handler
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off steering wheel heater."""
        actions = self._get_catalog_actions()
        off_def = next((a for a in actions if "steering" in a.get("id", "").lower() and ("off" in a.get("id", "").lower() or "stop" in a.get("id", "").lower())), None)
        if not off_def:
            off_def = next((a for a in actions if "steering" in a.get("id", "").lower()), None)

        if not off_def:
            _LOGGER.warning("Steering wheel heater action not defined in catalog for this vehicle")
            return

        success = await self.coordinator.async_execute_action(off_def)
        if success:
            self._attr_is_on = False
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore switch state."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_on = last_state.state == "on"
