"""Notify platform for WiCAN integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.notify import NotifyEntity, NotifyEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN
from .entity import CANDoEntity
from .helpers import extract_catalog_entries, format_friendly_name, wican_exception_handler

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import WiCANConfigEntry

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 0


def _is_notify_entry(item: dict[str, Any]) -> bool:
    """Return True if item should be set up as a notify entity."""
    if not isinstance(item, dict):
        return False
    ha_domain = str(item.get("ha_domain", "")).lower()
    if ha_domain in ("notify", "popup", "toast"):
        return True
    entry_type = str(item.get("type", "")).lower()
    return entry_type in ("popup", "toast")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: WiCANConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WiCAN notify platform."""
    created_ids: set[str] = set()
    entities: list[CANDoNotifyEntity] = []

    catalog = config_entry.runtime_data.coordinator.data.get("cando_catalog")
    catalog_entries = extract_catalog_entries(catalog)

    for item in catalog_entries:
        if _is_notify_entry(item):
            notify_id = item.get("id")
            if notify_id and notify_id not in created_ids:
                created_ids.add(notify_id)
                entities.append(CANDoNotifyEntity(config_entry, item))

    if entities:
        async_add_entities(entities)

    @callback
    def handle_catalog_update(webhook_id: str, data: dict[str, Any]) -> None:
        if webhook_id != config_entry.runtime_data.webhook_id:
            return
        cat = data.get("cando_catalog")
        if not cat:
            return
        cat_entries = extract_catalog_entries(cat)

        new_entities: list[CANDoNotifyEntity] = []
        for item in cat_entries:
            if _is_notify_entry(item):
                notify_id = item.get("id")
                if notify_id and notify_id not in created_ids:
                    created_ids.add(notify_id)
                    new_entities.append(CANDoNotifyEntity(config_entry, item))

        if new_entities:
            async_add_entities(new_entities)

    unsub = async_dispatcher_connect(hass, DOMAIN, handle_catalog_update)
    config_entry.async_on_unload(unsub)


class CANDoNotifyEntity(CANDoEntity, NotifyEntity):
    """Notify entity for WiCAN cluster OSD toasts/popups."""

    _attr_has_entity_name = True

    def __init__(self, config_entry: WiCANConfigEntry, notify_def: dict[str, Any]) -> None:
        """Initialize notify entity."""
        notify_id = notify_def.get("id", "unknown_notify")
        raw_name = notify_def.get("name", notify_id)
        icon = notify_def.get("icon", "mdi:message-text")

        description = NotifyEntityDescription(
            key=f"notify_{notify_id}",
            name=format_friendly_name(raw_name),
            icon=icon,
        )
        super().__init__(config_entry, description)
        self._notify_def = notify_def
        self._attr_unique_id = f"{config_entry.entry_id}_notify_{notify_id}"

    @wican_exception_handler
    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Send notification message to WiCAN device for vehicle OSD popup."""
        payload = {
            "id": self._notify_def.get("id"),
            "action": "popup",
            "message": message,
            "title": title or "Home Assistant",
        }
        _LOGGER.info("Sending vehicle OSD notification via WiCAN: %s", payload)
        await self.coordinator.async_execute_action(payload)
