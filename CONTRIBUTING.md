# Contributing

Contributions are welcome through focused issues and pull requests.

## Development setup

1. Use Linux with Python 3.10 or newer.
2. Run `python3 -m py_compile fan_control.py`.
3. Run `bash -n fan-control`.
4. Use `./fan-control --doctor` and `./fan-control --discover` for read-only checks.
5. Do not run `--apply` on unverified hardware.

## Pull requests

- Keep the runtime dependency-free beyond standard Linux utilities.
- Preserve keyboard-only operation and terminal mouse compatibility.
- Never include `/sys` paths tied to a changing `hwmonN` number.
- Add migration logic before changing the JSON configuration schema.
- Document user-facing keys, commands, and safety behavior.
- Avoid commits containing exported profiles, local configuration, or hardware logs.

## Style

Use Python type hints, clear names, fail-closed hardware writes, and concise
functions. Test both direct and symlinked launchers.
