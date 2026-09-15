"""Test the WiCAN light platform."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_light_entity_creation_and_controls(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test light entity creation, turn_on and turn_off actions."""
    coordinator = init_integration.runtime_data.coordinator
    catalog_data = [
        {"id": "act_interior_ambient_mood_lighting", "name": "Ambient Light", "type": "can_tx"},
        {"id": "act_interior_ambient_mood_lighting_off", "name": "Ambient Light Off", "type": "can_tx"},
    ]
    coordinator.handle_webhook_data({"cando_catalog": catalog_data})
    await hass.async_block_till_done()

    state = hass.states.get("light.wican_device_interior_ambient_mood_lighting")
    assert state is not None

    with patch(
        "custom_components.wican.coordinator.WiCANDataUpdateCoordinator.async_execute_action",
        return_value=True,
    ) as mock_execute:
        # Turn on
        await hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": "light.wican_device_interior_ambient_mood_lighting"},
            blocking=True,
        )
        assert mock_execute.called
        state_on = hass.states.get("light.wican_device_interior_ambient_mood_lighting")
        assert state_on.state == "on"

        # Turn off
        await hass.services.async_call(
            "light",
            "turn_off",
            {"entity_id": "light.wican_device_interior_ambient_mood_lighting"},
            blocking=True,
        )
        state_off = hass.states.get("light.wican_device_interior_ambient_mood_lighting")
        assert state_off.state == "off"
