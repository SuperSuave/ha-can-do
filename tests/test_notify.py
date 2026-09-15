"""Test the WiCAN notify platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_notify_entities_created(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test notify entities are created from OSD popup catalog items."""
    entity_registry = er.async_get(hass)

    popup_notify = entity_registry.async_get("notify.wican_device_cluster_telemetry_toast")
    assert popup_notify is not None
    assert popup_notify.unique_id.endswith("_notify_cluster_telemetry_popup")


async def test_notify_send_message(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test sending notification message calls async_execute_action."""
    coordinator = init_integration.runtime_data.coordinator

    with patch.object(coordinator, "async_execute_action", new_callable=AsyncMock, return_value=True) as mock_action:
        await hass.services.async_call(
            "notify",
            "send_message",
            {
                "entity_id": "notify.wican_device_cluster_telemetry_toast",
                "message": "Battery charging at 100kW",
                "title": "EV Status",
            },
            blocking=True,
        )

        mock_action.assert_awaited_once_with({
            "id": "cluster_telemetry_popup",
            "action": "popup",
            "message": "Battery charging at 100kW",
            "title": "EV Status",
        })
