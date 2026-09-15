"""Test the WiCAN select platform."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_select_entity_options(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test select entity creation and option selection."""
    coordinator = init_integration.runtime_data.coordinator
    catalog_data = [
        {"id": "act_interior_ambient_mood_lighting", "name": "Mood Light", "type": "can_tx", "options": [{"label": "Electric Blue"}]},
        {"id": "act_driver_seat_heater_off", "name": "Driver Seat Heater", "type": "can_tx"},
    ]
    coordinator.handle_webhook_data({"cando_catalog": catalog_data})
    await hass.async_block_till_done()

    state = hass.states.get("select.wican_device_mood_light_theme")
    assert state is not None
    assert "Electric Blue" in state.attributes["options"]

    with patch(
        "custom_components.can_do.coordinator.WiCANDataUpdateCoordinator.async_execute_action",
        return_value=True,
    ) as mock_execute:
        await hass.services.async_call(
            "select",
            "select_option",
            {
                "entity_id": "select.wican_device_mood_light_theme",
                "option": "Electric Blue",
            },
            blocking=True,
        )
        assert mock_execute.called
        state_updated = hass.states.get("select.wican_device_mood_light_theme")
        assert state_updated.state == "Electric Blue"
