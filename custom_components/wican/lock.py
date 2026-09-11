"""Lock platform for WiCAN integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.lock import LockEntity
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
    """Set up lock platform."""
    entity = WiCANVehicleLockEntity(config_entry)
    async_add_entities([entity])


class WiCANVehicleLockEntity(WiCANEntity, LockEntity, RestoreEntity):
    """Vehicle Lock Entity."""

    _attr_has_entity_name = True
    _attr_name = "Door Locks"

    def __init__(self, config_entry: WiCANConfigEntry) -> None:
        """Initialize vehicle lock entity."""
        description = EntityDescription(
            key="door_locks",
            name="Door Locks",
            icon="mdi:car-door-lock",
        )
        super().__init__(config_entry, description)
        self._attr_unique_id = f"{config_entry.entry_id}_door_locks"
        self._attr_is_locked = True

    def _get_catalog_actions(self) -> list[dict[str, Any]]:
        catalog = self.coordinator.data.get("cando_catalog")
        if not catalog:
            return []
        entries = catalog.get("entries", catalog) if isinstance(catalog, dict) else catalog if isinstance(catalog, list) else []
        return [item for item in entries if isinstance(item, dict)]

    def _handle_coordinator_update(self) -> None:
        """Handle coordinator update."""
        can_states = self.coordinator.data.get("can_states", {})
        status = self.coordinator.data.get("status", {})

        if "locked" in status:
            self._attr_is_locked = bool(status["locked"])
        elif "0x540" in can_states or "0X540" in can_states:
            state = can_states.get("0x540") or can_states.get("0X540")
            data_hex = state.get("data", "") if isinstance(state, dict) else str(state)
            if data_hex and not data_hex.startswith("00 00"):
                self._attr_is_locked = True

        self.async_write_ha_state()

    @wican_exception_handler
    async def async_lock(self, **kwargs: Any) -> None:
        """Lock vehicle doors."""
        actions = self._get_catalog_actions()
        lock_def = next((a for a in actions if "lock_all" in a.get("id", "").lower() or (a.get("id", "").lower().startswith("act_door_lock"))), None)

        if not lock_def and actions:
            _LOGGER.warning("Lock action not defined in catalog for this vehicle")
            return

        if not lock_def:
            lock_def = {
                "id": "act_door_lock_all",
                "name": "Door Lock All",
                "type": "can_tx",
                "can_id": "0x540",
                "steps": [{"payload": "01 00 00 00 00 00 00 00", "repeat": 2}],
            }

        success = await self.coordinator.async_execute_action(lock_def)
        if success:
            self._attr_is_locked = True
            self.async_write_ha_state()

    @wican_exception_handler
    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock vehicle doors."""
        actions = self._get_catalog_actions()
        unlock_def = next((a for a in actions if "unlock" in a.get("id", "").lower()), None)

        if not unlock_def and actions:
            _LOGGER.warning("Unlock action not defined in catalog for this vehicle")
            return

        if not unlock_def:
            unlock_def = {
                "id": "act_door_unlock_all",
                "name": "Door Unlock All",
                "type": "can_tx",
                "can_id": "0x540",
                "steps": [{"payload": "02 00 00 00 00 00 00 00", "repeat": 2}],
            }

        success = await self.coordinator.async_execute_action(unlock_def)
        if success:
            self._attr_is_locked = False
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore lock state."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_locked = last_state.state == "locked"
