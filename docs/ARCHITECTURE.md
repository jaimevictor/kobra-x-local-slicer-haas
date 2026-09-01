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
   ├── AnycubicHomeAssistantAdapter (public HA registry/state/service APIs)
   ├── DirectLanFileTransfer (strict local HTTP upload only)
   ├── ValidatedLegacyLanStart (one-shot, no-retry print/start only)
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

Final preflight requires a fresh, complete `anycubic_cloud` snapshot. Missing, `unknown`,
`unavailable` and stale essential values fail closed; these values are never converted to false,
zero or idle. ACE material and slot state are also read only from that snapshot.

## v2 Home Assistant boundary

```text
anycubic_cloud public registries + state changes + button.press
                         │
                         ▼
             AnycubicHomeAssistantAdapter
              ├── PrinterSnapshot / ACE / faults
              ├── capabilities
              └── pause, resume, cancel
                         │
                         ▼
                  Print Manager jobs
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
DirectLanFileTransfer       ValidatedLegacyLanStart
 upload only                 start only, at-most-once
```

The selected printer `device_id` is the only persisted HA selection. On discovery/reload the
adapter resolves entities from the entity registry with `platform == anycubic_cloud` and exact
`translation_key`; ACE child devices are included only through `via_device_id`. It does not use
friendly names or entity-id suffixes. HA state is the hardware source of truth. The two direct
LAN classes are retained only for the currently validated upload/start transport and do not expose
ACE parsing, telemetry polling, pause/resume/cancel or reconciliation.

| `translation_key` | `PrinterSnapshot` field |
|---|---|
| `printer_online`, `is_available`, `is_busy`, `current_status` | `online`, `available`, `busy`, `status` |
| `job_name`, `job_state`, `job_progress`, `job_is_paused` | `job.name`, `job.state`, `job.progress`, `job.paused` |
| `job_current_layer`, `job_total_layers`, `job_time_elapsed`, `job_time_remaining`, `job_eta` | corresponding `job.*` field |
| `curr_nozzle_temp`, `target_nozzle_temp`, `curr_hotbed_temp`, `target_hotbed_temp` | corresponding `thermal.*` field |
| `last_error_code`, `last_error` | `fault.code`, `fault.message` |
| `ace_loaded_slot`, `ace_slot_1` … `ace_slot_4`, `ace_spools` | `ace.loaded_slot`, `ace.normalized` |

| Command | Actual transport |
|---|---|
| Pause / resume / cancel | `button.press` through Home Assistant |
| G-code upload | `DirectLanFileTransfer` (printer local HTTP) |
| Start | `ValidatedLegacyLanStart` (single MQTT publish; no retry) |

If ACE material changes from PLA, the slice is invalidated. If only RGB changes, the slice may
remain technically valid but the mapping/preview are refreshed and human confirmation is cleared.

## Runtime isolation

Nginx is the only listener on 8099 and allows only the documented Home Assistant Ingress proxy
address. FastAPI binds only `127.0.0.1:8098`. Frontend fetches are relative (`./api`, `./static`) so
the dynamic Ingress path prefix is preserved.
