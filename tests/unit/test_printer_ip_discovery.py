from app.ha.client import _printer_ip, _printer_ip_details


def test_configuration_url_and_registry_connections_are_not_printer_ips():
    device = {
        "configuration_url": "http://192.168.1.2:8123/config/devices/device/printer",
        "connections": [["ip", "192.168.1.47"]],
    }
    assert _printer_ip(device, [], {}) is None


def test_explicit_sensor_outranks_old_attributes_regardless_of_registry_order():
    rows = [
        {"translation_key": "printer_online", "entity_id": "binary_sensor.online"},
        {"translation_key": "ip_address", "entity_id": "sensor.ip"},
    ]
    states = {
        "binary_sensor.online": {
            "state": "on",
            "attributes": {"ip_address": "192.168.1.47"},
        },
        "sensor.ip": {"state": "192.168.1.99", "attributes": {}},
    }
    assert _printer_ip_details(rows, states) == ("192.168.1.99", "sensor.ip")
    assert _printer_ip_details(list(reversed(rows)), states) == (
        "192.168.1.99",
        "sensor.ip",
    )


def test_conflicting_attributes_require_manual_address():
    rows = [{"entity_id": "sensor.one"}, {"entity_id": "sensor.two"}]
    states = {
        "sensor.one": {"state": "on", "attributes": {"ip_address": "192.168.1.47"}},
        "sensor.two": {"state": "on", "attributes": {"printer_ip": "192.168.1.99"}},
    }
    assert _printer_ip({}, rows, states) is None


def test_restored_and_unavailable_addresses_are_not_discovered():
    rows = [{"translation_key": "ip_address", "entity_id": "sensor.ip"}]
    for state in [
        {"state": "192.168.1.47", "attributes": {"restored": True}},
        {"state": "unavailable", "attributes": {"ip_address": "192.168.1.47"}},
    ]:
        assert _printer_ip({}, rows, {"sensor.ip": state}) is None


def test_unavailable_explicit_sensor_does_not_use_incidental_attributes():
    rows = [
        {"translation_key": "ip_address", "entity_id": "sensor.ip"},
        {"entity_id": "sensor.old"},
    ]
    states = {
        "sensor.ip": {"state": "unavailable"},
        "sensor.old": {"state": "on", "attributes": {"ip_address": "192.168.1.47"}},
    }
    assert _printer_ip({}, rows, states) is None


def test_conflicting_explicit_sensors_require_manual_address():
    rows = [
        {"translation_key": "ip_address", "entity_id": "sensor.one"},
        {"translation_key": "printer_ip", "entity_id": "sensor.two"},
    ]
    assert (
        _printer_ip(
            {},
            rows,
            {
                "sensor.one": {"state": "192.168.1.47"},
                "sensor.two": {"state": "192.168.1.99"},
            },
        )
        is None
    )


def test_disabled_ip_entities_are_ignored():
    rows = [
        {
            "translation_key": "ip_address",
            "entity_id": "sensor.ip",
            "disabled_by": "user",
        }
    ]
    assert _printer_ip({}, rows, {"sensor.ip": {"state": "192.168.1.47"}}) is None


def test_non_routable_address_is_not_discovered():
    rows = [{"translation_key": "ip_address", "entity_id": "sensor.ip"}]
    for ip in ["0.0.0.0", "127.0.0.1", "224.0.0.1", "169.254.1.2"]:
        assert _printer_ip({}, rows, {"sensor.ip": {"state": ip}}) is None
