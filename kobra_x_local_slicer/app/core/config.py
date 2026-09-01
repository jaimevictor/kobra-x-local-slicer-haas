from __future__ import annotations
import json
import os
from dataclasses import dataclass
from pathlib import Path
from .security import validate_printer_host


@dataclass
class Settings:
    data_dir: Path = Path(os.getenv("KOBRA_DATA_DIR", "/data"))
    profile_dir: Path = Path(
        os.getenv("KOBRA_PROFILE_DIR", "/opt/kobra/profiles/resolved")
    )
    printer_host: str = ""
    ha_device_id: str = ""
    slicing_timeout_seconds: int = 600
    upload_limit_bytes: int = 64 * 1024 * 1024
    decompressed_3mf_limit_bytes: int = 256 * 1024 * 1024
    gcode_limit_bytes: int = 512 * 1024 * 1024
    jobs_storage_limit_bytes: int = 1024 * 1024 * 1024
    retention_hours: int = 24
    max_jobs: int = 25
    max_concurrent_slicers: int = 1

    @classmethod
    def load(cls, *, data_dir: Path | None = None) -> "Settings":
        """Load defaults < add-on options < UI config < explicit environment.

        The UI only persists its two connection choices in ``config.json``; add-on
        options own operational limits.  Environment variables deliberately win
        for supervised/deployment overrides without rewriting either file.
        """
        s = cls(data_dir=data_dir) if data_dir is not None else cls()
        path = s.data_dir / "config.json"
        options = s.data_dir / "options.json"
        if options.is_file():
            raw_options = json.loads(options.read_text(encoding="utf-8"))
            s.printer_host = str(raw_options.get("printer_host", s.printer_host))
            s.ha_device_id = str(raw_options.get("ha_device_id", s.ha_device_id))
            for name, factor in (
                ("upload_limit_mib", 1024 * 1024),
                ("decompressed_3mf_limit_mib", 1024 * 1024),
                ("gcode_limit_mib", 1024 * 1024),
                ("jobs_storage_limit_mib", 1024 * 1024),
            ):
                destination = name.replace("_mib", "_bytes")
                if name in raw_options:
                    setattr(s, destination, int(raw_options[name]) * factor)
            if "slicing_timeout_seconds" in raw_options:
                s.slicing_timeout_seconds = int(raw_options["slicing_timeout_seconds"])
            if "retention_hours" in raw_options:
                s.retention_hours = int(raw_options["retention_hours"])
            if "max_jobs" in raw_options:
                s.max_jobs = int(raw_options["max_jobs"])
            if "max_concurrent_slicers" in raw_options:
                s.max_concurrent_slicers = int(raw_options["max_concurrent_slicers"])
        if path.is_file():
            raw = json.loads(path.read_text(encoding="utf-8"))
            s.printer_host = str(raw.get("printer_host", s.printer_host))
            s.ha_device_id = str(raw.get("ha_device_id", s.ha_device_id))
            for key in ("slicing_timeout_seconds", "retention_hours"):
                if key in raw:
                    setattr(s, key, int(raw[key]))
        if host := os.getenv("KOBRA_PRINTER_HOST"):
            s.printer_host = host
        if device_id := os.getenv("KOBRA_HA_DEVICE_ID"):
            s.ha_device_id = device_id
        return s

    def save_config(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "config.json").write_text(
            json.dumps(
                {
                    "printer_host": validate_printer_host(self.printer_host),
                    "ha_device_id": self.ha_device_id,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
