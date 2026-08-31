# Kobra X LAN protocol contract used by V1

This document records only behavior implemented by this App. It does not assign undocumented
meanings to printer error codes.

## LAN session and queries

`anycubic-cloud-api==0.4.26` provides the LAN handshake, ephemeral broker credentials and normal
idempotent local MQTT query client. The App uses fresh queries for:

- `info/query`
- `multiColorBox/getInfo`
- print status reports used for reconciliation

ACE is normalized to `(human_slot, protocol_slot_index, material_type, rgb, loaded)` while
keeping `raw`, `parsed` and `normalized` representations separately. Missing input fields remain
missing/`None`; they are not converted to `-1`.

## Upload

`info/query` supplies a dynamic `fileUploadurl`. Before HTTP:

- scheme must be `http`
- host must exactly match configured `printer_host`
- port must be `18910`
- path must be `/gcode_upload`
- query must contain exactly one non-empty `s` token
- userinfo/fragments are forbidden
- redirects are disabled

Multipart fields are `filename` and `gcode`. The client sends the observed BBL-style header names
with its own truthful client identity. The dynamic token is never logged or stored.

An upload is accepted only when HTTP status is 200, JSON `code` is 200, and `data.gcode` equals
the requested remote filename. `file/listLocal` and `file/fileDetails` are deliberately not part
of the acceptance gate.

## print/start

V1 sends:

```json
{
  "filename": "<uploaded>.gcode",
  "taskid": "<unix-seconds>",
  "use_ams": true,
  "ams_box_mapping": [
    {"slot_index": 0, "material_type": "PLA", "color": [33, 39, 33]}
  ]
}
```

The envelope is `type=print`, `action=start`. Human slots are 1-based; protocol slots are 0-based.

The physical command uses a separate Paho connection with reconnect-on-failure disabled and a
manual network loop. It subscribes before the single QoS0 publish. There is no retry branch.
After any post-publish uncertainty, the caller records `START_UNKNOWN` and performs query-only
reconciliation. A second `print/start` is never emitted automatically.

A positive ACK is `code=200` with state `checking`, `heating` or `printing`. When ACK is missing,
a subsequent active print state plus the exact expected filename can promote the job to accepted.

## Temperature policy

Post-start telemetry is not the primary safety gate. Generated G-code is parsed before approval
and its nozzle/bed targets are checked against the resolved PLA profile. The V1 official profile
pins nozzle range 190–230 °C; the observed transient 250 °C post-start value is therefore not used
as a slicing parameter.
