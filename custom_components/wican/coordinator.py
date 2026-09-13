"""DataUpdateCoordinator for WiCAN integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from yarl import URL

from .const import DOMAIN, WICAN_DATA_UPDATE_INTERVAL

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import WiCANConfigEntry

_LOGGER = logging.getLogger(__name__)

# WiCAN is push-based via webhooks, so we don't need frequent polling
# This is just for fallback/health check
UPDATE_INTERVAL = timedelta(seconds=WICAN_DATA_UPDATE_INTERVAL)


class WiCANDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching WiCAN data."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: WiCANConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.config_entry = config_entry
        self._data: dict[str, Any] = {}

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            config_entry=config_entry,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from WiCAN device.

        This is a push-based integration, but we also poll /api/can_states
        and /load_cando_catalog when available.
        """
        can_states = await self.async_fetch_can_states()
        if can_states is not None:
            self._data["can_states"] = can_states

        catalog = await self.async_fetch_cando_catalog()
        if catalog is not None:
            self._data["cando_catalog"] = catalog

        return self._data

    def _get_device_base_url(self) -> str | None:
        """Get base URL for device API calls."""
        if hasattr(self.config_entry, "runtime_data") and self.config_entry.runtime_data:
            host = (
                self.config_entry.runtime_data.device_host
                or self.config_entry.runtime_data.device_ip
            )
            if host:
                return host if host.startswith(("http://", "https://")) else f"http://{host}"

        host = (
            self.config_entry.data.get("host")
            or self.config_entry.data.get("ip")
            or self.config_entry.data.get("mdns")
        )
        if host:
            return host if host.startswith(("http://", "https://")) else f"http://{host}"

        return None

    async def async_fetch_can_states(self) -> dict[str, Any] | None:
        """Fetch CAN ID message states from /api/can_states endpoint."""
        base_url = self._get_device_base_url()
        if not base_url:
            return None

        try:
            url = str(URL(base_url).with_path("/api/can_states"))
            session = async_get_clientsession(self.hass)
            async with asyncio.timeout(10):
                response = await session.get(url, ssl=False)
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, dict):
                        return data
        except Exception as err:
            _LOGGER.debug("Failed to fetch CAN states from %s: %s", base_url, err)

        return None

    async def async_fetch_cando_catalog(self) -> dict[str, Any] | list[Any] | None:
        """Fetch CAN Do catalog from /load_cando_catalog endpoint."""
        base_url = self._get_device_base_url()
        if not base_url:
            return None

        try:
            url = str(URL(base_url).with_path("/load_cando_catalog"))
            session = async_get_clientsession(self.hass)
            async with asyncio.timeout(10):
                response = await session.get(url)
                if response.status == 200:
                    data = await response.json()
                    return data
        except Exception as err:
            _LOGGER.debug("Failed to fetch CAN Do catalog from %s: %s", base_url, err)

        return None

    async def async_config_entry_first_refresh(self) -> None:
        """Perform first refresh of the coordinator.

        For WiCAN, this is a push-based integration, so we don't poll for data.
        This method initializes the coordinator with empty data and succeeds immediately.
        Entities will be created and will update when the first webhook push arrives.
        """
        _LOGGER.debug(
            "First refresh for WiCAN coordinator (push-based, no polling required)",
        )
        # Initialize with empty data - webhook pushes will populate it
        await self.async_refresh()

    def handle_webhook_data(self, data: dict[str, Any]) -> None:
        """Handle incoming webhook data.

        This is called by the webhook handler when new data arrives.
        It updates the coordinator's data and notifies all listeners.
        """
        # Validate device identity before processing data
        self._validate_device_identity(data)

        # Update internal data store
        self._data.update(data)

        # Notify all entities that data has been updated
        self.async_set_updated_data(self._data)

        # Dispatch DOMAIN signal for platform catalog/update listeners
        if hasattr(self.config_entry, "runtime_data") and self.config_entry.runtime_data:
            async_dispatcher_send(self.hass, DOMAIN, self.config_entry.runtime_data.webhook_id, data)

    def _validate_device_identity(self, data: dict[str, Any]) -> None:
        """Ensure device identity hasn't changed.

        Validates that the device_id in the webhook data matches the stored
        device_id from initial configuration. This prevents a different device
        from impersonating the configured device.

        Raises:
            ConfigEntryError: If device_id mismatch is detected.
        """
        # Extract device_id from webhook data (can be in status dict or top-level)
        status = data.get("status", {})
        incoming_device_id = status.get("device_id") or data.get("device_id")

        if not incoming_device_id:
            # No device_id provided - skip validation
            # This maintains backward compatibility with older firmware
            return

        # Get stored device_id from config entry
        stored_device_id = self.config_entry.data.get("device_id")

        if not stored_device_id:
            # First time seeing device_id - this is okay
            # The webhook handler will store it in the config entry
            _LOGGER.debug(
                "No stored device_id yet, accepting incoming device_id: %s",
                incoming_device_id,
            )
            return

        # Validate device_id matches
        if incoming_device_id != stored_device_id:
            _LOGGER.error(
                "Device ID mismatch detected! Expected %s, got %s",
                stored_device_id,
                incoming_device_id,
            )
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="device_mismatch",
                translation_placeholders={
                    "expected": stored_device_id,
                    "actual": incoming_device_id,
                },
            )

        _LOGGER.debug("Device identity validated: %s", incoming_device_id)

    def normalize_sensor_value(self, key: str, raw_value: Any) -> Any:
        """Normalize raw sensor values.

        Converts string values with unit suffixes to proper numeric types.
        This centralizes value normalization logic for consistency.

        Args:
            key: Sensor key (e.g., "batt_voltage")
            raw_value: Raw value from device

        Returns:
            Normalized value suitable for Home Assistant
        """
        if raw_value is None:
            return None

        # Battery voltage: strip "V" / " V" suffix (any case) and convert to float
        # Handles firmware variants: "12.5V", "12.5 V", "12.5v", " 12.5 V "
        if key == "batt_voltage" and isinstance(raw_value, str):
            _LOGGER.debug("Raw batt_voltage from device: %r", raw_value)
            stripped = raw_value.strip()
            if stripped.upper().endswith("V"):
                numeric_part = stripped[:-1].strip()
                try:
                    return float(numeric_part)
                except ValueError:
                    _LOGGER.warning(
                        "Failed to parse battery voltage: %r (numeric part: %r)",
                        raw_value, numeric_part,
                    )
                    return raw_value

        # Generic numeric string conversion
        if isinstance(raw_value, str):
            # Check if it looks like a number
            cleaned = raw_value.replace(".", "", 1).replace("-", "", 1)
            if cleaned.isdigit():
                try:
                    return float(raw_value) if "." in raw_value else int(raw_value)
                except ValueError:
                    pass

        return raw_value

    def get_sensor_value(self, sensor_key: str) -> Any | None:
        """Get value for a specific sensor."""
        return self._data.get(sensor_key)

    async def async_execute_action(self, action_payload: dict[str, Any]) -> bool:
        """Send an action execution request to the WiCAN device (/test_can_do_action)."""
        base_url = self._get_device_base_url()
        if not base_url:
            _LOGGER.warning("Cannot execute action: base_url not resolved")
            return False

        try:
            url = str(URL(base_url).with_path("/test_can_do_action"))
            session = async_get_clientsession(self.hass)
            async with asyncio.timeout(10):
                response = await session.post(url, json=action_payload, ssl=False)
                if response.status in (200, 201, 204):
                    _LOGGER.info("Successfully executed CAN action on WiCAN device")
                    return True
                _LOGGER.warning("CAN action failed with status %s", response.status)
        except Exception as err:
            _LOGGER.exception("Failed to execute CAN action on WiCAN device: %s", err)

        return False

    async def async_trigger_precondition(self, state: bool | None = None, target_temp: float | None = None) -> bool:
        """Send a precondition toggle command to the WiCAN device (/precondition_toggle)."""
        base_url = self._get_device_base_url()
        if not base_url:
            _LOGGER.warning("Cannot toggle precondition: base_url not resolved")
            return False

        try:
            url = str(URL(base_url).with_path("/precondition_toggle"))
            session = async_get_clientsession(self.hass)
            payload = {}
            if state is not None:
                payload["state"] = "on" if state else "off"
            if target_temp is not None:
                payload["target_temp"] = target_temp
            async with asyncio.timeout(10):
                response = await session.post(url, json=payload, ssl=False)
                if response.status in (200, 201, 204):
                    _LOGGER.info("Successfully toggled precondition on WiCAN device")
                    return True
                _LOGGER.warning("Precondition toggle failed with status %s", response.status)
        except Exception as err:
            _LOGGER.exception("Failed to toggle precondition on WiCAN device: %s", err)

        return False
