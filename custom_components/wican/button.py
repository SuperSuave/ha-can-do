"""Button platform for WiCAN integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityDescription

from .const import DOMAIN
from .entity import WiCANEntity
from .helpers import format_friendly_name, wican_exception_handler

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import WiCANConfigEntry

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 0

DYNAMIC_BUTTON_ENTITIES: dict[str, dict[str, WiCANActionButtonEntity]] = {}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: WiCANConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button platform."""
    DYNAMIC_BUTTON_ENTITIES[config_entry.entry_id] = {}

    # Static default buttons
    default_buttons = [
        {
            "id": "act_climate_precondition_start",
            "name": "Climate Precondition Start",
            "icon": "mdi:fan",
            "type": "precondition",
            "state": True,
        },
        {
            "id": "act_climate_precondition_stop",
            "name": "Climate Precondition Stop",
            "icon": "mdi:fan-off",
            "type": "precondition",
            "state": False,
        },
        {
            "id": "act_hazard_lights_flash",
            "name": "Hazard Lights Flash",
            "icon": "mdi:car-emergency",
            "type": "can_tx",
            "can_id": "0x582",
            "steps": [{"payload": "01 00 00 00 00 00 00 00", "repeat": 2}],
        },
        {
            "id": "act_horn_flash_panic",
            "name": "Horn & Lights Panic Alarm",
            "icon": "mdi:bugle",
            "type": "can_tx",
            "can_id": "0x7A0",
            "steps": [{"payload": "01 00 00 00 00 00 00 00", "repeat": 2}],
        },
        {
            "id": "act_keepalive_wakeup_ping",
            "name": "Keepalive / Wakeup Ping",
            "icon": "mdi:signal-variant",
            "type": "can_tx",
            "can_id": "0x7DF",
            "steps": [{"payload": "02 01 00 00 00 00 00 00", "repeat": 2}],
        },
    ]

    entities = []
    for btn_def in default_buttons:
        entity = WiCANActionButtonEntity(config_entry, btn_def)
        DYNAMIC_BUTTON_ENTITIES[config_entry.entry_id][btn_def["id"]] = entity
        entities.append(entity)

    # Process catalog actions dynamically
    catalog = config_entry.runtime_data.coordinator.data.get("cando_catalog")
    if catalog:
        entries = catalog.get("entries", catalog) if isinstance(catalog, dict) else catalog
        if isinstance(entries, list):
            for item in entries:
                if isinstance(item, dict) and "action" in item.get("roles", ["action"]):
                    act_id = item.get("id")
                    if act_id and act_id not in DYNAMIC_BUTTON_ENTITIES[config_entry.entry_id]:
                        entity = WiCANActionButtonEntity(config_entry, item)
                        DYNAMIC_BUTTON_ENTITIES[config_entry.entry_id][act_id] = entity
                        entities.append(entity)

    async_add_entities(entities)

    # Connect catalog updates
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

        new_entities = []
        registered = DYNAMIC_BUTTON_ENTITIES[config_entry.entry_id]
        for item in cat_entries:
            if isinstance(item, dict) and "action" in item.get("roles", ["action"]):
                act_id = item.get("id")
                if act_id and act_id not in registered:
                    entity = WiCANActionButtonEntity(config_entry, item)
                    registered[act_id] = entity
                    new_entities.append(entity)

        if new_entities:
            async_add_entities(new_entities)

    unsub = async_dispatcher_connect(hass, DOMAIN, handle_catalog_update)
    config_entry.async_on_unload(unsub)


class WiCANActionButtonEntity(WiCANEntity, ButtonEntity):
    """Button entity for CAN Do actions."""

    _attr_has_entity_name = True

    def __init__(self, config_entry: WiCANConfigEntry, action_def: dict[str, Any]) -> None:
        """Initialize button entity."""
        act_id = action_def.get("id", "unknown_action")
        raw_name = action_def.get("name", act_id)
        icon = action_def.get("icon", "mdi:car-cog")

        description = EntityDescription(
            key=f"act_{act_id}",
            name=format_friendly_name(raw_name),
            icon=icon,
        )
        super().__init__(config_entry, description)
        self._action_def = action_def
        self._attr_unique_id = f"{config_entry.entry_id}_act_{act_id}"

    @wican_exception_handler
    async def async_press(self) -> None:
        """Handle the button press."""
        act_type = self._action_def.get("type")
        if act_type == "precondition":
            state = self._action_def.get("state")
            await self.coordinator.async_trigger_precondition(state)
        else:
            await self.coordinator.async_execute_action(self._action_def)
