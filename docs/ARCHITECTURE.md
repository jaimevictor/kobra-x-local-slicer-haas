# Architecture

## Components

```text
Home Assistant UI
   │ authenticated Ingress
   ▼
Supervisor ingress proxy 172.30.32.2
   │ :8099
   ▼
Nginx (allow 172.30.32.2; deny all)
   │ loopback only
   ▼
FastAPI :8098
   ├── /data job store + state machine
   ├── Supervisor/Core REST + WebSocket (SUPERVISOR_TOKEN)
   ├── anycubic-cloud-api 0.4.26 LAN handshake/query MQTT
   ├── strict local HTTP upload client
   ├── one-shot no-retry MQTT print/start client
   └── Xvfb + OrcaSlicer 2.4.2 subprocess
```

No privileged mode, host networking, Docker socket, USB/UART, HA Core filesystem import or
manual long-lived token is used.

## 3MF trust boundary

The original upload is immutable evidence. It is first inspected as a bounded ZIP with path
traversal, symlink, decompressed-size and compression-ratio checks. Plate assignment is derived
from Orca/Bambu `Metadata/model_settings.config` / `plater_id` when present, with standard 3MF
`<build>` as the fallback only when it is unambiguous. Multiple plates produce the required
Portuguese rejection and ambiguous plate counts fail closed.

Multicolor is rejected from painted triangle attributes, multiple material property assignments,
extruder assignments above 1, and custom layer tool-change data.

After inspection, `input_sanitized.3mf` is generated for Orca. It removes project/profile and
per-object slicing metadata such as `project_settings.config`, `model_settings.config`, embedded
machine/process/filament presets, custom per-layer G-code and layer config overrides. Core 3MF
geometry/resources remain. Therefore the Orca subprocess receives geometry plus the App's own
flattened Kobra X profiles, not the uploader's slicing profiles.

## Profile provenance

At image build time the exact Orca 2.4.2 AppImage is SHA-256 verified and extracted without
FUSE. The official Anycubic vendor profile directory is located dynamically under the extracted
AppImage. The resolver creates:

- `kobra_x_04.resolved.json`
- `kobra_x_020_standard.resolved.json`
- `anycubic_pla_kobra_x.resolved.json`
- `manifest.json`

The manifest records source files, source SHA-256s, resolved SHA-256s, Orca version/ref and
source commit. Profile files are baked into the image and never modified from the frontend.

## Print transaction

```text
UPLOADED -> INSPECTING -> READY_TO_SLICE -> SLICING -> SLICED
-> AWAITING_CONFIRMATION -> PREFLIGHT -> UPLOADING_TO_PRINTER
-> UPLOADED_TO_PRINTER -> STARTING
      ├── ACK/evidence -> PRINT_ACCEPTED -> MONITORING
      └── uncertain   -> START_UNKNOWN --query-only--> PRINT_ACCEPTED/MONITORING
```

There is no `SLICED -> PRINT` transition. The user approval stores the current G-code SHA-256,
ACE slot snapshot and table-clear checkbox. Changes invalidate the approval.

Final preflight requires fresh LAN state and fresh HA cross-check values. Missing safety-critical
HA roles fail closed. An unchanged sticky historical error is ignored; a changed/new active error
or current fault blocks.

If ACE material changes from PLA, the slice is invalidated. If only RGB changes, the slice may
remain technically valid but the mapping/preview are refreshed and human confirmation is cleared.

## Runtime isolation

Nginx is the only listener on 8099 and allows only the documented Home Assistant Ingress proxy
address. FastAPI binds only `127.0.0.1:8098`. Frontend fetches are relative (`./api`, `./static`) so
the dynamic Ingress path prefix is preserved.
