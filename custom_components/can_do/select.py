"""Select platform for WiCAN integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .entity import WiCANEntity
from .helpers import (
    extract_catalog_entries,
    format_friendly_name,
    match_can_payload,
    wican_exception_handler,
)

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import WiCANConfigEntry

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 0

DYNAMIC_SELECT_ENTITIES: dict[str, dict[str, WiCANSelectEntity]] = {}


def _is_select_entry(item: dict[str, Any]) -> bool:
    """Return True if item should be set up as a select entity."""
    if not isinstance(item, dict):
        return False
    item_id = str(item.get("id", "")).lower()
    if item_id.startswith("cond_"):
        return False
    ha_domain = str(item.get("ha_domain", "")).lower()
    if ha_domain == "select":
        return True
    if "options" in item and isinstance(item["options"], list) and len(item["options"]) > 1:
        if "mood" in item_id or ("ambient" in item_id and "temp" not in item_id):
            return True
    return False


def _get_select_icon(item_id: str, default_icon: str | None = None) -> str:
    """Return an appropriate MDI icon based on the entity key/category."""
    if default_icon:
        return default_icon
    item_lower = item_id.lower()
    if "seat" in item_lower:
        return "mdi:car-seat-heater"
    if "mood" in item_lower or "ambient" in item_lower:
        return "mdi:palette"
    if "charge" in item_lower:
        return "mdi:battery-charging"
    if "sound" in item_lower or "asd" in item_lower:
        return "mdi:volume-high"
    return "mdi:format-list-bulleted"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: WiCANConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select platform dynamically from CAN-Do catalog."""
    DYNAMIC_SELECT_ENTITIES[config_entry.entry_id] = {}
    registered = DYNAMIC_SELECT_ENTITIES[config_entry.entry_id]

    catalog = config_entry.runtime_data.coordinator.data.get("cando_catalog")
    entries = extract_catalog_entries(catalog)
    entities: list[WiCANSelectEntity] = []

    for item in entries:
        if _is_select_entry(item):
            item_id = item.get("id")
            if item_id and item_id not in registered:
                entity = WiCANSelectEntity(config_entry, item)
                if entity.options:
                    registered[item_id] = entity
                    entities.append(entity)

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

        new_entities: list[WiCANSelectEntity] = []
        for item in cat_entries:
            if _is_select_entry(item):
                item_id = item.get("id")
                if item_id:
                    if item_id in registered:
                        registered[item_id].update_select_def(item)
                    else:
                        entity = WiCANSelectEntity(config_entry, item)
                        if entity.options:
                            registered[item_id] = entity
                            new_entities.append(entity)

        if new_entities:
            async_add_entities(new_entities)

    unsub = async_dispatcher_connect(hass, DOMAIN, handle_catalog_update)
    config_entry.async_on_unload(unsub)


class WiCANSelectEntity(WiCANEntity, SelectEntity, RestoreEntity):
    """Dynamic select entity driven by CAN-Do catalog options."""

    _attr_has_entity_name = True

    def __init__(self, config_entry: WiCANConfigEntry, select_def: dict[str, Any]) -> None:
        """Initialize dynamic select entity."""
        item_id = select_def.get("id", "select")
        raw_name = select_def.get("name", item_id)
        icon = _get_select_icon(item_id, select_def.get("icon"))

        # Preserve standard mood light theme key for backward compatibility
        if item_id in ("ambient_mood_lighting", "act_interior_ambient_mood_lighting"):
            clean_key = "mood_light_theme"
            friendly_name = "Mood Light Theme"
        else:
            clean_key = item_id[4:] if item_id.startswith("act_") else item_id
            friendly_name = format_friendly_name(raw_name)

        description = EntityDescription(
            key=clean_key,
            name=friendly_name,
            icon=icon,
        )
        super().__init__(config_entry, description)
        self._select_def = select_def
        self._attr_unique_id = f"{config_entry.entry_id}_{clean_key}"
        self._options_map: dict[str, dict[str, Any]] = {}
        self._build_options(select_def)

    def _build_options(self, select_def: dict[str, Any]) -> None:
        """Build available option list and lookup map from catalog definition."""
        self._options_map.clear()
        options_defs = select_def.get("options", [])
        options_list: list[str] = []
        default_option: str | None = None

        for opt in options_defs:
            if isinstance(opt, dict) and "label" in opt:
                label = str(opt["label"])
                options_list.append(label)
                self._options_map[label] = opt
                if opt.get("default"):
                    default_option = label

        self._attr_options = options_list
        if not self._attr_current_option and options_list:
            self._attr_current_option = default_option or options_list[0]

    def update_select_def(self, select_def: dict[str, Any]) -> None:
        """Update select definition on catalog changes."""
        self._select_def = select_def
        self._build_options(select_def)
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        """Handle coordinator update by matching active CAN state or status."""
        can_states = self.coordinator.data.get("can_states", {})
        status = self.coordinator.data.get("status", {})

        target_can_id = (
            self._select_def.get("state_can_id")
            or self._select_def.get("can_id")
            or self._select_def.get("action_can_id")
        )

        matched_option: str | None = None
        if target_can_id and isinstance(can_states, dict):
            target_can_id_upper = str(target_can_id).upper()
            data_hex = None
            for can_id_key, state in can_states.items():
                if str(can_id_key).upper() == target_can_id_upper:
                    data_hex = state.get("data", "") if isinstance(state, dict) else str(state)
                    break

            if data_hex:
                for label, opt in self._options_map.items():
                    pattern = opt.get("match_payload")
                    if pattern and match_can_payload(data_hex, pattern):
                        matched_option = label
                        break

        # Fallback to status dict
        if not matched_option and isinstance(status, dict):
            for key in (self.entity_description.key, self._select_def.get("id")):
                if key and key in status and status[key] in self._attr_options:
                    matched_option = status[key]
                    break

        if matched_option:
            self._attr_current_option = matched_option

        self.async_write_ha_state()

    @wican_exception_handler
    async def async_select_option(self, option: str) -> None:
        """Select an option and execute the corresponding action."""
        if option not in self._attr_options:
            raise ValueError(f"Invalid option: {option}")

        opt_def = self._options_map.get(option)
        if not opt_def:
            _LOGGER.warning("Option %s not found in definition for %s", option, self.name)
            return

        action_payload = dict(self._select_def)

        if "steps" in opt_def:
            action_payload["steps"] = opt_def["steps"]
        elif "payload" in opt_def:
            action_payload["steps"] = [{"payload": opt_def["payload"], "repeat": 2}]
        elif "to_payload" in opt_def:
            action_payload["steps"] = [{"payload": opt_def["to_payload"], "repeat": 2}]

        success = await self.coordinator.async_execute_action(action_payload)
        if success:
            self._attr_current_option = option
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore select state on startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in self._attr_options:
            self._attr_current_option = last_state.state
