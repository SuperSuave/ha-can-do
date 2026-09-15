"""Helper functions and decorators for WiCAN integration."""

from __future__ import annotations

from functools import wraps
import logging
from typing import TYPE_CHECKING, Any, Concatenate, TypeVar

from homeassistant.components import webhook
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.network import NoURLAvailableError, get_url
from yarl import URL

from .const import DOMAIN
from .exceptions import WiCANConnectionError, WiCANError

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from homeassistant.core import HomeAssistant

    from .entity import WiCANEntity

_LOGGER = logging.getLogger(__name__)

_WiCANEntityT = TypeVar("_WiCANEntityT", bound="WiCANEntity")
_P = TypeVar("_P")


def extract_catalog_entries(catalog_data: Any) -> list[dict[str, Any]]:
    """Extract list of catalog entry dicts from catalog JSON payload."""
    if not catalog_data:
        return []
    if isinstance(catalog_data, list):
        return [item for item in catalog_data if isinstance(item, dict)]
    if isinstance(catalog_data, dict):
        for key in ("commands", "entries", "rules", "actions", "conditions"):
            val = catalog_data.get(key)
            if isinstance(val, list):
                return [item for item in val if isinstance(item, dict)]
    return []


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


def clean_mdns_host(host_or_url: str | None) -> str | None:
    """Remove trailing dot from mDNS host or URL string."""
    if not host_or_url:
        return host_or_url
    s = host_or_url.strip()
    if s.endswith("."):
        s = s[:-1]
    return s


def format_friendly_name(key_or_name: Any) -> str:
    """Format snake_case, camelCase, or PID key into a human-readable title."""
    if not key_or_name or str(type(key_or_name)).find("Undefined") != -1 or not isinstance(key_or_name, str):
        return ""

    # Known acronym overrides
    acronyms = {
        "ecu": "ECU",
        "ble": "BLE",
        "vpn": "VPN",
        "wifi": "WiFi",
        "can": "CAN",
        "pid": "PID",
        "rpm": "RPM",
        "maf": "MAF",
        "stft": "STFT",
        "ltft": "LTFT",
        "soc": "SOC",
        "soh": "SOH",
        "hv": "HV",
        "lv": "LV",
        "ac": "AC",
        "dc": "DC",
        "hvac": "HVAC",
        "gps": "GPS",
    }

    # If already formatted with spaces and capitals, preserve it
    if " " in key_or_name and any(c.isupper() for c in key_or_name):
        return key_or_name

    # Replace dashes and underscores with spaces
    cleaned = key_or_name.replace("_", " ").replace("-", " ").strip()

    # Split into words and format
    words = cleaned.split()
    formatted_words = []
    for word in words:
        w_lower = word.lower()
        if w_lower in acronyms:
            formatted_words.append(acronyms[w_lower])
        else:
            formatted_words.append(word.capitalize())

    return " ".join(formatted_words)


def build_webhook_url(base_url: str, webhook_id: str) -> str:
    """Build an absolute webhook URL from a base URL and webhook id."""
    return str(URL(base_url) / webhook.async_generate_path(webhook_id).lstrip("/"))


def _ensure_allowed_webhook_scheme(url: str, *, allowed_schemes: set[str]) -> str:
    """Validate webhook URL scheme against an allowed set."""
    try:
        parsed = URL(url)
    except ValueError as err:
        raise NoURLAvailableError from err

    if parsed.scheme not in allowed_schemes:
        raise NoURLAvailableError

    return str(parsed)


def resolve_local_webhook_url(
    hass: HomeAssistant,
    webhook_id: str,
    *,
    fallback_url: str | None = None,
    require_current_request: bool = False,
) -> str:
    """Resolve a local-only HTTP webhook URL for devices that cannot use HTTPS."""
    try:
        local_base = get_url(
            hass,
            allow_cloud=False,
            allow_ip=True,
            prefer_external=False,
        )
        return _ensure_allowed_webhook_scheme(
            build_webhook_url(local_base, webhook_id),
            allowed_schemes={"http"},
        )
    except NoURLAvailableError as original_error:
        if require_current_request:
            try:
                current_request_base = get_url(
                    hass,
                    require_current_request=True,
                    allow_cloud=False,
                    allow_ip=True,
                    prefer_external=False,
                )
                return _ensure_allowed_webhook_scheme(
                    build_webhook_url(current_request_base, webhook_id),
                    allowed_schemes={"http"},
                )
            except NoURLAvailableError:
                pass

        if fallback_url:
            try:
                return _ensure_allowed_webhook_scheme(
                    fallback_url,
                    allowed_schemes={"http"},
                )
            except NoURLAvailableError:
                pass

        raise original_error


