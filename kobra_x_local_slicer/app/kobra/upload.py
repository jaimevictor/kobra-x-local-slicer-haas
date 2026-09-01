from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any

import aiohttp

from app.core.security import validate_upload_url


class UploadError(RuntimeError):
    pass


def extract_upload_url(info_payload: dict[str, Any]) -> str:
    data = info_payload.get("data") if isinstance(info_payload.get("data"), dict) else info_payload
    urls = data.get("urls") if isinstance(data, dict) else None
    if isinstance(urls, dict) and isinstance(urls.get("fileUploadurl"), str):
        return urls["fileUploadurl"]
    matches: list[str] = []
    def walk(v: Any) -> None:
        if isinstance(v, dict):
            for k, child in v.items():
                if k == "fileUploadurl" and isinstance(child, str):
                    matches.append(child)
                else:
                    walk(child)
        elif isinstance(v, list):
            for child in v: walk(child)
    walk(info_payload)
    if len(set(matches)) != 1:
        raise UploadError("info/query did not contain exactly one fileUploadurl")
    return matches[0]


def validate_upload_response(status: int, body: dict[str, Any], filename: str) -> None:
    if status != 200:
        raise UploadError(f"upload HTTP status {status}")
    if body.get("code") != 200:
        raise UploadError("printer rejected upload")
    data = body.get("data")
    if not isinstance(data, dict) or data.get("gcode") != filename:
        raise UploadError("upload response filename mismatch")


class DirectLanFileTransfer:
    """The narrowly-scoped, validated direct HTTP file transfer exception.

    This class has no printer state, ACE, MQTT, polling, or control methods.
    """
    def __init__(self, printer_host: str, *, device_id: str, client_version: str = "2.0.0"):
        self.printer_host = printer_host
        self.device_id = device_id
        self.client_version = client_version

    async def upload(self, upload_url: str, gcode_path: Path, remote_filename: str) -> dict[str, Any]:
        validate_upload_url(upload_url, self.printer_host)
        size = gcode_path.stat().st_size
        headers = {
            "X-File-Length": str(size),
            "X-BBL-Client-Name": "KobraXLocalSlicer",
            "X-BBL-Client-Type": "slicer",
            "X-BBL-Client-Version": self.client_version,
            "X-BBL-Device-ID": self.device_id,
            "X-BBL-Language": "en-US",
            "X-BBL-OS-Type": "linux",
            "X-BBL-OS-Version": platform.release()[:80],
        }
        timeout = aiohttp.ClientTimeout(total=180, connect=10, sock_read=180)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            with gcode_path.open("rb") as fh:
                form = aiohttp.FormData()
                form.add_field("filename", remote_filename)
                form.add_field("gcode", fh, filename=remote_filename, content_type="application/octet-stream")
                async with session.post(
                    upload_url,
                    data=form,
                    headers=headers,
                    allow_redirects=False,
                ) as response:
                    text = await response.text()
                    try:
                        body = json.loads(text)
                    except json.JSONDecodeError as exc:
                        raise UploadError("upload response is not JSON") from exc
                    validate_upload_response(response.status, body, remote_filename)
                    return body


# Existing import path retained for third-party callers during the v2 transition.
KobraUploadClient = DirectLanFileTransfer
