# Security policy and threat model

## Primary controls

- LAN-only printer operations; no Anycubic cloud dependency.
- Home Assistant authentication delegated to Ingress; direct HTTP access denied except the
  Supervisor Ingress proxy address.
- `SUPERVISOR_TOKEN` is process environment only and is never persisted.
- Upload URL is validated against the configured printer host, fixed port/path/scheme and token
  requirement before every request; redirects are disabled to prevent SSRF pivoting.
- 3MF is treated as hostile ZIP/XML input: traversal, symlink, decompression and ratio guards,
  bounded metadata reads, defused XML parsing and fail-closed plate/color inspection.
- Project 3MF slicing settings are stripped before the Orca subprocess.
- Filenames are normalized to a restricted ASCII basename.
- Upload is streamed and bounded; job storage has a logical quota and retention policy.
- Orca runs with a subprocess wall-clock timeout and output file-size validation.
- G-code is validated after Orca and approval is tied to SHA-256.
- `print/start` has strict at-most-once semantics.

## Secrets

Never log or persist:

- the dynamic `s` upload token
- the LAN handshake broker password
- `SUPERVISOR_TOKEN`

Broker credentials remain only in process memory for the LAN session.

## Reporting

If this repository is published, configure a private security-advisory contact in the hosting
platform before public release. Do not place live printer captures, LAN credentials, Supervisor
tokens or upload URLs containing `s=` in public issues.
