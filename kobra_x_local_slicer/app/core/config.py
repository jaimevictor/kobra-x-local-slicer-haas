from __future__ import annotations
import json, os
from dataclasses import dataclass
from pathlib import Path
from .security import validate_printer_host

@dataclass
class Settings:
    data_dir: Path = Path(os.getenv('KOBRA_DATA_DIR','/data'))
    profile_dir: Path = Path(os.getenv('KOBRA_PROFILE_DIR','/opt/kobra/profiles/resolved'))
    printer_host: str = ''
    ha_device_id: str = ''
    ha_entity_map: dict | None = None
    ha_ace_entity_map: dict | None = None
    slicing_timeout_seconds: int = 600
    upload_limit_bytes: int = 64*1024*1024
    decompressed_3mf_limit_bytes: int = 256*1024*1024
    gcode_limit_bytes: int = 512*1024*1024
    jobs_storage_limit_bytes: int = 1024*1024*1024
    retention_hours: int = 24
    @classmethod
    def load(cls) -> 'Settings':
        s=cls(); path=s.data_dir/'config.json'
        options=s.data_dir/'options.json'
        if options.is_file():
            raw_options=json.loads(options.read_text(encoding='utf-8'))
            for name, factor in (('upload_limit_mib',1024*1024),('decompressed_3mf_limit_mib',1024*1024),('gcode_limit_mib',1024*1024),('jobs_storage_limit_mib',1024*1024)):
                destination=name.replace('_mib','_bytes')
                if name in raw_options: setattr(s,destination,int(raw_options[name])*factor)
            if 'slicing_timeout_seconds' in raw_options: s.slicing_timeout_seconds=int(raw_options['slicing_timeout_seconds'])
            if 'retention_hours' in raw_options: s.retention_hours=int(raw_options['retention_hours'])
        if path.is_file():
            raw=json.loads(path.read_text(encoding='utf-8')); s.printer_host=raw.get('printer_host',''); s.ha_device_id=raw.get('ha_device_id',''); s.ha_entity_map=raw.get('ha_entity_map'); s.ha_ace_entity_map=raw.get('ha_ace_entity_map')
            for key in ('slicing_timeout_seconds','retention_hours'):
                if key in raw: setattr(s,key,int(raw[key]))
        return s
    def save_config(self) -> None:
        self.data_dir.mkdir(parents=True,exist_ok=True); (self.data_dir/'config.json').write_text(json.dumps({'printer_host':validate_printer_host(self.printer_host),'ha_device_id':self.ha_device_id,'ha_entity_map':self.ha_entity_map or {},'ha_ace_entity_map':self.ha_ace_entity_map or {}},indent=2),encoding='utf-8')
