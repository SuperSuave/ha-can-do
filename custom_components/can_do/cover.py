"""Cover platform for WiCAN integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .entity import WiCANEntity
from .helpers import extract_catalog_entries, wican_exception_handler

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import WiCANConfigEntry

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 0

DYNAMIC_COVER_ENTITIES: dict[str, dict[str, WiCANChargePortCoverEntity]] = {}


def _is_charge_port_action(item: dict) -> bool:
    ha_domain = str(item.get("ha_domain", "")).lower()
    if ha_domain in ("cover", "door"):
        return True
    act_id = str(item.get("id", "")).lower()
    return "charge_port" in act_id or "tailgate" in act_id or "trunk" in act_id or "window" in act_id or "sunroof" in act_id


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: WiCANConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up cover platform."""
    DYNAMIC_COVER_ENTITIES[config_entry.entry_id] = {}

    catalog = config_entry.runtime_data.coordinator.data.get("cando_catalog")
    entries = extract_catalog_entries(catalog)
    matching = [item for item in entries if _is_charge_port_action(item)]
    has_charge_port = len(matching) > 0

    if has_charge_port:
        entity = WiCANChargePortCoverEntity(config_entry, matching)
        DYNAMIC_COVER_ENTITIES[config_entry.entry_id]["charge_port"] = entity
        async_add_entities([entity])

    @callback
    def handle_catalog_update(webhook_id, data):
        if webhook_id != config_entry.runtime_data.webhook_id:
            return
        cat = data.get("cando_catalog")
        if not cat:
            return
        cat_entries = extract_catalog_entries(cat)

        matching = [item for item in cat_entries if _is_charge_port_action(item)]
        registered = DYNAMIC_COVER_ENTITIES[config_entry.entry_id]
        if matching:
            if "charge_port" in registered:
                registered["charge_port"]._action_defs = matching
            else:
                entity = WiCANChargePortCoverEntity(config_entry, matching)
                registered["charge_port"] = entity
                async_add_entities([entity])

    unsub = async_dispatcher_connect(hass, DOMAIN, handle_catalog_update)
    config_entry.async_on_unload(unsub)


class WiCANChargePortCoverEntity(WiCANEntity, CoverEntity, RestoreEntity):
    """Charge Port Door Cover Entity."""

    _attr_has_entity_name = True
    _attr_name = "Charge Port Door"
    _attr_device_class = CoverDeviceClass.DOOR
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(self, config_entry: WiCANConfigEntry, action_defs: list[dict[str, Any]] | None = None) -> None:
        """Initialize charge port door entity."""
        description = EntityDescription(
            key="charge_port_door",
            name="Charge Port Door",
            icon="mdi:ev-plug-type2",
        )
        super().__init__(config_entry, description)
        self._action_defs = action_defs or []
        self._attr_unique_id = f"{config_entry.entry_id}_charge_port_door"
        self._attr_is_closed = True

    def _get_catalog_actions(self) -> list[dict[str, Any]]:
        catalog = self.coordinator.data.get("cando_catalog")
        return extract_catalog_entries(catalog)

    def _handle_coordinator_update(self) -> None:
        """Handle coordinator update."""
        status = self.coordinator.data.get("status", {})
        if "charge_port_open" in status:
            self._attr_is_closed = not bool(status["charge_port_open"])
        self.async_write_ha_state()

    @wican_exception_handler
    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open charge port door."""
        actions = self._get_catalog_actions()
        open_def = next((a for a in actions if "open" in a.get("id", "").lower()), None)

        if not open_def:
            _LOGGER.warning("Charge port open action not defined in catalog for this vehicle")
            return

        success = await self.coordinator.async_execute_action(open_def)
        if success:
            self._attr_is_closed = False
            self.async_write_ha_state()

    @wican_exception_handler
    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close charge port door."""
        actions = self._get_catalog_actions()
        close_def = next((a for a in actions if "close" in a.get("id", "").lower()), None)

        if not close_def:
            _LOGGER.warning("Charge port close action not defined in catalog for this vehicle")
            return

        success = await self.coordinator.async_execute_action(close_def)
        if success:
            self._attr_is_closed = True
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore cover state."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_closed = last_state.state == "closed"
