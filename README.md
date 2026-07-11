# fantop — BIOS-style fan curves in your terminal for Linux

Lightweight Linux terminal fan-curve editor and controller using only Python's
standard library, `lm-sensors`, Linux hwmon sysfs, and systemd or cron. It supports color,
keyboard-only operation, and terminal mouse input.
fantop combines a btop-style terminal experience with fail-safe control,
smoothing, calibration, rotating logs, dynamic channel setup, and systemd-first
scheduling with cron fallback.

<img width="1918" height="972" alt="Screenshot 2026-07-11 233452" src="https://github.com/user-attachments/assets/83266428-944f-41f1-98b0-7dc3c5dc4756" />
> [!CAUTION]
> fantop writes directly to Linux hwmon PWM controls. Verify hardware,
> sensors, and minimum safe speeds before enabling unattended operation.

## Contents

- [System requirements and prerequisites](#system-requirements-and-prerequisites)
- [Installation](#installation)
- [First-time setup](#first-time-setup)
- [Usage](#usage)
- [Development and testing](#development-and-testing)
- [Safety](#safety)

## System requirements and prerequisites

fantop requires:

- Linux with `/sys/class/hwmon` and a loaded motherboard or fan controller driver
- At least one channel exposing `pwmN` and `pwmN_enable`; `fanN_input` is strongly
  recommended so inactive headers can be hidden and RPM can be monitored
- Python 3.10 or newer with the standard `curses` module
- `lm-sensors` for temperature discovery
- systemd (preferred) or `cron`/`crond` with `crontab` for automatic application
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

Choose a stable installation directory. The managed scheduler stores the absolute path to
`fantop.py`, so do not move or delete that directory after enabling the
schedule.

Clone and install the latest release:

```bash
git clone https://github.com/NewAgeMedia-Daan/fantop.git
cd fantop
./install.sh
```

Or, from an already downloaded source directory:

```bash
./install.sh
```

Ensure `~/.local/bin` is on `PATH`, then verify the installation:

```bash
fantop --version
fantop --doctor
fantop --discover
```

The installer creates both `~/.local/bin/fantop` and `/usr/local/bin/fantop`, so
the utility can be launched as `fantop` from any working directory and remains
available through `sudo fantop`. It also migrates legacy configurations and
removes the previous launcher name.

`--discover` shows active channels with tachometer feedback. To diagnose all
PWM headers, including unused or zero-RPM channels, run:

```bash
fantop --discover --all-channels
```

Discovery is read-only and does not change fan speeds.

## First-time setup

1. Run `fantop --doctor` and resolve every failed prerequisite.
2. Run `fantop --discover` and verify the detected controller and channels.
3. Run `fantop --setup` to generate a configuration from active channels.
   Existing configurations require `fantop --setup --yes` to replace them.
4. Launch `fantop`, label each active header, select temperature sources,
   and review every curve.
5. Save from the TUI. Saving requests sudo access, applies the curves immediately,
   and creates or updates the managed systemd timer or root cron fallback.
6. Confirm that the footer shows green `SCHEDULE ACTIVE` and run
   `fantop --status` to verify temperatures, requested PWM, live PWM, and RPM.
7. Test cooling under load before relying on unattended operation.

To set the interval from the command line instead of the TUI:

```bash
fantop --schedule 5
sudo fantop --install-scheduler
```

Supported intervals are 1, 2, 3, 5, 10, 15, 30, and 60 minutes.

## Usage

```text
fantop                         interactive editor
fantop --status                current temperatures/PWM/RPM
fantop --doctor                prerequisite and hardware checks
fantop --discover              active controllable channels
fantop --discover --all-channels
fantop --setup                  configure active discovered channels
fantop --dry-run                calculate without writing PWM
sudo fantop --calibrate --yes   bounded PWM/RPM calibration
sudo fantop --restore-auto      restore firmware fan control
fantop --schedule 5            save a five-minute interval
sudo fantop --install-scheduler install systemd timer/cron fallback
sudo fantop --uninstall-scheduler remove managed scheduler
fantop --log-tail 50           show rotating log entries
sudo fantop --apply            apply once
```

In the TUI, use 1–9 or Tab to select, arrows and +/- to edit, A/D to add/delete,
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
The selected PWM card uses a red border and red title; unselected cards remain
cyan, making the curve currently being edited immediately visible.
The bottom-right indicator flashes green when the exact managed systemd timer or
cron fallback is active, or red when it is missing or out of date.
PWM labels use a persistent Nano-style footer prompt reading
`Renaming / Labeling PWMN to:` with explicit Enter-confirm and Escape-cancel
controls. Temperature-source changes remain unsaved until Save is selected.

Configuration is versioned JSON at
`INSTALL_DIR/.config/fantop/config.json`. With the recommended layout,
that is `~/.local/share/fantop/.config/fantop/config.json`.
Existing settings from the former application name are migrated automatically
on first launch and retained as a backup in their old location.
Export opens a Nano-style name prompt in the bottom status area. Type an
optional profile name, then use `Enter` to confirm or `Esc` to cancel. Named files use
`INSTALL_DIR/FantopExport_NAME_YYYYMMDD_HHMMSS.json` and retain the full label
inside JSON; unnamed exports keep `INSTALL_DIR/FantopExport_YYYYMMDD_HHMMSS.json`.
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
If required temperatures cannot be read, configured channels are driven to the
fail-safe PWM (255 by default). Upward fan changes are immediate; downward
changes use configurable hysteresis and smoothing. Calibration always restores
the original PWM values and enable modes in a `finally` path.
The systemd service also has an `OnFailure` emergency unit that forces fail-safe
PWM if the normal apply process crashes before its internal handler completes.
Every normal PWM write is polled for asynchronous readback. Exact convergence
or hardware-ramp movement is recorded; delayed mismatches are logged as warnings
because some controllers ramp their readable register slowly. Controllers with
immediate readback can opt into `strict_pwm_verification` in the JSON config.
Write errors and strict-verification failures activate the emergency fail-safe.

To uninstall safely, run `./uninstall.sh`; it offers to restore firmware control
before removing the scheduler and application files.

## Development and testing

Run the complete local validation suite with:

```bash
make check
```

GitHub Actions runs unit tests on Python 3.10 and 3.12, compiles the application,
and validates every shell entry point on pushes and pull requests.
