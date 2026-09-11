"""Light platform for WiCAN integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.light import ColorMode, LightEntity
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
    """Set up light platform."""
    entities = [
        WiCANAmbientLightEntity(config_entry),
    ]
    async_add_entities(entities)


class WiCANAmbientLightEntity(WiCANEntity, LightEntity, RestoreEntity):
    """Interior Ambient Mood Lighting Entity."""

    _attr_has_entity_name = True
    _attr_name = "Interior Ambient Mood Lighting"
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF

    def __init__(self, config_entry: WiCANConfigEntry) -> None:
        """Initialize ambient light entity."""
        description = EntityDescription(
            key="ambient_light",
            name="Interior Ambient Mood Lighting",
            icon="mdi:car-light-ambient",
        )
        super().__init__(config_entry, description)
        self._attr_unique_id = f"{config_entry.entry_id}_ambient_light"
        self._attr_is_on = False

    def _handle_coordinator_update(self) -> None:
        """Handle coordinator update."""
        status = self.coordinator.data.get("status", {})
        if "ambient_light_on" in status:
            self._attr_is_on = bool(status["ambient_light_on"])
        self.async_write_ha_state()

    @wican_exception_handler
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on interior ambient lighting."""
        action_payload = {
            "id": "act_interior_ambient_mood_lighting",
            "name": "Interior Ambient Mood Lighting",
            "type": "can_tx",
            "can_id": "0x4AD",
            "steps": [{"payload": "80 00 F0 0F 00 00 00 00", "repeat": 2}],
        }
        success = await self.coordinator.async_execute_action(action_payload)
        if success:
            self._attr_is_on = True
            self.async_write_ha_state()

    @wican_exception_handler
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off interior ambient lighting."""
        action_payload = {
            "id": "act_interior_ambient_mood_lighting_off",
            "name": "Interior Ambient Mood Lighting Off",
            "type": "can_tx",
            "can_id": "0x4AD",
            "steps": [{"payload": "00 00 00 00 00 00 00 00", "repeat": 2}],
        }
        success = await self.coordinator.async_execute_action(action_payload)
        if success:
            self._attr_is_on = False
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore light state."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_on = last_state.state == "on"
