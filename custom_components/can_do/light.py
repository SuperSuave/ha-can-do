"""Light platform for WiCAN integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.light import ColorMode, LightEntity
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

DYNAMIC_LIGHT_ENTITIES: dict[str, dict[str, WiCANAmbientLightEntity]] = {}


def _is_ambient_light_action(item: dict) -> bool:
    ha_domain = str(item.get("ha_domain", "")).lower()
    if ha_domain == "light":
        return True
    act_id = str(item.get("id", "")).lower()
    return "ambient" in act_id or "mood" in act_id or "lighting" in act_id


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: WiCANConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up light platform."""
    DYNAMIC_LIGHT_ENTITIES[config_entry.entry_id] = {}

    catalog = config_entry.runtime_data.coordinator.data.get("cando_catalog")
    entries = extract_catalog_entries(catalog)
    matching = [item for item in entries if _is_ambient_light_action(item)]
    has_ambient = len(matching) > 0

    if has_ambient:
        entity = WiCANAmbientLightEntity(config_entry, matching)
        DYNAMIC_LIGHT_ENTITIES[config_entry.entry_id]["ambient"] = entity
        async_add_entities([entity])

    @callback
    def handle_catalog_update(webhook_id, data):
        if webhook_id != config_entry.runtime_data.webhook_id:
            return
        cat = data.get("cando_catalog")
        if not cat:
            return
        cat_entries = extract_catalog_entries(cat)

        matching = [item for item in cat_entries if _is_ambient_light_action(item)]
        registered = DYNAMIC_LIGHT_ENTITIES[config_entry.entry_id]
        if matching:
            if "ambient" in registered:
                registered["ambient"]._action_defs = matching
            else:
                entity = WiCANAmbientLightEntity(config_entry, matching)
                registered["ambient"] = entity
                async_add_entities([entity])

    unsub = async_dispatcher_connect(hass, DOMAIN, handle_catalog_update)
    config_entry.async_on_unload(unsub)


class WiCANAmbientLightEntity(WiCANEntity, LightEntity, RestoreEntity):
    """Interior Ambient Mood Lighting Entity."""

    _attr_has_entity_name = True
    _attr_name = "Interior Ambient Mood Lighting"
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF

    def __init__(self, config_entry: WiCANConfigEntry, action_defs: list[dict[str, Any]] | None = None) -> None:
        """Initialize ambient light entity."""
        description = EntityDescription(
            key="ambient_light",
            name="Interior Ambient Mood Lighting",
            icon="mdi:car-light-ambient",
        )
        super().__init__(config_entry, description)
        self._action_defs = action_defs or []
        self._attr_unique_id = f"{config_entry.entry_id}_ambient_light"
        self._attr_is_on = False

    def _get_catalog_actions(self) -> list[dict[str, Any]]:
        catalog = self.coordinator.data.get("cando_catalog")
        return extract_catalog_entries(catalog)

    def _handle_coordinator_update(self) -> None:
        """Handle coordinator update."""
        status = self.coordinator.data.get("status", {})
        if "ambient_light_on" in status:
            self._attr_is_on = bool(status["ambient_light_on"])
        self.async_write_ha_state()

    @wican_exception_handler
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on interior ambient lighting."""
        actions = self._get_catalog_actions()
        on_def = next((a for a in actions if ("ambient" in a.get("id", "").lower() or "mood" in a.get("id", "").lower()) and "off" not in a.get("id", "").lower()), None)

        if not on_def:
            _LOGGER.warning("No ambient light on action defined in catalog for this vehicle")
            return

        success = await self.coordinator.async_execute_action(on_def)
        if success:
            self._attr_is_on = True
            self.async_write_ha_state()

    @wican_exception_handler
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off interior ambient lighting."""
        actions = self._get_catalog_actions()
        off_def = next((a for a in actions if ("ambient" in a.get("id", "").lower() or "mood" in a.get("id", "").lower()) and "off" in a.get("id", "").lower()), None)

        if not off_def:
            off_def = next((a for a in actions if "ambient" in a.get("id", "").lower() or "mood" in a.get("id", "").lower()), None)

        if not off_def:
            _LOGGER.warning("No ambient light off action defined in catalog for this vehicle")
            return

        success = await self.coordinator.async_execute_action(off_def)
        if success:
            self._attr_is_on = False
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore light state."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_on = last_state.state == "on"
