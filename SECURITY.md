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

No warranty is provided. Select and add an appropriate open-source license
before publishing or accepting external contributions.
