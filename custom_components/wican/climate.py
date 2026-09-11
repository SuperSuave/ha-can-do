"""Climate platform for WiCAN integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
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

DYNAMIC_CLIMATE_ENTITIES: dict[str, dict[str, WiCANVehicleClimateEntity]] = {}


def _is_climate_action(item: dict) -> bool:
    act_id = str(item.get("id", "")).lower()
    act_type = str(item.get("type", "")).lower()
    return "precondition" in act_id or "climate" in act_id or "hvac" in act_id or act_type == "precondition"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: WiCANConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate platform."""
    DYNAMIC_CLIMATE_ENTITIES[config_entry.entry_id] = {}

    catalog = config_entry.runtime_data.coordinator.data.get("cando_catalog")
    has_climate = False
    matching_actions = []

    if catalog:
        entries = catalog.get("entries", catalog) if isinstance(catalog, dict) else catalog
        if isinstance(entries, list):
            matching_actions = [item for item in entries if isinstance(item, dict) and _is_climate_action(item)]
            has_climate = len(matching_actions) > 0

    if has_climate:
        entity = WiCANVehicleClimateEntity(config_entry, matching_actions)
        DYNAMIC_CLIMATE_ENTITIES[config_entry.entry_id]["climate"] = entity
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

        matching = [item for item in cat_entries if isinstance(item, dict) and _is_climate_action(item)]
        registered = DYNAMIC_CLIMATE_ENTITIES[config_entry.entry_id]
        if matching:
            if "climate" in registered:
                registered["climate"]._action_defs = matching
            else:
                entity = WiCANVehicleClimateEntity(config_entry, matching)
                registered["climate"] = entity
                async_add_entities([entity])

    unsub = async_dispatcher_connect(hass, DOMAIN, handle_catalog_update)
    config_entry.async_on_unload(unsub)


class WiCANVehicleClimateEntity(WiCANEntity, ClimateEntity, RestoreEntity):
    """Vehicle Climate / Preconditioning Entity."""

    _attr_has_entity_name = True
    _attr_name = "Climate Preconditioning"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 16.0
    _attr_max_temp = 28.0
    _attr_target_temperature_step = 0.5
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT_COOL]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, config_entry: WiCANConfigEntry, action_defs: list[dict[str, Any]] | None = None) -> None:
        """Initialize vehicle climate entity."""
        description = EntityDescription(
            key="vehicle_climate",
            name="Climate Preconditioning",
            icon="mdi:fan",
        )
        super().__init__(config_entry, description)
        self._action_defs = action_defs or []
        self._attr_unique_id = f"{config_entry.entry_id}_vehicle_climate"
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_target_temperature = 21.0
        self._attr_current_temperature = None

    def _handle_coordinator_update(self) -> None:
        """Handle coordinator update."""
        status = self.coordinator.data.get("status", {})

        if "t_cab" in status:
            try:
                self._attr_current_temperature = float(status["t_cab"])
            except (ValueError, TypeError):
                pass

        if status.get("precondition_active") is True:
            self._attr_hvac_mode = HVACMode.HEAT_COOL
        elif status.get("precondition_active") is False:
            self._attr_hvac_mode = HVACMode.OFF

        self.async_write_ha_state()

    @wican_exception_handler
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            stop_def = next((a for a in self._action_defs if "stop" in a.get("id", "").lower() or a.get("state") is False), None)
            if stop_def:
                await self.coordinator.async_execute_action(stop_def)
            else:
                await self.coordinator.async_trigger_precondition(False)
            self._attr_hvac_mode = HVACMode.OFF
        else:
            start_def = next((a for a in self._action_defs if "start" in a.get("id", "").lower() or a.get("state") is True), None)
            if start_def:
                await self.coordinator.async_execute_action(start_def)
            else:
                await self.coordinator.async_trigger_precondition(True)
            self._attr_hvac_mode = HVACMode.HEAT_COOL
        self.async_write_ha_state()

    @wican_exception_handler
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature."""
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            self._attr_target_temperature = temp
            self.async_write_ha_state()

    @wican_exception_handler
    async def async_turn_on(self) -> None:
        """Turn climate preconditioning on."""
        await self.async_set_hvac_mode(HVACMode.HEAT_COOL)

    @wican_exception_handler
    async def async_turn_off(self) -> None:
        """Turn climate preconditioning off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_added_to_hass(self) -> None:
        """Restore climate state."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            if last_state.state in (HVACMode.HEAT_COOL, HVACMode.OFF):
                self._attr_hvac_mode = HVACMode(last_state.state)
            if "temperature" in last_state.attributes:
                try:
                    self._attr_target_temperature = float(last_state.attributes["temperature"])
                except (ValueError, TypeError):
                    pass
