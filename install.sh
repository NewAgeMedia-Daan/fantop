#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${FANTOP_INSTALL_DIR:-$HOME/.local/share/fantop}"
BIN_DIR="${FANTOP_BIN_DIR:-$HOME/.local/bin}"
SYSTEM_LAUNCHER="${FANTOP_SYSTEM_LAUNCHER:-/usr/local/bin/fantop}"

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
if [[ -L "$SYSTEM_LAUNCHER" && "$(readlink -f -- "$SYSTEM_LAUNCHER")" == "$INSTALL_DIR/fantop" ]]; then
  :
elif [[ -w "$(dirname -- "$SYSTEM_LAUNCHER")" ]]; then
  ln -sfn "$INSTALL_DIR/fantop" "$SYSTEM_LAUNCHER"
elif command -v sudo >/dev/null 2>&1; then
  sudo ln -sfn "$INSTALL_DIR/fantop" "$SYSTEM_LAUNCHER"
else
  echo "Warning: could not install $SYSTEM_LAUNCHER; use sudo with the full fantop path." >&2
fi

echo "Installed fantop to $INSTALL_DIR"
echo "Launcher: $BIN_DIR/fantop"
echo "System launcher: $SYSTEM_LAUNCHER"
"$BIN_DIR/fantop" --doctor
echo "Next: run 'fantop --setup', inspect curves, then Save in the TUI."
