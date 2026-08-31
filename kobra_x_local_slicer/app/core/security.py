from __future__ import annotations
import ipaddress, re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

class SecurityError(ValueError): pass
def sanitize_filename(name: str, *, allowed_extensions: set[str] | None = None) -> str:
    candidate = Path(name.replace('\\','/')).name
    candidate = re.sub(r"[^A-Za-z0-9._ -]", "_", candidate).strip(". ")
    if not candidate or candidate in {'.','..'}: raise SecurityError("invalid filename")
    if allowed_extensions and Path(candidate).suffix.lower() not in allowed_extensions: raise SecurityError("unsupported file extension")
    return candidate[:180]
def validate_printer_host(host: str) -> str:
    try: ipaddress.ip_address(host)
    except ValueError: raise SecurityError("printer host must be an IP address") from None
    return host
def validate_upload_url(url: str, printer_host: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != 'http' or parts.hostname != printer_host or parts.port != 18910 or parts.path != '/gcode_upload' or parts.username or parts.password or parts.fragment: raise SecurityError("unsafe upload URL")
    token = parse_qs(parts.query, keep_blank_values=True).get('s')
    if not token or len(token) != 1 or not token[0]: raise SecurityError("upload URL token missing")
