"""Event platform for WiCAN integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN
from .entity import CANDoEntity
from .helpers import extract_catalog_entries, format_friendly_name

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import WiCANConfigEntry

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 0

EVENT_TYPES = ["pressed", "single", "double", "long_press", "triggered"]


def _is_event_entry(item: dict[str, Any]) -> bool:
    """Return True if item should be set up as an event entity."""
    if not isinstance(item, dict):
        return False
    ha_domain = str(item.get("ha_domain", "")).lower()
    if ha_domain == "event":
        return True
    roles = item.get("roles")
    if roles and isinstance(roles, list) and "trigger" in roles:
        return True
    return False


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: WiCANConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WiCAN event platform."""
    created_event_ids: set[str] = set()
    entities: list[WiCANEventEntity] = []

    catalog = config_entry.runtime_data.coordinator.data.get("cando_catalog")
    catalog_entries = extract_catalog_entries(catalog)

    for item in catalog_entries:
        if _is_event_entry(item):
            evt_id = item.get("id")
            if evt_id and evt_id not in created_event_ids:
                created_event_ids.add(evt_id)
                entities.append(WiCANEventEntity(config_entry, item))

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

        new_entities: list[WiCANEventEntity] = []
        for item in cat_entries:
            if _is_event_entry(item):
                evt_id = item.get("id")
                if evt_id and evt_id not in created_event_ids:
                    created_event_ids.add(evt_id)
                    new_entities.append(WiCANEventEntity(config_entry, item))

        if new_entities:
            async_add_entities(new_entities)

    unsub = async_dispatcher_connect(hass, DOMAIN, handle_catalog_update)
    config_entry.async_on_unload(unsub)


class WiCANEventEntity(CANDoEntity, EventEntity):
    """Event entity for WiCAN triggers."""

    _attr_has_entity_name = True

    def __init__(self, config_entry: WiCANConfigEntry, event_def: dict[str, Any]) -> None:
        """Initialize WiCAN event entity."""
        evt_id = event_def.get("id", "unknown_event")
        raw_name = event_def.get("name", evt_id)
        icon = event_def.get("icon", "mdi:car-bolt")

        description = EventEntityDescription(
            key=f"evt_{evt_id}",
            name=format_friendly_name(raw_name),
            icon=icon,
            event_types=EVENT_TYPES,
        )
        super().__init__(config_entry, description)
        self._event_def = event_def
        self._attr_unique_id = f"{config_entry.entry_id}_evt_{evt_id}"

    def _handle_coordinator_update(self) -> None:
        """Handle coordinator updates and trigger event if matched."""
        evt_id = self._event_def.get("id")
        status = self.coordinator.data.get("status", {})
        triggers = self.coordinator.data.get("triggers", {})
        events = self.coordinator.data.get("events", {})

        # Check if this trigger or event fired in webhook data
        if evt_id and (evt_id in triggers or evt_id in events or status.get("last_trigger") == evt_id):
            evt_type = (
                triggers.get(evt_id, {}).get("event_type")
                or events.get(evt_id, {}).get("event_type")
                or "triggered"
            )
            if evt_type not in EVENT_TYPES:
                evt_type = "triggered"

            evt_data = {
                "trigger_id": evt_id,
                "raw": triggers.get(evt_id) or events.get(evt_id) or status,
            }
            self._trigger_event(evt_type, evt_data)
            self.async_write_ha_state()
