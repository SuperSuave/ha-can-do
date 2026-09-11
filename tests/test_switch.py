"""Test the WiCAN switch platform."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_switch_entity_controls(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test switch entity creation, turn_on and turn_off actions."""
    coordinator = init_integration.runtime_data.coordinator
    catalog_data = [{"id": "act_steering_wheel_heater_toggle", "name": "Steering Heater", "type": "can_tx"}]
    coordinator.handle_webhook_data({"cando_catalog": catalog_data})
    await hass.async_block_till_done()

    state = hass.states.get("switch.wican_device_steering_wheel_heater")
    assert state is not None

    with patch(
        "custom_components.wican.coordinator.WiCANDataUpdateCoordinator.async_execute_action",
        return_value=True,
    ) as mock_execute:
        # Turn on
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": "switch.wican_device_steering_wheel_heater"},
            blocking=True,
        )
        assert mock_execute.called
        state_on = hass.states.get("switch.wican_device_steering_wheel_heater")
        assert state_on.state == "on"

        # Turn off
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": "switch.wican_device_steering_wheel_heater"},
            blocking=True,
        )
        state_off = hass.states.get("switch.wican_device_steering_wheel_heater")
        assert state_off.state == "off"
