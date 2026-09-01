from __future__ import annotations

import asyncio
import json
import ssl
import threading
import time
import uuid
from typing import Any

import aiohttp
from anycubic_cloud_api.lan.client import AnycubicLANClient
from anycubic_cloud_api.lan.handshake import AnycubicLANBroker, AnycubicLANHandshake
from paho.mqtt import client as mqtt

from app.core.models import PrintStartResult


class KobraLanError(RuntimeError):
    pass


class ValidatedLegacyLanStart:
    """Temporary direct-LAN transport for upload bootstrap and one-shot start.

    It deliberately exposes no ACE/status/print monitor API. Hardware state and
    controls are supplied exclusively by Home Assistant anycubic_cloud.
    """

    def __init__(self, host: str):
        self.host = host
        self._in_flight = False

    async def close(self) -> None:
        # Connections are strictly scoped to each operation.
        return None

    @property
    def connected(self) -> bool:
        return self._in_flight

    async def upload_bootstrap(
        self, *, timeout: float = 10.0
    ) -> tuple[dict[str, Any], str]:
        """Obtain only the printer-supplied upload URL, then close LAN immediately."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()

        def on_message(topic: str, message_type: str, payload: dict[str, Any]) -> None:
            if message_type == "info" and not future.done():
                loop.call_soon_threadsafe(future.set_result, payload)

        self._in_flight = True
        http = aiohttp.ClientSession()
        client: AnycubicLANClient | None = None
        try:
            broker = await AnycubicLANHandshake(http, self.host).async_authenticate()
            client = AnycubicLANClient(broker, on_message)
            await client.async_connect()
            client.query("info")
            return await asyncio.wait_for(future, timeout), broker.device_id
        except TimeoutError as exc:
            raise KobraLanError("timeout waiting for upload bootstrap info") from exc
        finally:
            if client:
                await client.async_disconnect()
            await http.close()
            self._in_flight = False

    async def publish_print_start_once(
        self, data: dict[str, Any], *, ack_timeout: float = 10.0
    ) -> PrintStartResult:
        self._in_flight = True
        http = aiohttp.ClientSession()
        try:
            broker = await AnycubicLANHandshake(http, self.host).async_authenticate()
            client = AnycubicLANClient(broker, lambda *_: None)
            return await asyncio.to_thread(
                publish_once_no_retry,
                broker,
                client.query_topic("print"),
                client.report_topic,
                data,
                ack_timeout,
            )
        finally:
            await http.close()
            self._in_flight = False


# Compatibility alias; new code should use ValidatedLegacyLanStart.
KobraLanSession = ValidatedLegacyLanStart


def _ssl_context() -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _client(client_id: str) -> mqtt.Client:
    try:
        return mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION1,
            client_id=client_id,
            reconnect_on_failure=False,
        )
    except (AttributeError, TypeError):
        c = mqtt.Client(client_id=client_id)
        # paho 1.x has no reconnect_on_failure constructor switch; the manual loop below never calls reconnect.
        return c


def publish_once_no_retry(
    broker: AnycubicLANBroker,
    query_topic: str,
    report_topic: str,
    data: dict[str, Any],
    ack_timeout: float = 10.0,
) -> PrintStartResult:
    """Send print/start at most once.

    There is deliberately no retry path. Any uncertainty after publish() is START_UNKNOWN upstream.
    """
    command_id = str(uuid.uuid4())
    envelope = {
        "type": "print",
        "action": "start",
        "timestamp": int(time.time() * 1000),
        "msgid": command_id,
        "data": data,
    }
    connected = threading.Event()
    subscribed = threading.Event()
    ack = threading.Event()
    ack_payload: dict[str, Any] | None = None
    disconnected_after_send = threading.Event()
    sent = False

    c = _client(f"kx-once-{uuid.uuid4().hex[:10]}")
    c.username_pw_set(broker.username, broker.password)
    c.tls_set_context(_ssl_context())

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            connected.set()
            client.subscribe(f"{report_topic}/#", qos=0)

    def on_subscribe(client, userdata, mid, granted_qos):
        subscribed.set()

    def on_disconnect(client, userdata, rc):
        if sent:
            disconnected_after_send.set()

    def on_message(client, userdata, message):
        nonlocal ack_payload
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        if payload.get("type") != "print" or payload.get("action") != "start":
            return
        # Prefer msgid correlation when firmware echoes it, but accept the validated action/state/code ACK shape.
        if payload.get("msgid") not in {None, "", command_id}:
            return
        ack_payload = payload
        ack.set()

    c.on_connect = on_connect
    c.on_subscribe = on_subscribe
    c.on_disconnect = on_disconnect
    c.on_message = on_message
    try:
        c.connect(broker.host, broker.port, keepalive=20)
        deadline = time.monotonic() + min(ack_timeout, 10)
        while not subscribed.is_set() and time.monotonic() < deadline:
            c.loop(timeout=0.1)
        if not subscribed.is_set():
            raise KobraLanError(
                "one-shot MQTT could not establish subscribed connection"
            )
        info = c.publish(
            query_topic,
            json.dumps(envelope, separators=(",", ":")),
            qos=0,
            retain=False,
        )
        sent = True
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            # publish was attempted; do not retry because physical delivery is uncertain.
            return PrintStartResult(
                sent=True, ack_received=False, accepted=False, unknown=True
            )
        deadline = time.monotonic() + ack_timeout
        while (
            not ack.is_set()
            and time.monotonic() < deadline
            and not disconnected_after_send.is_set()
        ):
            c.loop(timeout=0.1)
        if not ack.is_set():
            return PrintStartResult(
                sent=True, ack_received=False, accepted=False, unknown=True
            )
        assert ack_payload is not None
        state = str(
            ack_payload.get("state")
            or (ack_payload.get("data") or {}).get("state")
            or ""
        ).lower()
        code = ack_payload.get("code")
        if code is None and isinstance(ack_payload.get("data"), dict):
            code = ack_payload["data"].get("code")
        accepted = code == 200 and state in {"checking", "heating", "printing"}
        return PrintStartResult(
            sent=True,
            ack_received=True,
            accepted=accepted,
            unknown=not accepted,
            raw_ack=ack_payload,
        )
    except Exception:
        if sent:
            return PrintStartResult(
                sent=True, ack_received=False, accepted=False, unknown=True
            )
        raise
    finally:
        try:
            c.disconnect()
        except Exception:
            pass
