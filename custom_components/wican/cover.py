"""Cover platform for WiCAN integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
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
    """Set up cover platform."""
    entities = [
        WiCANChargePortCoverEntity(config_entry),
    ]
    async_add_entities(entities)


class WiCANChargePortCoverEntity(WiCANEntity, CoverEntity, RestoreEntity):
    """Charge Port Door Cover Entity."""

    _attr_has_entity_name = True
    _attr_name = "Charge Port Door"
    _attr_device_class = CoverDeviceClass.DOOR
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(self, config_entry: WiCANConfigEntry) -> None:
        """Initialize charge port door entity."""
        description = EntityDescription(
            key="charge_port_door",
            name="Charge Port Door",
            icon="mdi:ev-plug-type2",
        )
        super().__init__(config_entry, description)
        self._attr_unique_id = f"{config_entry.entry_id}_charge_port_door"
        self._attr_is_closed = True

    def _handle_coordinator_update(self) -> None:
        """Handle coordinator update."""
        status = self.coordinator.data.get("status", {})
        if "charge_port_open" in status:
            self._attr_is_closed = not bool(status["charge_port_open"])
        self.async_write_ha_state()

    @wican_exception_handler
    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open charge port door."""
        action_payload = {
            "id": "act_charge_port_door_open",
            "name": "Charge Port Door Open / Release",
            "type": "can_tx",
            "can_id": "0x594",
            "steps": [{"payload": "01 00 00 00 00 00 00 00", "repeat": 2}],
        }
        success = await self.coordinator.async_execute_action(action_payload)
        if success:
            self._attr_is_closed = False
            self.async_write_ha_state()

    @wican_exception_handler
    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close charge port door."""
        action_payload = {
            "id": "act_charge_port_door_close",
            "name": "Charge Port Door Close",
            "type": "can_tx",
            "can_id": "0x594",
            "steps": [{"payload": "00 00 00 00 00 00 00 00", "repeat": 2}],
        }
        success = await self.coordinator.async_execute_action(action_payload)
        if success:
            self._attr_is_closed = True
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore cover state."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_closed = last_state.state == "closed"
