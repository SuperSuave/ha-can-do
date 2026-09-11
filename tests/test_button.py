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
    state = hass.states.get("button.wican_device_hazard_lights_flash")
    assert state is not None

    with patch(
        "custom_components.wican.coordinator.WiCANDataUpdateCoordinator.async_execute_action",
        return_value=True,
    ) as mock_execute:
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.wican_device_hazard_lights_flash"},
            blocking=True,
        )
        assert mock_execute.called
