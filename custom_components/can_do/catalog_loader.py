"""CAN Do Message Catalog loader for WiCAN integration.

Loads vehicle catalog definitions from the bundled can_do_catalog.json file,
sourced from the CAN Do Message Catalog repository:
https://github.com/SuperSuave/CAN-Do-Message-Catalog/raw/refs/heads/main/can_do_catalog.json

The integration fetches updates from GitHub on reload and updates the local cache if changes are detected.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from .helpers import extract_catalog_entries

if TYPE_CHECKING:
    from aiohttp import ClientSession

_LOGGER = logging.getLogger(__name__)

CATALOG_GITHUB_URL: Final[str] = (
    "https://raw.githubusercontent.com/SuperSuave/CAN-Do-Message-Catalog/main/can_do_catalog.json"
)
CATALOG_GITHUB_URL_ALT: Final[str] = (
    "https://github.com/SuperSuave/CAN-Do-Message-Catalog/raw/refs/heads/main/can_do_catalog.json"
)

GITHUB_FETCH_TIMEOUT: Final[int] = 10


def _get_catalog_file_path() -> Path:
    """Get path to the local can_do_catalog.json file."""
    return Path(__file__).parent / "data" / "can_do_catalog.json"


def _compute_hash(data: bytes) -> str:
    """Compute SHA256 hash of data."""
    return hashlib.sha256(data).hexdigest()


def load_catalog() -> dict[str, Any]:
    """Load catalog from bundled JSON file.

    Returns:
        Catalog dictionary.
    """
    catalog_file = _get_catalog_file_path()

    try:
        with catalog_file.open(encoding="utf-8") as f:
            data = json.load(f)
            entries = extract_catalog_entries(data)
            _LOGGER.debug("Loaded %d entries from local can_do_catalog.json", len(entries))
            return data
    except FileNotFoundError:
        _LOGGER.warning("can_do_catalog.json not found at %s", catalog_file)
        return {}
    except json.JSONDecodeError:
        _LOGGER.exception("Failed to parse local can_do_catalog.json")
        return {}


async def _async_get_current_catalog_hash() -> str | None:
    """Get hash of current catalog file."""
    catalog_file = _get_catalog_file_path()
    try:
        content = await asyncio.to_thread(catalog_file.read_bytes)
        return _compute_hash(content)
    except (FileNotFoundError, OSError):
        return None


async def async_fetch_catalog_from_github(
    session: ClientSession,
) -> tuple[dict[str, Any] | None, str | None]:
    """Fetch can_do_catalog.json from GitHub."""
    urls = [CATALOG_GITHUB_URL, CATALOG_GITHUB_URL_ALT]

    for url in urls:
        try:
            async with asyncio.timeout(GITHUB_FETCH_TIMEOUT):
                response = await session.get(url)
                if response.status != 200:
                    continue
                content = await response.read()
                content_hash = _compute_hash(content)
                data = json.loads(content.decode("utf-8"))
                return data, content_hash
        except Exception as err:
            _LOGGER.debug("Error fetching catalog from %s: %s", url, err)

    return None, None


async def async_update_catalog_from_github(session: ClientSession) -> dict[str, Any] | None:
    """Fetch can_do_catalog.json from GitHub and update local file if changed."""
    current_hash = await _async_get_current_catalog_hash()
    new_catalog, new_hash = await async_fetch_catalog_from_github(session)

    if new_catalog is None:
        _LOGGER.debug("Could not fetch catalog from GitHub, using current version")
        return get_catalog()

    if current_hash and current_hash == new_hash:
        _LOGGER.debug("Catalog is up to date (hash: %s...)", current_hash[:8])
        _CATALOG.clear()
        _CATALOG.update(new_catalog)
        return get_catalog()

    catalog_file = _get_catalog_file_path()
    try:
        def _write_catalog() -> None:
            catalog_file.parent.mkdir(parents=True, exist_ok=True)
            with catalog_file.open("w", encoding="utf-8") as f:
                json.dump(new_catalog, f, indent=2, ensure_ascii=False)

        await asyncio.to_thread(_write_catalog)
        _LOGGER.info("Updated can_do_catalog.json from GitHub (hash: %s...)", new_hash[:8] if new_hash else "unknown")

        _CATALOG.clear()
        _CATALOG.update(new_catalog)
    except OSError as err:
        _LOGGER.warning("Failed to write updated can_do_catalog.json: %s", err)

    return get_catalog()


def get_catalog() -> dict[str, Any]:
    """Get all loaded catalog data."""
    if not _CATALOG:
        _CATALOG.update(load_catalog())
    return _CATALOG.copy()


def get_catalog_entries() -> list[dict[str, Any]]:
    """Get extracted entry dicts from current catalog."""
    return extract_catalog_entries(get_catalog())


_CATALOG: dict[str, Any] = load_catalog()
