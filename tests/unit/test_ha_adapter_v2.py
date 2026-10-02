import asyncio
from datetime import UTC, datetime, timedelta

import pytest
import aiohttp

from app.ha.client import (
    AnycubicHomeAssistantAdapter, ESSENTIAL_KEYS, READINESS_KEYS,
    HomeAssistantError, _receive_ws_json, suggest_entity_map,
)


def _row(state, **attributes):
    return {
        "state": state,
        "attributes": attributes,
        "last_updated": datetime.now(UTC).isoformat(),
    }


def _old_row(state, **attributes):
    return {
        "state": state,
        "attributes": attributes,
        "last_updated": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
    }


def _idle_states():
    return {
        "printer_online": _row("on"), "is_available": _row("on"),
        "is_busy": _row("off"), "job_in_progress": _row("off"),
        "current_status": _row("available"), "job_name": _row("unavailable"),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("job_name", ["unavailable", "unknown", None])
async def test_idle_job_name_does_not_block_readiness(monkeypatch, job_name):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test")
    adapter = AnycubicHomeAssistantAdapter("printer")
    states = _idle_states()
    states["job_name"] = _row(job_name)
    async def fake_states():
        return states
    monkeypatch.setattr(adapter, "_states", fake_states)
    snapshot = await adapter.snapshot()
    assert "job_name" in ESSENTIAL_KEYS
    assert snapshot.essential_entities_available is True
    assert snapshot.capabilities["telemetry_from_ha"] is True
    assert snapshot.job.name is None


@pytest.mark.asyncio
@pytest.mark.parametrize("key", READINESS_KEYS)
async def test_required_telemetry_still_blocks_readiness(monkeypatch, key):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test")
    adapter = AnycubicHomeAssistantAdapter("printer")
    states = _idle_states()
    states[key] = _row("unavailable")
    async def fake_states():
        return states
    monkeypatch.setattr(adapter, "_states", fake_states)
    snapshot = await adapter.snapshot()
    assert snapshot.essential_entities_available is False
    assert snapshot.capabilities["telemetry_from_ha"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("frame", [aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR])
async def test_websocket_close_frames_are_recoverable(frame):
    class Socket:
        async def receive(self, *, timeout):
            return aiohttp.WSMessage(frame, None, None)
    with pytest.raises(HomeAssistantError, match="non-text frame"):
        await _receive_ws_json(Socket(), timeout=15)


@pytest.mark.asyncio
async def test_websocket_reconnect_refreshes_missed_state(monkeypatch):
    import json
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test")
    adapter = AnycubicHomeAssistantAdapter("printer")
    connections = refreshes = 0
    class Socket:
        def __init__(self, number):
            self.number = number
            self.messages = iter([
                {"type": "auth_required"}, {"type": "auth_ok"},
                *[{"success": True} for _ in range(3)],
            ])
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            pass
        async def send_json(self, payload):
            pass
        async def receive(self, *, timeout):
            payload = next(self.messages, None)
            if payload is not None:
                return aiohttp.WSMessage(aiohttp.WSMsgType.TEXT, json.dumps(payload), None)
            assert adapter.ws_connected
            assert adapter._state_cache["is_busy"]["state"] == ("off" if self.number == 1 else "on")
            if self.number == 2:
                adapter._stop_event.set()
            return aiohttp.WSMessage(aiohttp.WSMsgType.CLOSE, 1000, None)
    class Session:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            pass
        def ws_connect(self, *_args, **_kwargs):
            nonlocal connections
            connections += 1
            assert not adapter.ws_connected
            return Socket(connections)
    async def refresh():
        nonlocal refreshes
        refreshes += 1
        adapter._state_cache = {"is_busy": _row("off" if refreshes == 1 else "on")}
        return adapter._state_cache
    async def backoff(seconds):
        assert seconds == 1.0
        assert adapter.ws_connected is False
        assert adapter._state_cache is None
    monkeypatch.setattr("app.ha.client.aiohttp.ClientSession", Session)
    monkeypatch.setattr("app.ha.client.asyncio.sleep", backoff)
    monkeypatch.setattr(adapter, "_refresh_states", refresh)
    await asyncio.wait_for(adapter._watch_state_changes(), 2)
    assert connections == refreshes == 2
    assert adapter.ws_connected is False
    assert adapter._state_cache is None


def test_entity_id_text_is_never_used_as_a_fallback():
    mapping, unresolved = suggest_entity_map(
        [
            {
                "entity_id": "binary_sensor.renamed_printer_online",
                "translation_key": None,
            },
        ]
    )
    assert mapping == {}
    assert "online" in unresolved


def test_ace_snapshot_preserves_attributes_and_unknowns(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test")
    adapter = AnycubicHomeAssistantAdapter("printer")
    ace = adapter._ace(
        {
            "ace_loaded_slot": _row("2"),
            "ace_slot_1": _row(
                "unknown", slot=1, color_hex="#010203", spool_loaded=False
            ),
            "ace_slot_2": _row(
                "PLA",
                slot=2,
                color_hex="#aabbcc",
                sku="sku",
                spool_loaded=True,
                consumables_percent="37",
            ),
        }
    )
    assert ace is not None
    assert ace.loaded_slot == 2
    assert ace.normalized[0].material_type is None
    assert ace.normalized[0].spool_loaded is False
    assert ace.normalized[1].loaded is True
    assert ace.normalized[1].rgb == (170, 187, 204)
    assert ace.normalized[1].consumables_percent == 37.0


@pytest.mark.asyncio
async def test_snapshot_keeps_unknown_false_and_zero_distinct(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test")
    adapter = AnycubicHomeAssistantAdapter("printer")
    adapter.entities = {"printer_online": "a"}
    states = {
        "printer_online": _row("unknown"),
        "is_available": _row("off"),
        "is_busy": _row("0"),
        "job_in_progress": _row("false"),
        "current_status": _row("idle"),
        "job_name": _row("none"),
        "job_progress": _row("0"),
        "job_is_paused": _row("unavailable"),
    }

    async def fake_states():
        return states

    monkeypatch.setattr(adapter, "_states", fake_states)
    snapshot = await adapter.snapshot()
    assert snapshot.online is None
    assert snapshot.available is False
    assert snapshot.busy is False
    assert snapshot.job.progress == 0.0
    assert snapshot.job.paused is None
    assert snapshot.capabilities["local_start_via_ha"] is False


@pytest.mark.asyncio
async def test_snapshot_refresh_bypasses_the_event_cache(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test")
    adapter = AnycubicHomeAssistantAdapter("printer")
    states = {"printer_online": _row("on")}
    refreshes = 0

    async def cached_states():
        raise AssertionError("the cached snapshot must not be used")

    async def refreshed_states():
        nonlocal refreshes
        refreshes += 1
        return states

    monkeypatch.setattr(adapter, "_states", cached_states)
    monkeypatch.setattr(adapter, "_refresh_states", refreshed_states)
    snapshot = await adapter.snapshot(refresh=True)

    assert refreshes == 1
    assert snapshot.online is True


@pytest.mark.asyncio
async def test_successful_idle_snapshot_is_fresh_despite_old_entity_timestamps(
    monkeypatch,
):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test")
    adapter = AnycubicHomeAssistantAdapter("printer")
    states = {
        "printer_online": _old_row("on"),
        "is_available": _old_row("on"),
        "is_busy": _old_row("off"),
        "job_in_progress": _old_row("off"),
        "current_status": _old_row("idle"),
        "job_name": _old_row("none"),
        "last_error_code": _old_row("10107"),
        "last_error": _old_row("historical"),
        "job_failed": _old_row("off"),
    }

    async def fake_states():
        return states

    monkeypatch.setattr(adapter, "_states", fake_states)
    snapshot = await adapter.snapshot()
    assert snapshot.stale is False
    assert snapshot.snapshot_received_at > snapshot.observed_at
    assert snapshot.essential_entities_available is True
    assert snapshot.fault.active is False
    assert snapshot.fault.historical is True


@pytest.mark.asyncio
async def test_essential_unavailable_is_not_usable(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test")
    adapter = AnycubicHomeAssistantAdapter("printer")
    states = {
        "printer_online": _row("on"),
        "is_available": _row("unavailable"),
        "is_busy": _row("off"),
        "job_in_progress": _row("off"),
        "current_status": _row("idle"),
        "job_name": _row("none"),
    }

    async def fake_states():
        return states

    monkeypatch.setattr(adapter, "_states", fake_states)
    snapshot = await adapter.snapshot()
    assert snapshot.essential_entities_available is False
    assert snapshot.entity_availability["is_available"] == "unavailable"


@pytest.mark.asyncio
async def test_discovery_links_ace_only_through_via_device_id(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test")
    adapter = AnycubicHomeAssistantAdapter()
    devices = [
        {"id": "printer", "name": "Renamed"},
        {"id": "ace", "via_device_id": "printer"},
    ]
    entities = [
        {
            "entity_id": "binary_sensor.whatever",
            "platform": "anycubic_cloud",
            "device_id": "printer",
            "translation_key": "printer_online",
        },
        {
            "entity_id": "sensor.status",
            "platform": "anycubic_cloud",
            "device_id": "printer",
            "translation_key": "current_status",
        },
        {
            "entity_id": "sensor.ace_any_name",
            "platform": "anycubic_cloud",
            "device_id": "ace",
            "translation_key": "ace_slot_1",
        },
    ]

    async def fake_registries():
        return devices, entities

    monkeypatch.setattr(adapter, "_registries", fake_registries)
    found = await adapter.discover()
    assert found[0]["device_id"] == "printer"
    assert found[0]["ace_device_id"] == "ace"


@pytest.mark.asyncio
async def test_concurrent_start_creates_only_one_websocket_lifecycle(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test")
    adapter = AnycubicHomeAssistantAdapter("printer")
    resolves = refreshes = 0

    async def resolve():
        nonlocal resolves
        resolves += 1

    async def refresh():
        nonlocal refreshes
        refreshes += 1
        return {}

    async def watch():
        await adapter._stop_event.wait()

    monkeypatch.setattr(adapter, "resolve", resolve)
    monkeypatch.setattr(adapter, "_refresh_states", refresh)
    monkeypatch.setattr(adapter, "_watch_state_changes", watch)
    await asyncio.gather(adapter.start(), adapter.start())

    assert resolves == 1
    assert refreshes == 1
    await adapter.close()


@pytest.mark.asyncio
async def test_registry_invalidation_reresolves_entity_ids(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test")
    adapter = AnycubicHomeAssistantAdapter("printer")
    # This is the state left by an entity/device registry update event.
    adapter.entities = {}
    adapter._state_cache = None
    resolves = 0

    async def resolve():
        nonlocal resolves
        resolves += 1
        adapter.entities = {"printer_online": "binary_sensor.renamed"}

    async def ws(commands):
        assert commands == [("get_states", {})]
        return [[{"entity_id": "binary_sensor.renamed", **_row("on")}]]

    monkeypatch.setattr(adapter, "resolve", resolve)
    monkeypatch.setattr(adapter, "_ws", ws)
    states = await adapter._refresh_states()

    assert resolves == 1
    assert states["printer_online"]["state"] == "on"


@pytest.mark.asyncio
async def test_state_read_uses_rest_only_after_websocket_failure(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test")
    adapter = AnycubicHomeAssistantAdapter("printer")
    adapter.entities = {"printer_online": "binary_sensor.printer_online"}

    async def unavailable(_commands):
        from app.ha.client import HomeAssistantError

        raise HomeAssistantError("websocket unavailable")

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return _row("on")

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, *, headers):
            assert url.endswith("/binary_sensor.printer_online")
            assert headers["Authorization"] == "Bearer test"
            return Response()

    monkeypatch.setattr(adapter, "_ws", unavailable)
    monkeypatch.setattr("app.ha.client.httpx.AsyncClient", lambda **_kwargs: Client())
    states = await adapter._refresh_states()

    assert states["printer_online"]["state"] == "on"
