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
    """Set up climate platform."""
    entity = WiCANVehicleClimateEntity(config_entry)
    async_add_entities([entity])


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

    def __init__(self, config_entry: WiCANConfigEntry) -> None:
        """Initialize vehicle climate entity."""
        description = EntityDescription(
            key="vehicle_climate",
            name="Climate Preconditioning",
            icon="mdi:fan",
        )
        super().__init__(config_entry, description)
        self._attr_unique_id = f"{config_entry.entry_id}_vehicle_climate"
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_target_temperature = 21.0
        self._attr_current_temperature = None

    def _get_catalog_actions(self) -> list[dict[str, Any]]:
        catalog = self.coordinator.data.get("cando_catalog")
        if not catalog:
            return []
        entries = catalog.get("entries", catalog) if isinstance(catalog, dict) else catalog if isinstance(catalog, list) else []
        return [item for item in entries if isinstance(item, dict)]

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
        actions = self._get_catalog_actions()
        if hvac_mode == HVACMode.OFF:
            stop_def = next((a for a in actions if "stop" in a.get("id", "").lower() or a.get("state") is False), None)
            if stop_def:
                await self.coordinator.async_execute_action(stop_def)
            else:
                await self.coordinator.async_trigger_precondition(False)
            self._attr_hvac_mode = HVACMode.OFF
        else:
            start_def = next((a for a in actions if "start" in a.get("id", "").lower() or a.get("state") is True), None)
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
