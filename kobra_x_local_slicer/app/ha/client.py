"""Public Home Assistant adapter for Anycubic Cloud & LAN.

This is intentionally the only module that knows Home Assistant entity ids. It
uses public registry/state/service APIs and never reads anycubic_cloud internals
or parses the printer MQTT payload.
"""
from __future__ import annotations

import os
import asyncio
from datetime import UTC, datetime
from typing import Any

import aiohttp
import httpx

from app.core.models import AceSlot, AceSnapshot, PrinterFaultSnapshot, PrinterJobSnapshot, PrinterSnapshot, PrinterThermalSnapshot


class HomeAssistantError(RuntimeError):
    pass


DOMAIN = "anycubic_cloud"
ESSENTIAL_KEYS = ("printer_online", "is_available", "is_busy", "job_in_progress", "current_status", "job_name")
PRINTER_KEYS = (
    "printer_online", "is_busy", "is_available", "current_status", "job_name", "job_state", "job_progress",
    "job_in_progress", "job_complete", "job_failed", "job_is_paused", "job_current_layer", "job_total_layers",
    "job_time_elapsed", "job_time_remaining", "job_eta", "curr_nozzle_temp", "curr_hotbed_temp",
    "target_nozzle_temp", "target_hotbed_temp", "print_speed_pct", "fan_speed_pct", "aux_fan_speed_pct",
    "box_fan_level", "last_error_code", "last_error", "file_list_local", "job_image_url", "pause_print",
    "resume_print", "cancel_print",
)
ACE_KEYS = ("ace_loaded_slot", "ace_spools", "ace_slot_1", "ace_slot_2", "ace_slot_3", "ace_slot_4", "ace_current_temperature", "dry_status_is_drying")
CAPABILITY_DEFAULTS = {
    "telemetry_from_ha": False, "ace_from_ha": False, "pause_via_ha": False, "resume_via_ha": False,
    "cancel_via_ha": False, "local_file_list_via_ha": False, "local_upload_via_ha": False,
    "local_start_via_ha": False, "local_start_with_ace_via_ha": False, "cloud_upload_via_ha": False,
    "camera_via_ha": False,
}


def _translation_key(entity: dict[str, Any]) -> str | None:
    key = entity.get("translation_key")
    return key if isinstance(key, str) and key else None


def _find_entity(entities: list[dict[str, Any]], keys: tuple[str, ...]) -> str | None:
    """Find only by exact translation_key, never by entity id/name text."""
    for key in keys:
        for entity in entities:
            if _translation_key(entity) == key and isinstance(entity.get("entity_id"), str):
                return entity["entity_id"]
    return None


