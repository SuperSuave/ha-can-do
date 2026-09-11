"""Lock platform for WiCAN integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.lock import LockEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .entity import WiCANEntity
from .helpers import wican_exception_handler

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import WiCANConfigEntry

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 0

DYNAMIC_LOCK_ENTITIES: dict[str, dict[str, WiCANVehicleLockEntity]] = {}


def _is_lock_action(item: dict) -> bool:
    act_id = str(item.get("id", "")).lower()
    return "lock" in act_id or "unlock" in act_id


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: WiCANConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up lock platform."""
    DYNAMIC_LOCK_ENTITIES[config_entry.entry_id] = {}

    catalog = config_entry.runtime_data.coordinator.data.get("cando_catalog")
    has_lock = False
    matching = []

    if catalog:
        entries = catalog.get("entries", catalog) if isinstance(catalog, dict) else catalog
        if isinstance(entries, list):
            matching = [item for item in entries if isinstance(item, dict) and _is_lock_action(item)]
            has_lock = len(matching) > 0

    if has_lock:
        entity = WiCANVehicleLockEntity(config_entry, matching)
        DYNAMIC_LOCK_ENTITIES[config_entry.entry_id]["lock"] = entity
        async_add_entities([entity])

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

        matching = [item for item in cat_entries if isinstance(item, dict) and _is_lock_action(item)]
        registered = DYNAMIC_LOCK_ENTITIES[config_entry.entry_id]
        if matching:
            if "lock" in registered:
                registered["lock"]._action_defs = matching
            else:
                entity = WiCANVehicleLockEntity(config_entry, matching)
                registered["lock"] = entity
                async_add_entities([entity])

    unsub = async_dispatcher_connect(hass, DOMAIN, handle_catalog_update)
    config_entry.async_on_unload(unsub)


class WiCANVehicleLockEntity(WiCANEntity, LockEntity, RestoreEntity):
    """Vehicle Lock Entity."""

    _attr_has_entity_name = True
    _attr_name = "Door Locks"

    def __init__(self, config_entry: WiCANConfigEntry, action_defs: list[dict[str, Any]] | None = None) -> None:
        """Initialize vehicle lock entity."""
        description = EntityDescription(
            key="door_locks",
            name="Door Locks",
            icon="mdi:car-door-lock",
        )
        super().__init__(config_entry, description)
        self._action_defs = action_defs or []
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
        lock_def = next((a for a in actions if "lock" in a.get("id", "").lower() and "unlock" not in a.get("id", "").lower()), None)

        if not lock_def:
            _LOGGER.warning("Lock action not defined in catalog for this vehicle")
            return

        success = await self.coordinator.async_execute_action(lock_def)
        if success:
            self._attr_is_locked = True
            self.async_write_ha_state()

    @wican_exception_handler
    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock vehicle doors."""
        actions = self._get_catalog_actions()
        unlock_def = next((a for a in actions if "unlock" in a.get("id", "").lower()), None)

        if not unlock_def:
            _LOGGER.warning("Unlock action not defined in catalog for this vehicle")
            return

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
