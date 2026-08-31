from app.ha.client import suggest_ace_entity_map, suggest_entity_map


def test_anycubic_documented_entity_keys_are_suggested():
    entities = [
        {"entity_id": "binary_sensor.kobra_printer_online", "translation_key": "printer_online"},
        {"entity_id": "binary_sensor.kobra_is_available", "translation_key": "is_available"},
        {"entity_id": "binary_sensor.kobra_is_busy", "translation_key": "is_busy"},
        {"entity_id": "binary_sensor.kobra_job_in_progress", "translation_key": "job_in_progress"},
        {"entity_id": "sensor.kobra_current_status", "translation_key": "current_status"},
        {"entity_id": "sensor.kobra_job_name", "translation_key": "job_name"},
        {"entity_id": "binary_sensor.kobra_job_failed", "translation_key": "job_failed"},
    ]
    mapping, unresolved = suggest_entity_map(entities)
    assert not unresolved
    assert mapping["online"] == "binary_sensor.kobra_printer_online"
    assert mapping["state"] == "sensor.kobra_current_status"
    assert mapping["filename"] == "sensor.kobra_job_name"
    assert mapping["current_fault"] == "binary_sensor.kobra_job_failed"
    assert mapping["error_entities"] == ["binary_sensor.kobra_job_failed"]


def test_ace_child_device_entities_are_mapped_separately():
    entities = [
        {"entity_id": "sensor.kobra_ace_ace_slot_1", "translation_key": "ace_slot_1"},
        {"entity_id": "sensor.kobra_ace_ace_slot_2", "translation_key": "ace_slot_2"},
        {"entity_id": "sensor.kobra_ace_ace_loaded_slot", "translation_key": "ace_loaded_slot"},
    ]
    mapping = suggest_ace_entity_map(entities)
    assert mapping == {
        "slot_1": "sensor.kobra_ace_ace_slot_1",
        "slot_2": "sensor.kobra_ace_ace_slot_2",
        "loaded_slot": "sensor.kobra_ace_ace_loaded_slot",
    }