def suggest_entity_map(entities: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    roles = {
        "online": ("printer_online",), "available": ("is_available",), "busy": ("is_busy",),
        "job_in_progress": ("job_in_progress",), "state": ("current_status", "job_state"),
        "filename": ("job_name",), "current_fault": ("job_failed",),
    }
    found = {role: entity_id for role, keys in roles.items() if (entity_id := _find_entity(entities, keys))}
    errors = [row["entity_id"] for row in entities if _translation_key(row) in {"job_failed", "last_error", "last_error_code"} and isinstance(row.get("entity_id"), str)]
    if errors:
        found["error_entities"] = errors
    required = ("online", "available", "busy", "job_in_progress", "state", "filename")
    return found, [role for role in required if role not in found]


def suggest_ace_entity_map(entities: list[dict[str, Any]]) -> dict[str, str]:
    keys = {"slot_1": "ace_slot_1", "slot_2": "ace_slot_2", "slot_3": "ace_slot_3", "slot_4": "ace_slot_4", "loaded_slot": "ace_loaded_slot"}
    return {role: entity_id for role, key in keys.items() if (entity_id := _find_entity(entities, (key,)))}


def _unknown(value: Any) -> bool:
    return value is None or str(value).strip().lower() in {"", "unknown", "unavailable", "none", "null"}


def _bool(value: Any) -> bool | None:
    if _unknown(value):
        return None
    value = str(value).strip().lower()
    return True if value in {"on", "true", "1"} else False if value in {"off", "false", "0"} else None


def _number(value: Any) -> float | None:
    if _unknown(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    value = _number(value)
    return int(value) if value is not None else None


def _availability(row: dict[str, Any] | None) -> str:
    if row is None:
        return "missing"
    value = _state(row)
    if value is None:
        return "missing"
    normalized = str(value).strip().lower()
    if normalized == "unavailable":
        return "unavailable"
    if normalized == "unknown":
        return "unknown"
    return "available"


def _list(value: Any) -> list[Any] | None:
    return value if isinstance(value, list) else None


def _state(row: dict[str, Any] | None) -> Any:
    return row.get("state") if isinstance(row, dict) else None


def _attrs(row: dict[str, Any] | None) -> dict[str, Any]:
    attrs = row.get("attributes") if isinstance(row, dict) else None
    return attrs if isinstance(attrs, dict) else {}


def _rgb(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    value = value.removeprefix("#")
    if len(value) != 6:
        return None
    try:
        return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return None


class AnycubicHomeAssistantAdapter:
    """Server-side state/control provider backed by ``anycubic_cloud``."""

    def __init__(self, printer_device_id: str = "", *, stale_after_seconds: int = 45):
        self.token = os.getenv("SUPERVISOR_TOKEN", "")
        if not self.token:
            raise HomeAssistantError("SUPERVISOR_TOKEN unavailable")
        self.printer_device_id = printer_device_id
        self.stale_after_seconds = stale_after_seconds
        self.entities: dict[str, str] = {}
        self.ace_device_ids: list[str] = []
        # The public registries have no reliable custom-component version field.
        self.integration_version: str | None = None
        self.version_detection = "unsupported"
        self._state_cache: dict[str, dict[str, Any]] | None = None
        self._watch_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self.ws_connected = False
        self.last_health_check_at: datetime | None = None

    async def start(self) -> None:
        """Resolve once, hydrate a state cache, then keep it live via HA events."""
        if self._watch_task and not self._watch_task.done():
            return
        self._stop_event.clear()
        await self.resolve()
        await self._refresh_states()
        self._watch_task = asyncio.create_task(self._watch_state_changes())

    async def close(self) -> None:
        self._stop_event.set()
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
        self._watch_task = None
        self.ws_connected = False

    async def _ws(self, commands: list[tuple[str, dict[str, Any]]]) -> list[Any]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect("ws://supervisor/core/websocket", timeout=8) as ws:
                    if (await ws.receive_json()).get("type") != "auth_required":
                        raise HomeAssistantError("unexpected Home Assistant WebSocket greeting")
                    await ws.send_json({"type": "auth", "access_token": self.token})
                    if (await ws.receive_json()).get("type") != "auth_ok":
                        raise HomeAssistantError("Supervisor token was not accepted")
                    results: list[Any] = []
                    for ident, (command, payload) in enumerate(commands, 1):
                        await ws.send_json({"id": ident, "type": command, **payload})
                        response = await ws.receive_json()
                        if not response.get("success"):
                            raise HomeAssistantError(f"Home Assistant {command} failed: {response.get('error', {})}")
                        results.append(response.get("result"))
                    return results
        except aiohttp.ClientError as exc:
            raise HomeAssistantError(f"Home Assistant WebSocket unavailable: {exc}") from exc

    async def _registries(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        devices, entities = await self._ws([("config/device_registry/list", {}), ("config/entity_registry/list", {})])
        return [x for x in devices if isinstance(x, dict)], [x for x in entities if isinstance(x, dict)]

    async def discover(self) -> list[dict[str, Any]]:
        devices, entities = await self._registries()
        device_map = {d["id"]: d for d in devices if isinstance(d.get("id"), str)}
        by_device: dict[str, list[dict[str, Any]]] = {}
        for row in entities:
            if row.get("platform") == DOMAIN and isinstance(row.get("device_id"), str):
                by_device.setdefault(row["device_id"], []).append(row)
        candidates = []
        for device_id, rows in by_device.items():
            if not {_translation_key(row) for row in rows}.intersection({"printer_online", "current_status", "is_available"}):
                continue
            child_ids = [ident for ident, device in device_map.items() if device.get("via_device_id") == device_id and ident in by_device]
            ace_ids = [ident for ident in child_ids if {_translation_key(row) for row in by_device[ident]}.intersection(ACE_KEYS)]
            mapping, unresolved = suggest_entity_map(rows)
            ace_rows = [row for ident in ace_ids for row in by_device[ident]]
            device = device_map.get(device_id, {})
            candidates.append({
                "device_id": device_id, "name": str(device.get("name_by_user") or device.get("name") or device_id),
                "entities": [{"entity_id": row["entity_id"], "translation_key": _translation_key(row)} for row in rows],
                "suggested_map": mapping, "unresolved_roles": unresolved,
                "ace_device_id": ace_ids[0] if ace_ids else None, "ace_device_ids": ace_ids,
                "ace_suggested_map": suggest_ace_entity_map(ace_rows),
            })
        return candidates

    async def resolve(self) -> None:
        if not self.printer_device_id:
            raise HomeAssistantError("Anycubic printer device is not selected")
        devices, entities = await self._registries()
        device_ids = {d.get("id") for d in devices}
        if self.printer_device_id not in device_ids:
            raise HomeAssistantError("selected Anycubic printer device is no longer in the registry")
        children = {d["id"] for d in devices if isinstance(d.get("id"), str) and d.get("via_device_id") == self.printer_device_id}
        rows = [row for row in entities if row.get("platform") == DOMAIN and row.get("device_id") in children | {self.printer_device_id}]
        if not any(row.get("device_id") == self.printer_device_id for row in rows):
            raise HomeAssistantError("selected device has no anycubic_cloud entities")
        self.entities = {}
        self._state_cache = None
        valid_keys = set(PRINTER_KEYS + ACE_KEYS)
        for row in rows:
            key, entity_id = _translation_key(row), row.get("entity_id")
            if key in valid_keys and isinstance(entity_id, str) and key not in self.entities:
                self.entities[key] = entity_id
        self.ace_device_ids = [ident for ident in children if any(row.get("device_id") == ident and _translation_key(row) in ACE_KEYS for row in rows)]

    async def _states(self) -> dict[str, dict[str, Any]]:
        if self._state_cache is not None and self.ws_connected:
            return dict(self._state_cache)
        return await self._refresh_states()

    async def _refresh_states(self) -> dict[str, dict[str, Any]]:
        if not self.entities:
            await self.resolve()
        # Home Assistant's websocket state stream is the normal path.  A single
        # `get_states` snapshot also avoids the old per-entity REST polling loop.
        try:
            all_states, = await self._ws([("get_states", {})])
            by_entity = {row.get("entity_id"): row for row in all_states if isinstance(row, dict)}
            states = {key: by_entity[entity_id] for key, entity_id in self.entities.items() if isinstance(by_entity.get(entity_id), dict)}
            self._state_cache = states
            self.last_health_check_at = datetime.now(UTC)
            return dict(states)
        except HomeAssistantError:
            # REST is a health/recovery fallback only; it never contacts Kobra X.
            pass
        headers = {"Authorization": f"Bearer {self.token}"}
        states: dict[str, dict[str, Any]] = {}
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                for key, entity_id in self.entities.items():
                    response = await client.get(f"http://supervisor/core/api/states/{entity_id}", headers=headers)
                    if response.status_code == 404:
                        continue
                    response.raise_for_status()
                    payload = response.json()
                    if isinstance(payload, dict):
                        states[key] = payload
        except httpx.HTTPError as exc:
            raise HomeAssistantError(f"Home Assistant state read failed: {exc}") from exc
        self._state_cache = states
        self.last_health_check_at = datetime.now(UTC)
        return dict(states)

    async def _watch_state_changes(self) -> None:
        """Persistent HA subscription with bounded reconnect backoff and resubscribe."""
        backoff = 1.0
        while not self._stop_event.is_set():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect("ws://supervisor/core/websocket", timeout=8) as ws:
                        if (await ws.receive_json()).get("type") != "auth_required":
                            raise HomeAssistantError("unexpected Home Assistant WebSocket greeting")
                        await ws.send_json({"type": "auth", "access_token": self.token})
                        if (await ws.receive_json()).get("type") != "auth_ok":
                            raise HomeAssistantError("Supervisor token was not accepted")
                        for ident, event_type in enumerate(("state_changed", "entity_registry_updated", "device_registry_updated"), 1):
                            await ws.send_json({"id": ident, "type": "subscribe_events", "event_type": event_type})
                            response = await ws.receive_json()
                            if not response.get("success"):
                                raise HomeAssistantError(f"cannot subscribe to {event_type}")
                        self.ws_connected = True
                        self.last_health_check_at = datetime.now(UTC)
                        backoff = 1.0
                        while not self._stop_event.is_set():
                            try:
                                message = await ws.receive_json(timeout=15)
                            except asyncio.TimeoutError:
                                await ws.ping()
                                self.last_health_check_at = datetime.now(UTC)
                                continue
                            if message.get("type") != "event":
                                continue
                            event = message.get("event", {})
                            event_type = event.get("event_type")
                            if event_type in {"entity_registry_updated", "device_registry_updated"}:
                                self.entities = {}
                                self._state_cache = None
                                continue
                            data = event.get("data", {})
                            entity_id = data.get("entity_id")
                            if not isinstance(entity_id, str):
                                continue
                            key = next((name for name, value in self.entities.items() if value == entity_id), None)
                            if key is not None:
                                new_state = data.get("new_state")
                                if isinstance(new_state, dict):
                                    if self._state_cache is None:
                                        self._state_cache = {}
                                    self._state_cache[key] = new_state
                                elif self._state_cache:
                                    self._state_cache.pop(key, None)
                            self.last_health_check_at = datetime.now(UTC)
            except (aiohttp.ClientError, HomeAssistantError, asyncio.TimeoutError):
                self.ws_connected = False
                if not self._stop_event.is_set():
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30)
            finally:
                self.ws_connected = False

    def capabilities(self, states: dict[str, dict[str, Any]] | None = None) -> dict[str, bool]:
        keys = set(states or self.entities)
        result = dict(CAPABILITY_DEFAULTS)
        result.update({
            "telemetry_from_ha": set(ESSENTIAL_KEYS).issubset(keys),
            "ace_from_ha": bool(keys.intersection({"ace_spools", "ace_slot_1", "ace_loaded_slot"})),
            "pause_via_ha": "pause_print" in keys, "resume_via_ha": "resume_print" in keys,
            "cancel_via_ha": "cancel_print" in keys, "local_file_list_via_ha": "file_list_local" in keys,
            "camera_via_ha": "job_image_url" in keys,
        })
        return result

    def _ace(self, states: dict[str, dict[str, Any]]) -> AceSnapshot | None:
        if not any(key in states for key in ("ace_loaded_slot", "ace_spools", "ace_slot_1")):
            return None
        loaded_slot = _integer(_state(states.get("ace_loaded_slot")))
        parsed: list[dict[str, Any]] = []
        slots: list[AceSlot] = []
        for number in range(1, 5):
            row = states.get(f"ace_slot_{number}")
            if row is None:
                continue
            value, attrs = _state(row), _attrs(row)
            color_hex = attrs.get("color_hex") or attrs.get("color")
            colors = attrs.get("colors_hex") if isinstance(attrs.get("colors_hex"), list) else []
            slots.append(AceSlot(
                human_slot=_integer(attrs.get("slot")) or number, protocol_slot_index=number - 1,
                material_type=None if _unknown(value) else str(value).upper(), rgb=_rgb(color_hex),
                loaded=(number == loaded_slot) if loaded_slot is not None else None,
                color_hex=color_hex if isinstance(color_hex, str) else None, colors_hex=[str(x) for x in colors if isinstance(x, str)],
                is_multi_color=attrs.get("is_multi_color") if isinstance(attrs.get("is_multi_color"), bool) else None,
                sku=attrs.get("sku") if isinstance(attrs.get("sku"), str) else None,
                spool_loaded=attrs.get("spool_loaded") if isinstance(attrs.get("spool_loaded"), bool) else None,
                status=attrs.get("status") if isinstance(attrs.get("status"), str) else None,
                edit_status=attrs.get("edit_status") if isinstance(attrs.get("edit_status"), str) else None,
                consumables_percent=_number(attrs.get("consumables_percent")), raw_state=None if value is None else str(value),
            ))
            parsed.append({"state": value, "attributes": attrs})
        return AceSnapshot(
            raw={key: row for key, row in states.items() if key.startswith("ace_")},
            parsed=parsed,
            normalized=slots,
            loaded_slot=loaded_slot,
            current_temperature=_number(_state(states.get("ace_current_temperature"))),
            dry_status_is_drying=_bool(_state(states.get("dry_status_is_drying"))),
        )

    async def snapshot(self) -> PrinterSnapshot:
        states = await self._states()
        now = datetime.now(UTC)
        dates = []
        for row in states.values():
            stamp = row.get("last_updated") or row.get("last_changed")
            if isinstance(stamp, str):
                try:
                    dates.append(datetime.fromisoformat(stamp.replace("Z", "+00:00")))
                except ValueError:
                    pass
        observed_at = max(dates) if dates else now
        received_at = self.last_health_check_at or now
        availability = {key: _availability(states.get(key)) for key in set(self.entities) | set(ESSENTIAL_KEYS)}
        essential = all(availability.get(key) == "available" for key in ESSENTIAL_KEYS)
        status = _state(states.get("current_status")) or _state(states.get("job_state"))
        return PrinterSnapshot(
            integration_version=self.integration_version, printer_device_id=self.printer_device_id, observed_at=observed_at,
            snapshot_received_at=received_at, last_health_check_at=self.last_health_check_at,
            # A successful HA snapshot is fresh even if the printer has been idle
            # and none of its entity values changed recently.
            stale=(now - received_at).total_seconds() > self.stale_after_seconds,
            ha_connected=self.ws_connected or self.last_health_check_at is not None, essential_entities_available=essential,
            entity_availability=availability,
            online=_bool(_state(states.get("printer_online"))), available=_bool(_state(states.get("is_available"))),
            busy=_bool(_state(states.get("is_busy"))), status=None if _unknown(status) else str(status),
            job=PrinterJobSnapshot(
                name=None if _unknown(_state(states.get("job_name"))) else str(_state(states.get("job_name"))),
                state=None if _unknown(_state(states.get("job_state"))) else str(_state(states.get("job_state"))),
                progress=_number(_state(states.get("job_progress"))), current_layer=_integer(_state(states.get("job_current_layer"))),
                total_layers=_integer(_state(states.get("job_total_layers"))), elapsed_minutes=_number(_state(states.get("job_time_elapsed"))),
                remaining_minutes=_number(_state(states.get("job_time_remaining"))), eta=None if _unknown(_state(states.get("job_eta"))) else str(_state(states.get("job_eta"))),
                paused=_bool(_state(states.get("job_is_paused"))),
                in_progress=_bool(_state(states.get("job_in_progress"))),
                complete=_bool(_state(states.get("job_complete"))),
                failed=_bool(_state(states.get("job_failed"))),
            ),
            thermal=PrinterThermalSnapshot(nozzle_current=_number(_state(states.get("curr_nozzle_temp"))), nozzle_target=_number(_state(states.get("target_nozzle_temp"))), bed_current=_number(_state(states.get("curr_hotbed_temp"))), bed_target=_number(_state(states.get("target_hotbed_temp")))),
            print_speed_pct=_number(_state(states.get("print_speed_pct"))), fan_speed_pct=_number(_state(states.get("fan_speed_pct"))),
            aux_fan_speed_pct=_number(_state(states.get("aux_fan_speed_pct"))), box_fan_level=_number(_state(states.get("box_fan_level"))),
            local_files=_list(_state(states.get("file_list_local"))), job_image_url=None if _unknown(_state(states.get("job_image_url"))) else str(_state(states.get("job_image_url"))),
            ace=self._ace(states),
            fault=PrinterFaultSnapshot(
                active=_bool(_state(states.get("job_failed"))),
                job_failed=_bool(_state(states.get("job_failed"))),
                last_error_code=None if _unknown(_state(states.get("last_error_code"))) else str(_state(states.get("last_error_code"))),
                last_error_message=None if _unknown(_state(states.get("last_error"))) else str(_state(states.get("last_error"))),
                historical=bool(_state(states.get("last_error_code")) or _state(states.get("last_error"))),
            ),
            capabilities=self.capabilities(states),
        )

    async def press(self, action: str) -> dict[str, Any]:
        key = {"pause": "pause_print", "resume": "resume_print", "cancel": "cancel_print"}.get(action)
        if key is None:
            raise HomeAssistantError(f"unsupported printer action: {action}")
        if key not in self.entities:
            await self.resolve()
        if key not in self.entities:
            raise HomeAssistantError(f"{action} is unsupported by the selected Anycubic integration")
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.post("http://supervisor/core/api/services/button/press", headers=headers, json={"entity_id": self.entities[key]})
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HomeAssistantError(f"Home Assistant {action} command failed: {exc}") from exc
        return {"action": action, "entity_id": self.entities[key], "accepted_by_home_assistant": True}

    async def diagnostics(self) -> dict[str, Any]:
        await self.resolve()
        snapshot = await self.snapshot()
        return {
            "domain": DOMAIN, "version": self.integration_version, "version_detection": self.version_detection, "printer_device_id": self.printer_device_id,
            "ace_device_ids": self.ace_device_ids, "entities_resolved": self.entities,
            "entities_missing": [key for key in ESSENTIAL_KEYS if key not in self.entities],
            "freshness": {"observed_at": snapshot.observed_at, "stale": snapshot.stale}, "capabilities": snapshot.capabilities,
            "upload_transport": "DirectLanFileTransfer", "start_transport": "ValidatedLegacyLanStart",
            "local_start_via_anycubic_cloud": False,
        }


HomeAssistantClient = AnycubicHomeAssistantAdapter


def new_errors(current: dict[str, str], baseline: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in current.items() if baseline.get(key) != value}
