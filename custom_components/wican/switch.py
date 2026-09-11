"""Switch platform for WiCAN integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up switch platform."""
    entities = [
        WiCANSteeringWheelHeaterSwitchEntity(config_entry),
    ]
    async_add_entities(entities)


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

    def _handle_coordinator_update(self) -> None:
        """Handle coordinator update."""
        status = self.coordinator.data.get("status", {})
        if "steering_heater" in status:
            self._attr_is_on = bool(status["steering_heater"])
        self.async_write_ha_state()

    @wican_exception_handler
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on steering wheel heater."""
        action_payload = {
            "id": "act_steering_wheel_heater_toggle",
            "name": "Steering Wheel Heater Toggle",
            "type": "can_tx",
            "can_id": "0x496",
            "steps": [{"payload": "12 00 00 00 00 00 00 00", "repeat": 2}],
        }
        success = await self.coordinator.async_execute_action(action_payload)
        if success:
            self._attr_is_on = True
            self.async_write_ha_state()

    @wican_exception_handler
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off steering wheel heater."""
        action_payload = {
            "id": "act_steering_wheel_heater_toggle",
            "name": "Steering Wheel Heater Toggle",
            "type": "can_tx",
            "can_id": "0x496",
            "steps": [{"payload": "00 00 00 00 00 00 00 00", "repeat": 2}],
        }
        success = await self.coordinator.async_execute_action(action_payload)
        if success:
            self._attr_is_on = False
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore switch state."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_on = last_state.state == "on"
