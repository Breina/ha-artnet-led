"""Repair flow for migrating ha_artnet_led → dmx configuration."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
import yaml
from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .migration import MigrationResult, device_fixture_signature, run_migration

_LOGGER = logging.getLogger(__name__)


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, Any] | None,
) -> RepairsFlow:
    """Create the fix flow for the ha_artnet_led_migration issue."""
    return MigrationRepairFlow()


class MigrationRepairFlow(RepairsFlow):
    """Multi-step repair flow: confirm → run migration → show result."""

    def __init__(self) -> None:
        super().__init__()
        self._result: MigrationResult | None = None
        self._written_files: list[str] = []

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        entries: list[dict[str, Any]] = self.hass.data.get(DOMAIN, {}).get("_old_entries", [])

        if not entries:
            return self.async_abort(reason="no_entries")

        if user_input is not None:
            self._result = await self.hass.async_add_executor_job(run_migration, entries)
            try:
                self._written_files = await self.hass.async_add_executor_job(self._write_outputs, self._result)
            except OSError as exc:
                _LOGGER.exception("Migration file write failed")
                return self.async_abort(
                    reason="write_failed",
                    description_placeholders={"error": str(exc)},
                )
            return await self.async_step_done()

        device_count = sum(len(u.get("devices", [])) for e in entries for u in e.get("universes", {}).values())
        universe_count = sum(len(e.get("universes", {})) for e in entries)
        fixture_count = len(
            {
                device_fixture_signature(d)
                for e in entries
                for u in e.get("universes", {}).values()
                for d in u.get("devices", [])
            }
        )

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "device_count": str(device_count),
                "universe_count": str(universe_count),
                "fixture_count": str(fixture_count),
            },
        )

    async def async_step_done(self, user_input: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data={})

        assert self._result is not None
        file_list = "\n".join(f"- `{f}`" for f in self._written_files)
        warnings_section = (
            "**Migration notes:**\n" + "\n".join(f"- {w}" for w in self._result.warnings)
            if self._result.warnings
            else ""
        )

        return self.async_show_form(
            step_id="done",
            data_schema=vol.Schema({}),
            description_placeholders={
                "file_list": file_list,
                "warnings_section": warnings_section,
            },
        )

    def _write_outputs(self, result: MigrationResult) -> list[str]:
        """Write fixture JSON files and YAML snippet. Called via async_add_executor_job."""
        config_dir = Path(self.hass.config.config_dir)
        fixtures_dir = config_dir / "fixtures"
        fixtures_dir.mkdir(parents=True, exist_ok=True)

        written: list[str] = []

        for sig, fixture in result.fixture_map.items():
            key = result.fixture_key_map[sig]
            fixture_path = fixtures_dir / f"{key}.json"
            fixture_path.write_text(
                json.dumps(fixture, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            written.append(str(fixture_path))

        yaml_path = config_dir / "dmx_migration.yaml"
        yaml_path.write_text(
            yaml.safe_dump(
                result.dmx_config,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        written.append(str(yaml_path))

        return written
