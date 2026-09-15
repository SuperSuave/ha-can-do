"""Test the WiCAN cover platform."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_cover_entity_creation_and_controls(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test cover entity creation, open and close actions."""
    coordinator = init_integration.runtime_data.coordinator
    catalog_data = [
        {"id": "act_charge_port_door_open", "name": "Charge Port Open", "type": "can_tx"},
        {"id": "act_charge_port_door_close", "name": "Charge Port Close", "type": "can_tx"},
    ]
    coordinator.handle_webhook_data({"cando_catalog": catalog_data})
    await hass.async_block_till_done()

    state = hass.states.get("cover.wican_device_charge_port_door")
    assert state is not None

    with patch(
        "custom_components.can_do.coordinator.WiCANDataUpdateCoordinator.async_execute_action",
        return_value=True,
    ) as mock_execute:
        # Open
        await hass.services.async_call(
            "cover",
            "open_cover",
            {"entity_id": "cover.wican_device_charge_port_door"},
            blocking=True,
        )
        assert mock_execute.called
        state_open = hass.states.get("cover.wican_device_charge_port_door")
        assert state_open.state == "open"

        # Close
        await hass.services.async_call(
            "cover",
            "close_cover",
            {"entity_id": "cover.wican_device_charge_port_door"},
            blocking=True,
        )
        state_closed = hass.states.get("cover.wican_device_charge_port_door")
        assert state_closed.state == "closed"
