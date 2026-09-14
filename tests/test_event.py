"""Test the WiCAN event platform."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.const import CONF_WEBHOOK_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_event_entities_created(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test event entities are created from catalog triggers."""
    entity_registry = er.async_get(hass)

    # Check sw_star button trigger event entity exists
    star_evt = entity_registry.async_get("event.wican_device_star_button")
    assert star_evt is not None
    assert star_evt.unique_id.endswith("_evt_sw_star")


async def test_event_entity_triggers_on_webhook(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_webhook_data: dict,
    hass_client,
) -> None:
    """Test event entity triggers when webhook reports trigger event."""
    entry = init_integration
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    client = await hass_client()

    payload = {
        **mock_webhook_data,
        "triggers": {
            "sw_star": {"event_type": "pressed"},
        },
    }

    resp = await client.post(f"/api/webhook/{webhook_id}", json=payload)
    assert resp.status == 204
    await hass.async_block_till_done()

    state = hass.states.get("event.wican_device_star_button")
    assert state is not None
    assert state.attributes.get("event_type") == "pressed"
