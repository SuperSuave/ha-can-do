"""Switch platform for WiCAN integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up switch platform."""
    entity = WiCANSteeringWheelHeaterSwitchEntity(config_entry)
    async_add_entities([entity])


class WiCANSteeringWheelHeaterSwitchEntity(WiCANEntity, SwitchEntity, RestoreEntity):
    """Steering Wheel Heater Switch Entity."""

    _attr_has_entity_name = True
    _attr_name = "Steering Wheel Heater"

    def __init__(self, config_entry: WiCANConfigEntry) -> None:
        """Initialize steering wheel heater switch entity."""
        description = EntityDescription(
            key="steering_wheel_heater",
            name="Steering Wheel Heater",
            icon="mdi:steering",
        )
        super().__init__(config_entry, description)
        self._attr_unique_id = f"{config_entry.entry_id}_steering_wheel_heater"
        self._attr_is_on = False

    def _get_catalog_actions(self) -> list[dict[str, Any]]:
        catalog = self.coordinator.data.get("cando_catalog")
        if not catalog:
            return []
        entries = catalog.get("entries", catalog) if isinstance(catalog, dict) else catalog if isinstance(catalog, list) else []
        return [item for item in entries if isinstance(item, dict)]

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
        toggle_def = next((a for a in actions if "steering" in a.get("id", "").lower()), None)

        if not toggle_def and actions:
            _LOGGER.warning("Steering wheel heater action not defined in catalog for this vehicle")
            return

        if not toggle_def:
            toggle_def = {
                "id": "act_steering_wheel_heater_toggle",
                "name": "Steering Wheel Heater Toggle",
                "type": "can_tx",
                "can_id": "0x496",
                "steps": [{"payload": "12 00 00 00 00 00 00 00", "repeat": 2}],
            }

        success = await self.coordinator.async_execute_action(toggle_def)
        if success:
            self._attr_is_on = True
            self.async_write_ha_state()

    @wican_exception_handler
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off steering wheel heater."""
        actions = self._get_catalog_actions()
        toggle_def = next((a for a in actions if "steering" in a.get("id", "").lower()), None)

        if not toggle_def and actions:
            _LOGGER.warning("Steering wheel heater action not defined in catalog for this vehicle")
            return

        if not toggle_def:
            toggle_def = {
                "id": "act_steering_wheel_heater_toggle",
                "name": "Steering Wheel Heater Toggle",
                "type": "can_tx",
                "can_id": "0x496",
                "steps": [{"payload": "00 00 00 00 00 00 00 00", "repeat": 2}],
            }

        success = await self.coordinator.async_execute_action(toggle_def)
        if success:
            self._attr_is_on = False
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore switch state."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_on = last_state.state == "on"
