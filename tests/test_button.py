"""Test the WiCAN button platform."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_button_entity_press(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test button entity creation and press action."""
    coordinator = init_integration.runtime_data.coordinator
    catalog_data = [{"id": "act_hazard_lights_flash", "name": "Hazard Lights Flash", "roles": ["action"], "type": "can_tx"}]
    coordinator.handle_webhook_data({"cando_catalog": catalog_data})
    await hass.async_block_till_done()

    state = hass.states.get("button.wican_device_hazard_lights_flash")
    assert state is not None

    with patch(
        "custom_components.can_do.coordinator.WiCANDataUpdateCoordinator.async_execute_action",
        return_value=True,
    ) as mock_execute:
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.wican_device_hazard_lights_flash"},
            blocking=True,
        )
        assert mock_execute.called
