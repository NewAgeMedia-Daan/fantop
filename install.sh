#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${FAN_CONTROL_INSTALL_DIR:-$HOME/.local/share/fan-control-tui}"
BIN_DIR="${FAN_CONTROL_BIN_DIR:-$HOME/.local/bin}"

mkdir -p "$INSTALL_DIR" "$BIN_DIR"
install -m 755 "$SOURCE_DIR/fan_control.py" "$INSTALL_DIR/fan_control.py"
install -m 755 "$SOURCE_DIR/fan-control" "$INSTALL_DIR/fan-control"
install -m 644 "$SOURCE_DIR/README.md" "$INSTALL_DIR/README.md"
ln -sfn "$INSTALL_DIR/fan-control" "$BIN_DIR/fan-control"

echo "Installed Fan Control TUI to $INSTALL_DIR"
echo "Launcher: $BIN_DIR/fan-control"
"$BIN_DIR/fan-control" --doctor
echo "Next: run 'fan-control --setup', inspect curves, then Save in the TUI."
