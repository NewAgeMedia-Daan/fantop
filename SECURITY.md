# Security and safety policy

## Reporting

Please report vulnerabilities privately to the repository owner before opening
a public issue. Include the affected version, reproduction steps, and impact.

## Hardware safety

This software writes motherboard PWM controls through Linux hwmon. Incorrect
curves, sensor mappings, permissions, or driver behavior can cause overheating,
hardware damage, or data loss.

- Discovery is read-only; applying curves is not.
- Verify every PWM header and temperature source on the target machine.
- Keep firmware fan protection enabled where possible.
- Test under sustained load while independently monitoring temperatures.
- Keep a recovery path for restoring firmware/automatic fan control.
- Keep `/usr/local/bin/fantop` and `/usr/local/lib/fantop` root-owned and
  inaccessible for writing by other users; the scheduler refuses unsafe paths.
- Configured controller paths are accepted only when they resolve to a device
  listed under `/sys/class/hwmon`.
- Keep `/var/lib/fantop/recovery-config.json` root-owned and unwritable by other
  users. The emergency command uses this last applied copy if the editable
  configuration is damaged.

No warranty is provided. See the MIT license for legal terms.
