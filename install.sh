#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${FANTOP_INSTALL_DIR:-$HOME/.local/share/fantop}"
BIN_DIR="${FANTOP_BIN_DIR:-$HOME/.local/bin}"
SYSTEM_DIR="/usr/local/lib/fantop"
SYSTEM_SCRIPT="$SYSTEM_DIR/fantop.py"
SYSTEM_LAUNCHER="/usr/local/bin/fantop"
if [[ $EUID -eq 0 ]]; then ROOT_CMD=(); else ROOT_CMD=(sudo); fi

mkdir -p "$INSTALL_DIR" "$BIN_DIR"
LEGACY_DIR="$HOME/.local/share/fan-control-tui"
LEGACY_HOME_DIR="$HOME/.config/nam-fan-control"
if [[ ! -f "$INSTALL_DIR/.config/fantop/config.json" && -f "$LEGACY_HOME_DIR/config.json" ]]; then
  mkdir -p "$INSTALL_DIR/.config/fantop"
  cp "$LEGACY_HOME_DIR/config.json" "$INSTALL_DIR/.config/fantop/config.json"
elif [[ -f "$LEGACY_DIR/.config/nam-fan-control/config.json" && ! -f "$INSTALL_DIR/.config/fantop/config.json" ]]; then
  mkdir -p "$INSTALL_DIR/.config/fantop"
  cp -a "$LEGACY_DIR/.config/nam-fan-control/." "$INSTALL_DIR/.config/fantop/"
fi
install -m 755 "$SOURCE_DIR/fantop.py" "$INSTALL_DIR/.fantop.py.new"
mv -f "$INSTALL_DIR/.fantop.py.new" "$INSTALL_DIR/fantop.py"
install -m 755 "$SOURCE_DIR/fantop" "$INSTALL_DIR/.fantop.new"
mv -f "$INSTALL_DIR/.fantop.new" "$INSTALL_DIR/fantop"
install -m 644 "$SOURCE_DIR/README.md" "$INSTALL_DIR/README.md"
ln -sfn "$INSTALL_DIR/fantop" "$BIN_DIR/fantop"
rm -f "$BIN_DIR/fan-control"
"${ROOT_CMD[@]}" install -d -m 755 "$SYSTEM_DIR"
"${ROOT_CMD[@]}" install -d -m 755 /var/lib/fantop
"${ROOT_CMD[@]}" install -m 755 "$SOURCE_DIR/fantop.py" "$SYSTEM_SCRIPT.new"
"${ROOT_CMD[@]}" mv -Tf "$SYSTEM_SCRIPT.new" "$SYSTEM_SCRIPT"
LAUNCHER_TEMP="$(mktemp)"
trap 'rm -f "$LAUNCHER_TEMP"' EXIT
printf '#!/bin/bash\n# fantop system launcher (managed)\nset -euo pipefail\nexport FANTOP_DATA_DIR=%q\nexec /usr/bin/python3 %q "$@"\n' "$INSTALL_DIR" "$SYSTEM_SCRIPT" > "$LAUNCHER_TEMP"
"${ROOT_CMD[@]}" install -m 755 "$LAUNCHER_TEMP" "$SYSTEM_LAUNCHER.new"
"${ROOT_CMD[@]}" mv -Tf "$SYSTEM_LAUNCHER.new" "$SYSTEM_LAUNCHER"
if { command -v systemctl >/dev/null 2>&1 && systemctl is-enabled --quiet fantop.timer; } ||
   "${ROOT_CMD[@]}" crontab -l 2>/dev/null | grep -Fx '# fantop (managed; do not edit)' >/dev/null; then
  "${ROOT_CMD[@]}" "$SYSTEM_LAUNCHER" --install-scheduler
fi

echo "Installed fantop to $INSTALL_DIR"
echo "Launcher: $BIN_DIR/fantop"
echo "System launcher: $SYSTEM_LAUNCHER"
"$BIN_DIR/fantop" --doctor
echo "Next: run 'fantop --setup', inspect curves, then Save in the TUI."
