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
from .helpers import extract_catalog_entries, format_friendly_name, wican_exception_handler

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import WiCANConfigEntry

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 0

DYNAMIC_BUTTON_ENTITIES: dict[str, dict[str, WiCANActionButtonEntity]] = {}


def _is_action_entry(item: dict) -> bool:
    if not isinstance(item, dict):
        return False
    roles = item.get("roles")
    if roles and isinstance(roles, list):
        return "action" in roles
    entry_type = str(item.get("type", "")).lower()
    return entry_type in ("can_tx", "webhook", "mqtt", "precondition")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: WiCANConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button platform."""
    DYNAMIC_BUTTON_ENTITIES[config_entry.entry_id] = {}

    entities = []
    registered = DYNAMIC_BUTTON_ENTITIES[config_entry.entry_id]

    catalog = config_entry.runtime_data.coordinator.data.get("cando_catalog")
    catalog_entries = extract_catalog_entries(catalog)

    for item in catalog_entries:
        if _is_action_entry(item):
            act_id = item.get("id")
            if act_id and act_id not in registered:
                entity = WiCANActionButtonEntity(config_entry, item)
                registered[act_id] = entity
                entities.append(entity)

    if entities:
        async_add_entities(entities)

    @callback
    def handle_catalog_update(webhook_id, data):
        if webhook_id != config_entry.runtime_data.webhook_id:
            return
        cat = data.get("cando_catalog")
        if not cat:
            return
        cat_entries = extract_catalog_entries(cat)

        new_entities = []
        for item in cat_entries:
            if _is_action_entry(item):
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

        clean_key = act_id[4:] if act_id.startswith("act_") else act_id

        description = EntityDescription(
            key=clean_key,
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
