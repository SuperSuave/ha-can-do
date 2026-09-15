"""Test the WiCAN climate platform."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_climate_entity_creation_and_controls(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test climate entity creation, mode change, and temperature setting."""
    coordinator = init_integration.runtime_data.coordinator
    catalog_data = [{"id": "act_climate_precondition_start", "name": "Start Precon", "type": "precondition"}]
    coordinator.handle_webhook_data({"cando_catalog": catalog_data})
    await hass.async_block_till_done()

    state = hass.states.get("climate.wican_device_climate_preconditioning")
    assert state is not None
    assert state.state == HVACMode.OFF

    with patch(
        "custom_components.can_do.coordinator.WiCANDataUpdateCoordinator.async_execute_action",
        return_value=True,
    ) as mock_execute, patch(
        "custom_components.can_do.coordinator.WiCANDataUpdateCoordinator.async_trigger_precondition",
        return_value=True,
    ) as mock_trigger:
        # Turn on
        await hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {
                "entity_id": "climate.wican_device_climate_preconditioning",
                "hvac_mode": HVACMode.HEAT_COOL,
            },
            blocking=True,
        )
        assert mock_execute.called or mock_trigger.called

        # Set temperature
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {
                "entity_id": "climate.wican_device_climate_preconditioning",
                "temperature": 22.5,
            },
            blocking=True,
        )
        updated_state = hass.states.get("climate.wican_device_climate_preconditioning")
        assert updated_state.attributes.get("temperature") == 22.5