def resolve_external_webhook_url(hass: HomeAssistant, webhook_id: str) -> str:
    """Resolve the preferred external webhook URL for cloud or remote access."""
    external_base = get_url(
        hass,
        allow_ip=False,
        prefer_external=True,
    )
    return _ensure_allowed_webhook_scheme(
        build_webhook_url(external_base, webhook_id),
        allowed_schemes={"http", "https"},
    )


def resolve_external_https_webhook_url(hass: HomeAssistant, webhook_id: str) -> str:
    """Resolve the preferred external HTTPS webhook URL for remote access."""
    external_base = get_url(
        hass,
        allow_ip=False,
        prefer_external=True,
    )
    return _ensure_allowed_webhook_scheme(
        build_webhook_url(external_base, webhook_id),
        allowed_schemes={"https"},
    )


def resolve_device_webhook_urls(
    hass: HomeAssistant,
    webhook_id: str,
    *,
    fallback_url: str | None = None,
    require_current_request: bool = False,
    allow_external_https_fallback: bool = False,
) -> list[str]:
    """Resolve ordered webhook URLs to send to a device.

    Non-Pro devices require a local HTTP webhook URL. Pro devices can also use
    an external HTTPS URL, and may fall back to it when no local HTTP URL is
    available.
    """
    local_url: str | None = None
    local_error: NoURLAvailableError | None = None

    try:
        local_url = resolve_local_webhook_url(
            hass,
            webhook_id,
            fallback_url=fallback_url,
            require_current_request=require_current_request,
        )
    except NoURLAvailableError as err:
        local_error = err
        if not allow_external_https_fallback:
            raise

    external_url: str | None = None
    if allow_external_https_fallback:
        try:
            external_url = resolve_external_https_webhook_url(hass, webhook_id)
        except NoURLAvailableError:
            external_url = None

    urls: list[str] = []
    if local_url:
        urls.append(local_url)
    if external_url and external_url != local_url:
        urls.append(external_url)

    if urls:
        return urls

    if local_error is not None:
        raise local_error

    raise NoURLAvailableError


def resolve_webhook_url(
    hass: HomeAssistant,
    webhook_id: str,
    *,
    fallback_url: str | None = None,
    require_current_request: bool = False,
) -> str:
    """Resolve the best available absolute webhook URL.

    Prefer Home Assistant's normal URL resolution with IPs allowed and internal
    addresses favored, then optionally fall back to the active request host.
    Finally, reuse a previously stored webhook URL if one exists.
    """
    return resolve_local_webhook_url(
        hass,
        webhook_id,
        fallback_url=fallback_url,
        require_current_request=require_current_request,
    )


def wican_exception_handler[WiCANEntityT: "WiCANEntity"](
    func: Callable[Concatenate[_WiCANEntityT, ...], Coroutine[Any, Any, Any]],
) -> Callable[Concatenate[_WiCANEntityT, ...], Coroutine[Any, Any, None]]:
    """Decorate WiCAN calls to handle exceptions consistently.

    This decorator provides centralized error handling for entity methods,
    converting WiCAN-specific exceptions into HomeAssistant exceptions with
    proper translation support.

    Usage:
        @wican_exception_handler
        async def async_turn_on(self, **kwargs) -> None:
            # Implementation that may raise WiCANError
    """

    @wraps(func)
    async def handler(self: _WiCANEntityT, *args: Any, **kwargs: Any) -> None:
        """Handle exceptions from WiCAN operations."""
        try:
            await func(self, *args, **kwargs)
            # Update coordinator listeners after successful operation
            if hasattr(self, "coordinator"):
                self.coordinator.async_update_listeners()
        except WiCANConnectionError as error:
            # Connection errors - mark coordinator as failed
            if hasattr(self, "coordinator"):
                self.coordinator.last_update_success = False
                self.coordinator.async_update_listeners()
            _LOGGER.exception("Connection error in %s", func.__name__)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="connection_error",
                translation_placeholders={"error": str(error)},
            ) from error
        except WiCANError as error:
            # Generic WiCAN errors
            _LOGGER.exception("WiCAN error in %s", func.__name__)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="wican_error",
                translation_placeholders={"error": str(error)},
            ) from error
        except Exception:
            # Unexpected errors - log and re-raise
            _LOGGER.exception("Unexpected error in %s", func.__name__)
            raise

    return handler
