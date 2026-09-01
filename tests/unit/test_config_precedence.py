import json

from app.core.config import Settings


def test_connection_settings_follow_documented_precedence(monkeypatch, tmp_path):
    (tmp_path / "options.json").write_text(
        json.dumps(
            {
                "printer_host": "192.168.1.10",
                "ha_device_id": "from-options",
                "max_jobs": 11,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "config.json").write_text(
        json.dumps(
            {"printer_host": "192.168.1.20", "ha_device_id": "from-ui"}
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("KOBRA_PRINTER_HOST", "192.168.1.30")
    monkeypatch.setenv("KOBRA_HA_DEVICE_ID", "from-env")
    settings = Settings.load(data_dir=tmp_path)

    assert settings.printer_host == "192.168.1.30"
    assert settings.ha_device_id == "from-env"
    assert settings.max_jobs == 11
