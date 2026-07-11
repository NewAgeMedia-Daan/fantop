# Fan Control TUI — BIOS-style fan curves in your terminal

Lightweight Linux terminal fan-curve editor and controller using only Python's
standard library, `lm-sensors`, Linux hwmon sysfs, and cron. It supports color,
keyboard-only operation, and terminal mouse input.

> [!CAUTION]
> Fan Control TUI writes directly to Linux hwmon PWM controls. Verify hardware,
> sensors, and minimum safe speeds before enabling unattended operation.

## Contents

- [System requirements and prerequisites](#system-requirements-and-prerequisites)
- [Installation](#installation)
- [First-time setup](#first-time-setup)
- [Usage](#usage)
- [Safety](#safety)

## System requirements and prerequisites

Fan Control TUI requires:

- Linux with `/sys/class/hwmon` and a loaded motherboard or fan-controller driver
- At least one channel exposing `pwmN` and `pwmN_enable`; `fanN_input` is strongly
  recommended so inactive headers can be hidden and RPM can be monitored
- Python 3.10 or newer with the standard `curses` module
- `lm-sensors` for temperature discovery
- `cron`/`crond` and `crontab` for automatic curve application
- `sudo` or root access when switching PWM channels to manual mode and writing values
- A color-capable terminal of at least 90 columns by 28 rows; mouse support is optional

The application does not install or guess a kernel driver. Confirm that Linux
supports your Super I/O or fan controller before applying values. Hardware that
only exposes read-only RPM or temperature files cannot be controlled.

### Install operating-system packages

Debian, Ubuntu, and derivatives:

```bash
sudo apt update
sudo apt install python3 lm-sensors cron
sudo systemctl enable --now cron
```

Fedora and RHEL-family distributions:

```bash
sudo dnf install python3 lm_sensors cronie
sudo systemctl enable --now crond
```

Arch Linux and derivatives:

```bash
sudo pacman -S python lm_sensors cronie
sudo systemctl enable --now cronie
```

Package names can differ on other distributions. Python's curses module is
included by the packages above on most systems; some distributions package it
separately as `python3-curses`.

## Installation

Choose a stable installation directory. Cron stores the absolute path to
`fan_control.py`, so do not move or delete that directory after enabling the
schedule.

From a downloaded or cloned source directory:

```bash
install_dir="$HOME/.local/share/fan-control-tui"
mkdir -p "$install_dir" "$HOME/.local/bin"
cp fan_control.py fan-control README.md "$install_dir/"
chmod +x "$install_dir/fan-control" "$install_dir/fan_control.py"
ln -sfn "$install_dir/fan-control" "$HOME/.local/bin/fan-control"
```

Ensure `~/.local/bin` is on `PATH`, then verify the installation:

```bash
fan-control --version
fan-control --doctor
fan-control --discover
```

`--discover` shows active channels with tachometer feedback. To diagnose all
PWM headers, including unused or zero-RPM channels, run:

```bash
fan-control --discover --all-channels
```

Discovery is read-only and does not change fan speeds.

## First-time setup

1. Run `fan-control --doctor` and resolve every failed prerequisite.
2. Run `fan-control --discover` and verify the detected controller and channels.
3. Launch `fan-control`, label each active header, and review every curve.
4. Save from the TUI. Saving requests sudo access, applies the curves immediately,
   and creates or updates the managed root crontab entry.
5. Confirm that the footer shows green `CRON ACTIVE` and run
   `fan-control --status` to verify temperatures, requested PWM, live PWM, and RPM.
6. Test cooling under load before relying on unattended operation.

To set the interval from the command line instead of the TUI:

```bash
fan-control --schedule 5
sudo fan-control --install-cron
```

Supported intervals are 1, 2, 3, 5, 10, 15, 30, and 60 minutes.

## Usage

```text
fan-control                         interactive editor
fan-control --status                current temperatures/PWM/RPM
fan-control --doctor                prerequisite and hardware checks
fan-control --discover              active controllable channels
fan-control --discover --all-channels
fan-control --schedule 5            save a five-minute interval
sudo fan-control --install-cron     install/update root scheduler
sudo fan-control --apply            apply once
```

In the TUI, use 1–4 or Tab to select, arrows and +/- to edit, A/D to add/delete,
M for step/linear mode, N to label a channel, C to cycle scheduler intervals,
T to select a temperature source from the currently available sensors (with
live temperatures shown),
using the footer action `[T Temp Source]`,
F to set every point in the selected curve to PWM 255, S to save/apply, E/I to
export/import, ? for help, and Q or Ctrl+C to exit
without saving. Bare Esc never exits the utility; it only cancels the active
import, export, or rename dialog.
Mouse selection, graph editing, and buttons work in terminals supporting mouse
reporting. Right-click a yellow curve-point marker on the main editing graph to
select it. Ctrl+right-click anywhere on that graph to insert a new point at the
clicked temperature and PWM. The Help control is available through `?`, F1, or
either clickable `[? Help]` label; help remains open until the next key press.
A bold yellow dotted vertical line marks the selected fan's current controlling
sensor temperature on both its overview graph and the main editing graph.
The bottom-right indicator flashes green when the cron daemon and exact managed
root schedule are active, or red when either is missing/out of date.
PWM labels use a persistent Nano-style footer prompt reading
`Renaming / Labeling PWMN to:` with explicit Enter-confirm and Escape-cancel
controls. Temperature-source changes remain unsaved until Save is selected.

Configuration is versioned JSON at
`INSTALL_DIR/.config/nam-fan-control/config.json`. With the recommended layout,
that is `~/.local/share/fan-control-tui/.config/nam-fan-control/config.json`.
Export opens a Nano-style name prompt in the bottom status area. Type an
optional profile name, then use `Enter` to confirm or `Esc` to cancel. Named files use
`INSTALL_DIR/FanExport_NAME_YYYYMMDD_HHMMSS.json` and retain the full label
inside JSON; unnamed exports keep `INSTALL_DIR/FanExport_YYYYMMDD_HHMMSS.json`.
In the Import browser,
press `N` to rename the selected profile and its file. The import rename field
uses the same focused bottom-footer layout with explicit `Enter` confirmation
and `Esc` cancellation while other actions are hidden. Invalid imports are
rejected. Missing sensors or non-writable PWM controls fail closed without
partially choosing fallback temperatures.

## Safety

Discovering channels is read-only. Applying switches configured channels to
manual mode. Keep a firmware/BIOS fallback available and test curves under load.
The default profile includes HDD and board-temperature airflow floors. Review
and adapt every sensor mapping and safety threshold for the target hardware.
