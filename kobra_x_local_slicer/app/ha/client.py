from __future__ import annotations

import os
from typing import Any

import aiohttp
import httpx
from pydantic import BaseModel, Field
from app.core.models import AceSlot, AceSnapshot


class HomeAssistantError(RuntimeError):
    pass


class HAStatus(BaseModel):
    online: bool | None = None
    available: bool | None = None
    busy: bool | None = None
    job_in_progress: bool | None = None
    state: str | None = None
    filename: str | None = None
    current_fault: bool | None = None
    error_states: dict[str, str] = Field(default_factory=dict)


# The maintained Anycubic Cloud & LAN integration publishes these translation keys.
# Entity-id suffixes are retained as a fallback for older integration releases.
ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "online": ("printer_online", "online"),
    "available": ("is_available", "available"),
    "busy": ("is_busy", "busy"),
    "job_in_progress": ("job_in_progress",),
    "state": ("current_status", "job_state", "state"),
    "filename": ("job_name", "filename", "current_filename"),
    "current_fault": ("job_failed", "current_fault", "fault", "printer_error"),
}
REQUIRED_ROLES = ("online", "available", "busy", "job_in_progress", "state", "filename")
ACE_ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "slot_1": ("ace_slot_1",), "slot_2": ("ace_slot_2",),
    "slot_3": ("ace_slot_3",), "slot_4": ("ace_slot_4",),
    "loaded_slot": ("ace_loaded_slot",),
}


def _entity_names(entity: dict[str, Any]) -> set[str]:
    values = [entity.get("translation_key"), entity.get("entity_id"), entity.get("original_name")]
    names: set[str] = set()
    for value in values:
        if isinstance(value, str) and value:
            names.add(value.lower())
    return names


