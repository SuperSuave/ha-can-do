"""Binary sensor platform for WiCAN integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.restore_state import RestoreEntity

from .attributes import BINARY_SENSOR_DESCRIPTIONS, WiCANBinarySensorEntityDescription, get_sensor_attributes
from .const import DOMAIN
from .entity import WiCANEntity

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import WiCANConfigEntry

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 0

TRUE_STRINGS = {"enable", "true", "online"}


def is_true_status(value: str) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in TRUE_STRINGS
    return bool(value)


def _is_condition_entry(item: dict) -> bool:
    if not isinstance(item, dict):
        return False
    roles = item.get("roles")
    if roles and isinstance(roles, list):
        return "condition" in roles
    entry_type = str(item.get("type", "")).lower()
    return entry_type in ("can_state", "voltage", "speed_zero", "param_range", "day_of_week", "time_window")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: WiCANConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""

    entities: list[BinarySensorEntity] = [
        WiCANBinarySensorEntity(config_entry, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    ]

    created_cond_ids: set[str] = set()

    catalog = config_entry.runtime_data.coordinator.data.get("cando_catalog")
    if catalog:
        entries = catalog.get("entries", catalog) if isinstance(catalog, dict) else catalog
        if isinstance(entries, list):
            for item in entries:
                if _is_condition_entry(item):
                    cond_id = item.get("id")
                    if cond_id and cond_id not in created_cond_ids:
                        created_cond_ids.add(cond_id)
                        entities.append(WiCANCanConditionBinarySensorEntity(config_entry, item))

    async_add_entities(entities)

    @callback
    def handle_catalog_update(webhook_id, data):
        if webhook_id != config_entry.runtime_data.webhook_id:
            return
        cat = data.get("cando_catalog")
        if not cat:
            return
        cat_entries = cat.get("entries", cat) if isinstance(cat, dict) else cat
        if not isinstance(cat_entries, list):
            return

        new_entities = []
        for item in cat_entries:
            if _is_condition_entry(item):
                cond_id = item.get("id")
                if cond_id and cond_id not in created_cond_ids:
                    created_cond_ids.add(cond_id)
                    new_entities.append(WiCANCanConditionBinarySensorEntity(config_entry, item))

        if new_entities:
            async_add_entities(new_entities)

    unsub = async_dispatcher_connect(hass, DOMAIN, handle_catalog_update)
    config_entry.async_on_unload(unsub)


class WiCANBinarySensorEntity(WiCANEntity, BinarySensorEntity, RestoreEntity):
    """A binary sensor entity."""

    __slots__ = ("_attr_extra_state_attributes", "_attr_is_on")

    entity_description: WiCANBinarySensorEntityDescription

    def __init__(self, config_entry, entity_description):
        super().__init__(config_entry, entity_description)
        self._attr_unique_id = f"{config_entry.entry_id}_{entity_description.key}"
        self._attr_is_on = None
        self._attr_extra_state_attributes = None

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        key = self.entity_description.key
        status = self.coordinator.data.get("status", {})

        if key in status:
            self._attr_is_on = is_true_status(status[key])
            self._attr_extra_state_attributes = get_sensor_attributes(key, self.coordinator.data)

        self.async_write_ha_state()

    @callback
    def _async_handle_event(self, webhook_id: str, data) -> None:
        """Handle webhook event (backward compatibility)."""

    async def async_added_to_hass(self) -> None:
        """Restore entity state."""
        last_state = await self.async_get_last_state()
        if last_state is not None and self._attr_is_on is None:
            self._attr_is_on = last_state.state == "on"
        await super().async_added_to_hass()


def match_can_payload(raw_hex: str, pattern: str) -> bool:
    """Check if raw hex string matches pattern (e.g. '* * 00 * * * * *' or '!12 *')."""
    if not raw_hex or not pattern:
        return False

    raw_clean = raw_hex.replace(" ", "").upper()
    bytes_raw = [raw_clean[i:i + 2] for i in range(0, len(raw_clean), 2)]
    pattern_parts = pattern.strip().split()

    if len(pattern_parts) > len(bytes_raw):
        return False

    for p, r in zip(pattern_parts, bytes_raw):
        p = p.upper()
        if p == "*":
            continue
        if p.startswith("!"):
            if r == p[1:]:
                return False
        elif p != r:
            return False

    return True


class WiCANCanConditionBinarySensorEntity(WiCANEntity, BinarySensorEntity, RestoreEntity):
    @callback
    def _async_handle_event(self, webhook_id: str, data: dict[str, str]) -> None:
        pass

    """Binary sensor for CAN Do catalog conditions based on CAN state matching."""

    __slots__ = ("_attr_extra_state_attributes", "_attr_is_on", "_condition_def")

    def __init__(self, config_entry: WiCANConfigEntry, condition_def: dict) -> None:
        cond_id = condition_def.get("id", "unknown")
        cond_name = condition_def.get("name", cond_id)
        description = WiCANBinarySensorEntityDescription(
            key=f"cando_{cond_id}",
            name=f"CAN Condition: {cond_name}",
            icon="mdi:car-cog",
        )
        super().__init__(config_entry, description)
        self._condition_def = condition_def
        self._attr_unique_id = f"{config_entry.entry_id}_cando_cond_{cond_id}"
        self._attr_is_on = False
        self._attr_extra_state_attributes = {"condition_id": cond_id, "definition": condition_def}

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from coordinator."""
        cond_type = self._condition_def.get("type")
        status = self.coordinator.data.get("status", {})
        can_states = self.coordinator.data.get("can_states", {})

        if cond_type == "voltage":
            target_v = float(self._condition_def.get("voltage_val", 12.0))
            direction = self._condition_def.get("voltage_dir", "above")
            raw_v = self.coordinator.normalize_sensor_value("batt_voltage", status.get("batt_voltage"))
            if isinstance(raw_v, (int, float)):
                if direction == "above":
                    self._attr_is_on = raw_v > target_v
                else:
                    self._attr_is_on = raw_v < target_v
                self.async_write_ha_state()
                return

        elif cond_type == "speed_zero":
            autopid = self.coordinator.data.get("autopid_data", {})
            raw_speed = autopid.get("SPEED") if "SPEED" in autopid else autopid.get("vehicle_speed") if "vehicle_speed" in autopid else status.get("speed")
            if raw_speed is not None:
                try:
                    speed_float = float(raw_speed)
                    self._attr_is_on = (speed_float == 0)
                except (ValueError, TypeError):
                    self._attr_is_on = False
            else:
                self._attr_is_on = False
            self.async_write_ha_state()
            return

        target_can_id = self._condition_def.get("can_id")
        match_payload = self._condition_def.get("match_payload")

        if target_can_id and match_payload and isinstance(can_states, dict):
            matched = False
            for can_id_key, state in can_states.items():
                if str(can_id_key).upper() == str(target_can_id).upper():
                    data_hex = state.get("data", "") if isinstance(state, dict) else str(state)
                    if match_can_payload(data_hex, match_payload):
                        matched = True
                        break
            self._attr_is_on = matched
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore entity state."""
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_on = last_state.state == "on"
        await super().async_added_to_hass()
