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


async def test_seat_comfort_select_entities(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test driver and passenger seat comfort dynamic select entities with heat and cool."""
    coordinator = init_integration.runtime_data.coordinator
    catalog_data = [
        {
            "id": "drivers_seat_comfort",
            "name": "Driver Seat Comfort",
            "ha_domain": "select",
            "state_can_id": "0x496",
            "options": [
                {"label": "Off", "match_payload": "16 * * * * * * *"},
                {"label": "High Heat", "match_payload": "46 * * * * * * *"},
                {"label": "Low Cool", "match_payload": "1E * * * * * * *"},
            ],
        },
        {
            "id": "passengers_seat_comfort",
            "name": "Passenger Seat Comfort",
            "ha_domain": "select",
            "state_can_id": "0x475",
            "options": [
                {"label": "Off", "match_payload": "16 * * * * * * *"},
                {"label": "Medium Heat", "match_payload": "4E * * * * * * *"},
                {"label": "High Cool", "match_payload": "2E * * * * * * *"},
            ],
        },
    ]
    coordinator.handle_webhook_data({"cando_catalog": catalog_data})
    await hass.async_block_till_done()

    driver_state = hass.states.get("select.wican_device_driver_seat_comfort")
    assert driver_state is not None
    assert driver_state.attributes["options"] == ["Off", "High Heat", "Low Cool"]

    pass_state = hass.states.get("select.wican_device_passenger_seat_comfort")
    assert pass_state is not None
    assert pass_state.attributes["options"] == ["Off", "Medium Heat", "High Cool"]

    # Test CAN state matching for cooling
    coordinator.handle_webhook_data({
        "can_states": {
            "0x496": {"data": "1E 00 00 00 00 00 00 00"},
            "0x475": {"data": "2E 00 00 00 00 00 00 00"},
        }
    })
    await hass.async_block_till_done()

    driver_updated = hass.states.get("select.wican_device_driver_seat_comfort")
    assert driver_updated.state == "Low Cool"

    pass_updated = hass.states.get("select.wican_device_passenger_seat_comfort")
    assert pass_updated.state == "High Cool"