def _find_entity(entities: list[dict[str, Any]], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        for entity in entities:
            entity_id = entity.get("entity_id")
            if not isinstance(entity_id, str):
                continue
            names = _entity_names(entity)
            if alias in names or any(name.endswith(f"_{alias}") for name in names):
                return entity_id
    return None


def suggest_entity_map(entities: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    suggested = {role: entity_id for role, aliases in ROLE_ALIASES.items() if (entity_id := _find_entity(entities, aliases))}
    errors = [
        entity["entity_id"]
        for entity in entities
        if isinstance(entity.get("entity_id"), str)
        and any(token in name for token in ("failed", "fault", "error") for name in _entity_names(entity))
    ]
    if errors:
        suggested["error_entities"] = errors
    return suggested, [role for role in REQUIRED_ROLES if role not in suggested]


def suggest_ace_entity_map(entities: list[dict[str, Any]]) -> dict[str, str]:
    return {role: entity_id for role, aliases in ACE_ROLE_ALIASES.items() if (entity_id := _find_entity(entities, aliases))}


def _is_ace_device(device: dict[str, Any], entities: list[dict[str, Any]]) -> bool:
    name = str(device.get("name_by_user") or device.get("name") or "").lower()
    return " ace" in name or "ace" == name or "slot_1" in suggest_ace_entity_map(entities)


class HomeAssistantClient:
    def __init__(self):
        self.token = os.getenv("SUPERVISOR_TOKEN", "")
        if not self.token:
            raise HomeAssistantError("SUPERVISOR_TOKEN unavailable")

    async def discover_anycubic_devices(self) -> list[dict[str, Any]]:
        """Read Home Assistant registries through Supervisor's authenticated WebSocket."""
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect("ws://supervisor/core/websocket", timeout=8) as ws:
                hello = await ws.receive_json()
                if hello.get("type") != "auth_required":
                    raise HomeAssistantError("unexpected Home Assistant WebSocket greeting")
                await ws.send_json({"type": "auth", "access_token": self.token})
                if (await ws.receive_json()).get("type") != "auth_ok":
                    raise HomeAssistantError("Supervisor token was not accepted")

                async def command(message_id: int, command_type: str):
                    await ws.send_json({"id": message_id, "type": command_type})
                    response = await ws.receive_json()
                    if not response.get("success"):
                        raise HomeAssistantError(f"Home Assistant {command_type} failed")
                    return response.get("result", [])

                devices = await command(1, "config/device_registry/list")
                entities = await command(2, "config/entity_registry/list")

        anycubic_devices = []
        rows_by_device: dict[str, list[dict[str, Any]]] = {}
        for device in devices:
            identifiers = device.get("identifiers", []) if isinstance(device, dict) else []
            if isinstance(device, dict) and any(item[0] == "anycubic_cloud" for item in identifiers if isinstance(item, (list, tuple)) and item):
                anycubic_devices.append(device)
                rows_by_device[device["id"]] = [entity for entity in entities if isinstance(entity, dict) and entity.get("device_id") == device["id"]]

        ace_devices = [device for device in anycubic_devices if _is_ace_device(device, rows_by_device[device["id"]])]
        candidates = []
        for device in anycubic_devices:
            rows = rows_by_device[device["id"]]
            if _is_ace_device(device, rows):
                continue
            suggested, unresolved = suggest_entity_map(rows)
            name = str(device.get("name_by_user") or device.get("name") or "")
            ace_device = next((child for child in ace_devices if child.get("via_device_id") == device["id"]), None)
            if ace_device is None:
                ace_device = next((child for child in ace_devices if str(child.get("name_by_user") or child.get("name") or "").lower().startswith(name.lower())), None)
            ace_rows = rows_by_device.get(ace_device["id"], []) if ace_device else []
            candidates.append({
                "device_id": device["id"],
                "name": name or device["id"],
                "entities": [{"entity_id": entity["entity_id"], "translation_key": entity.get("translation_key")} for entity in rows],
                "suggested_map": suggested,
                "unresolved_roles": unresolved,
                "ace_device_id": ace_device.get("id") if ace_device else None,
                "ace_suggested_map": suggest_ace_entity_map(ace_rows),
            })
        return candidates

    async def ace_snapshot(self, mapping: dict[str, str]) -> AceSnapshot:
        if not any(role.startswith("slot_") for role in mapping):
            raise HomeAssistantError("Home Assistant ACE entity mapping is not configured")
        headers = {"Authorization": f"Bearer {self.token}"}
        values: dict[str, str] = {}
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                for role, entity_id in mapping.items():
                    if not isinstance(entity_id, str):
                        continue
                    response = await client.get(f"http://supervisor/core/api/states/{entity_id}", headers=headers)
                    response.raise_for_status()
                    values[role] = str(response.json().get("state"))
        except httpx.HTTPError as exc:
            raise HomeAssistantError(str(exc)) from exc

        try:
            loaded_slot = int(values.get("loaded_slot", "-1"))
        except ValueError:
            loaded_slot = -1
        parsed: list[dict[str, Any]] = []
        normalized: list[AceSlot] = []
        for index in range(1, 5):
            material = values.get(f"slot_{index}")
            if material and material.lower() not in {"unknown", "unavailable", "none"}:
                material = material.upper()
            else:
                material = None
            item = {"slot": index, "material_type": material, "loaded": index == loaded_slot}
            parsed.append(item)
            normalized.append(AceSlot(human_slot=index, protocol_slot_index=index - 1, material_type=material, loaded=index == loaded_slot))
        return AceSnapshot(raw={"source": "home_assistant", "states": values}, parsed=parsed, normalized=normalized)

    async def cross_check(self, mapping: dict[str, Any]) -> HAStatus:
        headers = {"Authorization": f"Bearer {self.token}"}
        states: dict[str, str] = {}
        errors: dict[str, str] = {}
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                for role, entity_id in mapping.items():
                    entity_ids = entity_id if role == "error_entities" and isinstance(entity_id, list) else [entity_id]
                    for item in entity_ids:
                        if not isinstance(item, str):
                            continue
                        response = await client.get(f"http://supervisor/core/api/states/{item}", headers=headers)
                        response.raise_for_status()
                        value = str(response.json().get("state"))
                        if role == "error_entities":
                            errors[item] = value
                        else:
                            states[role] = value
        except httpx.HTTPError as exc:
            raise HomeAssistantError(str(exc)) from exc

        def boolean(value: str | None) -> bool | None:
            return None if value is None else value.lower() in {"on", "true", "available", "idle", "ready"}

        return HAStatus(
            online=boolean(states.get("online")),
            available=boolean(states.get("available")),
            busy=boolean(states.get("busy")) if "busy" in states else None,
            job_in_progress=boolean(states.get("job_in_progress")) if "job_in_progress" in states else None,
            state=states.get("state"),
            filename=states.get("filename"),
            current_fault=boolean(states.get("current_fault")) if "current_fault" in states else None,
            error_states=errors,
        )


def new_errors(current: dict[str, str], baseline: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in current.items() if baseline.get(key) != value}
