#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${FANTOP_INSTALL_DIR:-$HOME/.local/share/fantop}"
BIN_DIR="${FANTOP_BIN_DIR:-$HOME/.local/bin}"
SYSTEM_DIR="/usr/local/lib/fantop"
SYSTEM_LAUNCHER="/usr/local/bin/fantop"
if [[ $EUID -eq 0 ]]; then ROOT_CMD=(); else ROOT_CMD=(sudo); fi

if [[ -x "$INSTALL_DIR/fantop" ]]; then
  read -r -p "Restore configured fans to firmware/automatic control after removing the scheduler? [Y/n] " answer
  "${ROOT_CMD[@]}" "$SYSTEM_LAUNCHER" --uninstall-scheduler
  if [[ ! "$answer" =~ ^[Nn]$ ]]; then
    "${ROOT_CMD[@]}" "$SYSTEM_LAUNCHER" --restore-auto
  fi
fi
rm -f "$BIN_DIR/fantop"
rm -f "$BIN_DIR/fan-control"
if [[ -f "$SYSTEM_LAUNCHER" ]] && grep -qFx '# fantop system launcher (managed)' "$SYSTEM_LAUNCHER"; then
  "${ROOT_CMD[@]}" rm -f "$SYSTEM_LAUNCHER"
fi
"${ROOT_CMD[@]}" rm -f "$SYSTEM_DIR/fantop.py"
"${ROOT_CMD[@]}" rmdir "$SYSTEM_DIR" 2>/dev/null || true
"${ROOT_CMD[@]}" rm -f /var/lib/fantop/state.json
"${ROOT_CMD[@]}" rm -f /var/lib/fantop/fantop.log /var/lib/fantop/fantop.log.[0-9]*
"${ROOT_CMD[@]}" rmdir /var/lib/fantop 2>/dev/null || true
rm -rf "$INSTALL_DIR"
echo "fantop removed."
