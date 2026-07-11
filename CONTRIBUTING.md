# Contributing

Contributions are welcome through focused issues and pull requests.

## Development setup

1. Use Linux with Python 3.10 or newer.
2. Run `python3 -m py_compile fantop.py`.
3. Run `bash -n fantop install.sh uninstall.sh`.
4. Run `python3 -m unittest discover -s tests -v`.
5. Use `./fantop --doctor`, `--discover`, and `--dry-run` for read-only checks.
6. Do not run `--apply` or `--calibrate` on unverified hardware.

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
