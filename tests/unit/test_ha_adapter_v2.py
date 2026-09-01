from datetime import UTC, datetime

import pytest

from app.ha.client import AnycubicHomeAssistantAdapter, suggest_entity_map


def _row(state, **attributes):
    return {"state": state, "attributes": attributes, "last_updated": datetime.now(UTC).isoformat()}


def test_entity_id_text_is_never_used_as_a_fallback():
    mapping, unresolved = suggest_entity_map([
        {"entity_id": "binary_sensor.renamed_printer_online", "translation_key": None},
    ])
    assert mapping == {}
    assert "online" in unresolved


def test_ace_snapshot_preserves_attributes_and_unknowns(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test")
    adapter = AnycubicHomeAssistantAdapter("printer")
    ace = adapter._ace({
        "ace_loaded_slot": _row("2"),
        "ace_slot_1": _row("unknown", slot=1, color_hex="#010203", spool_loaded=False),
        "ace_slot_2": _row("PLA", slot=2, color_hex="#aabbcc", sku="sku", spool_loaded=True, consumables_percent="37"),
    })
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
        "printer_online": _row("unknown"), "is_available": _row("off"), "is_busy": _row("0"),
        "job_in_progress": _row("false"), "current_status": _row("idle"), "job_name": _row("none"),
        "job_progress": _row("0"), "job_is_paused": _row("unavailable"),
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
async def test_discovery_links_ace_only_through_via_device_id(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test")
    adapter = AnycubicHomeAssistantAdapter()
    devices = [{"id": "printer", "name": "Renamed"}, {"id": "ace", "via_device_id": "printer"}]
    entities = [
        {"entity_id": "binary_sensor.whatever", "platform": "anycubic_cloud", "device_id": "printer", "translation_key": "printer_online"},
        {"entity_id": "sensor.status", "platform": "anycubic_cloud", "device_id": "printer", "translation_key": "current_status"},
        {"entity_id": "sensor.ace_any_name", "platform": "anycubic_cloud", "device_id": "ace", "translation_key": "ace_slot_1"},
    ]

    async def fake_registries():
        return devices, entities

    monkeypatch.setattr(adapter, "_registries", fake_registries)
    found = await adapter.discover()
    assert found[0]["device_id"] == "printer"
    assert found[0]["ace_device_id"] == "ace"
