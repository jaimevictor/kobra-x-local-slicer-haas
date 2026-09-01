# Upstream path: remove the direct-LAN start fallback

`ValidatedLegacyLanStart` remains enabled only because the current Print Manager transport has
been physically validated and the reviewed `anycubic_cloud` LAN path has not. It must not be
replaced merely because `print_local_file` accepts a service call.

Before enabling `local_start_via_ha`, upstream `hass-anycubic` / `anycubic-cloud-api` needs:

- a proven `START_PRINT` LAN command and direct upload through the printer-provided
  `fileUploadurl`;
- ACE/slot mapping in the local start command;
- `msgid` response correlation and non-mocked transport tests;
- a Kobra X physical test showing exactly one start and a corresponding HA state transition;
- a released dependency version pinned by this add-on.

Until all items are satisfied, capabilities report `local_upload_via_ha`, `local_start_via_ha`,
and `local_start_with_ace_via_ha` as `false`. Cloud upload is intentionally unused by the
local-first baseline.
