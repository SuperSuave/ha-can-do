"""Test the WiCAN lock platform."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_lock_entity_creation_and_controls(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test lock entity creation, lock and unlock actions."""
    coordinator = init_integration.runtime_data.coordinator
    catalog_data = [
        {"id": "act_door_lock_all", "name": "Door Lock All", "type": "can_tx"},
        {"id": "act_door_unlock_all", "name": "Door Unlock All", "type": "can_tx"},
    ]
    coordinator.handle_webhook_data({"cando_catalog": catalog_data})
    await hass.async_block_till_done()

    state = hass.states.get("lock.wican_device_door_locks")
    assert state is not None

    with patch(
        "custom_components.can_do.coordinator.WiCANDataUpdateCoordinator.async_execute_action",
        return_value=True,
    ) as mock_execute:
        # Unlock
        await hass.services.async_call(
            "lock",
            "unlock",
            {"entity_id": "lock.wican_device_door_locks"},
            blocking=True,
        )
        assert mock_execute.called
        state_after = hass.states.get("lock.wican_device_door_locks")
        assert state_after.state == "unlocked"

        # Lock
        await hass.services.async_call(
            "lock",
            "lock",
            {"entity_id": "lock.wican_device_door_locks"},
            blocking=True,
        )
        state_locked = hass.states.get("lock.wican_device_door_locks")
        assert state_locked.state == "locked"
