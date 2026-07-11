#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${FAN_CONTROL_INSTALL_DIR:-$HOME/.local/share/fan-control-tui}"
BIN_DIR="${FAN_CONTROL_BIN_DIR:-$HOME/.local/bin}"

if [[ -x "$INSTALL_DIR/fan-control" ]]; then
  read -r -p "Restore configured fans to firmware/automatic control first? [Y/n] " answer
  if [[ ! "$answer" =~ ^[Nn]$ ]]; then
    sudo "$INSTALL_DIR/fan-control" --restore-auto
  fi
  sudo "$INSTALL_DIR/fan-control" --uninstall-scheduler
fi
rm -f "$BIN_DIR/fan-control"
rm -rf "$INSTALL_DIR"
echo "Fan Control TUI removed."
