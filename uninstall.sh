#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${FANTOP_INSTALL_DIR:-$HOME/.local/share/fantop}"
BIN_DIR="${FANTOP_BIN_DIR:-$HOME/.local/bin}"
SYSTEM_LAUNCHER="${FANTOP_SYSTEM_LAUNCHER:-/usr/local/bin/fantop}"

if [[ -x "$INSTALL_DIR/fantop" ]]; then
  read -r -p "Restore configured fans to firmware/automatic control first? [Y/n] " answer
  if [[ ! "$answer" =~ ^[Nn]$ ]]; then
    sudo "$INSTALL_DIR/fantop" --restore-auto
  fi
  sudo "$INSTALL_DIR/fantop" --uninstall-scheduler
fi
rm -f "$BIN_DIR/fantop"
rm -f "$BIN_DIR/fan-control"
if [[ -L "$SYSTEM_LAUNCHER" ]]; then sudo rm -f "$SYSTEM_LAUNCHER"; fi
rm -rf "$INSTALL_DIR"
echo "fantop removed."
