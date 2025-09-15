"""Fixture registry for centralized fixture management."""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from custom_components.dmx.fixture.fixture import Fixture
from custom_components.dmx.fixture.parser import parse_async

log = logging.getLogger(__name__)


@dataclass
class FixtureCacheEntry:
    """Cache entry for a fixture."""

    fixture: Fixture
    file_path: str
    file_hash: str
    last_modified: float
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0


class FixtureRegistry:
    """Centralized registry for fixture management with caching."""

    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self._fixtures: dict[str, FixtureCacheEntry] = {}
        self._cache_stats = {"hits": 0, "misses": 0, "evictions": 0}
        self._max_cache_size = 100  # Maximum number of cached fixtures

    async def load_fixtures_from_folder(self, fixture_folder: str) -> dict[str, Fixture]:
        """Load all fixtures from a folder with caching."""
        fixture_map: dict[str, Fixture] = {}

        if not os.path.isdir(fixture_folder):
            log.warning(f"Fixture folder does not exist: {fixture_folder}")
            return fixture_map

        log.debug(f"Loading fixtures from folder: {fixture_folder}")

        # Get all JSON files in the folder
        try:
            file_list = await self.hass.async_add_executor_job(os.listdir, fixture_folder)
            json_files = [f for f in file_list if f.endswith(".json")]

            log.info(f"Found {len(json_files)} fixture files in {fixture_folder}")

            for filename in json_files:
                file_path = os.path.join(fixture_folder, filename)
                try:
                    fixture = await self.get_fixture(file_path)
                    if fixture:
                        fixture_map[fixture.short_name] = fixture
                        # Also map by fixture key and name for better lookup
                        if hasattr(fixture, "fixture_key") and fixture.fixture_key:
                            fixture_map[fixture.fixture_key] = fixture
                        if fixture.name != fixture.short_name:
                            fixture_map[fixture.name] = fixture

                except Exception as e:
                    log.warning(f"Error loading fixture from {filename}: {e}")

        except Exception as e:
            log.error(f"Error reading fixture folder {fixture_folder}: {e}")

        log.info(f"Successfully loaded {len(fixture_map)} fixtures")
        return fixture_map

    async def get_fixture(self, file_path: str) -> Fixture | None:
        """Get a fixture from cache or load it from file."""
        try:
            # Calculate file hash for cache validation
            file_hash = await self._get_file_hash(file_path)
            file_stat = await self.hass.async_add_executor_job(os.stat, file_path)

            # Check if fixture is cached and valid
            cache_key = self._get_cache_key(file_path)
            if cache_entry := self._fixtures.get(cache_key):
                if cache_entry.file_hash == file_hash and cache_entry.last_modified == file_stat.st_mtime:
                    # Cache hit - update access stats
                    cache_entry.last_accessed = time.time()
                    cache_entry.access_count += 1
                    self._cache_stats["hits"] += 1
                    log.debug(f"Cache hit for fixture: {file_path}")
                    return cache_entry.fixture
                else:
                    # Cache invalid - remove old entry
                    log.debug(f"Cache invalidated for fixture: {file_path}")
                    del self._fixtures[cache_key]

            # Cache miss - load fixture from file
            self._cache_stats["misses"] += 1
            log.debug(f"Cache miss for fixture: {file_path}")

            fixture = await parse_async(file_path, self.hass)

            # Add to cache
            cache_entry = FixtureCacheEntry(
                fixture=fixture, file_path=file_path, file_hash=file_hash, last_modified=file_stat.st_mtime
            )

            self._fixtures[cache_key] = cache_entry

            # Evict old entries if cache is full
            await self._evict_if_needed()

            return fixture

        except json.JSONDecodeError as e:
            log.warning(f"Invalid JSON in file {file_path}: {e}")
        except FileNotFoundError:
            log.warning(f"Fixture file not found: {file_path}")
        except Exception as e:
            log.error(f"Error loading fixture from {file_path}: {e}")

        return None

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache performance statistics."""
        total_requests = self._cache_stats["hits"] + self._cache_stats["misses"]
        hit_rate = (self._cache_stats["hits"] / total_requests * 100) if total_requests > 0 else 0

        return {
            "cached_fixtures": len(self._fixtures),
            "total_requests": total_requests,
            "cache_hits": self._cache_stats["hits"],
            "cache_misses": self._cache_stats["misses"],
            "cache_evictions": self._cache_stats["evictions"],
            "hit_rate_percent": round(hit_rate, 2),
        }

    async def _get_file_hash(self, file_path: str) -> str:
        """Get MD5 hash of a file."""

        def _hash_file() -> str:
            hash_md5 = hashlib.md5()  # noqa: S324
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()

        return await self.hass.async_add_executor_job(_hash_file)

    def _get_cache_key(self, file_path: str) -> str:
        """Generate a cache key from file path."""
        return f"fixture_{Path(file_path).stem}"

    async def _evict_if_needed(self) -> None:
        """Evict least recently used fixtures if cache is too large."""
        if len(self._fixtures) <= self._max_cache_size:
            return

        # Sort by last accessed time and remove oldest
        sorted_fixtures = sorted(self._fixtures.items(), key=lambda x: x[1].last_accessed)

        # Remove oldest 20% of fixtures
        evict_count = len(self._fixtures) - self._max_cache_size + int(self._max_cache_size * 0.2)

        for cache_key, _ in sorted_fixtures[:evict_count]:
            self._fixtures.pop(cache_key)
            self._cache_stats["evictions"] += 1

        log.debug(f"Evicted {evict_count} fixtures from cache")


# Global registry instance
_fixture_registry: FixtureRegistry | None = None


def get_fixture_registry(hass: HomeAssistant) -> FixtureRegistry:
    """Get the global fixture registry instance."""
    global _fixture_registry
    if _fixture_registry is None:
        _fixture_registry = FixtureRegistry(hass)
    return _fixture_registry
