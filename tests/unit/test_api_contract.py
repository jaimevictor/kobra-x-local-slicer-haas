from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app


def test_read_only_api_contract_without_printer_configuration(monkeypatch, tmp_path):
    monkeypatch.setattr(
        Settings,
        "load",
        classmethod(lambda cls: cls(data_dir=tmp_path)),
    )

    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json() == {
            "ok": True,
            "printer_host_configured": False,
            "ha_device_configured": False,
            "integration_error": None,
            "lan_transport_configured": False,
            "ha_accessible": False,
            "integration_resolved": False,
            "snapshot_available": False,
            "printer_online": None,
        }
        assert client.get("/api/jobs/active").json() == []
        assert client.get("/api/jobs/recent").json() == []
        assert client.get("/api/printer/state").status_code == 400
        assert client.get("/api/printer/capabilities").status_code == 400
        assert client.get("/api/printer/integration").status_code == 400
