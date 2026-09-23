<img src="/img/Fantop - BIOS-style fan curves in your terminal for Linux.png" alt="Fantop - BIOS-style fan curves in your terminal for Linux" style="max-width: 100%;">


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

Choose a stable installation directory. The installer places the interactive
copy there and installs a root-owned controller at
`/usr/local/lib/fantop/fantop.py`. The managed scheduler uses the protected
`/usr/local/bin/fantop` launcher. Installation needs sudo access.

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

The installer creates a user launcher at `~/.local/bin/fantop` and a protected
system launcher at `/usr/local/bin/fantop`, so `fantop` and `sudo fantop` work
from any directory. It also migrates legacy configurations, removes the previous
launcher name, and updates an existing managed schedule. It stores a protected
copy of the last applied configuration at `/var/lib/fantop/recovery-config.json`.

`--discover` shows active channels with tachometer feedback. To diagnose all
PWM headers, including unused or zero-RPM channels, run:

```bash
fantop --discover --all-channels
```

Discovery is read-only and does not change fan speeds.

## First-time setup

1. Run `fantop --doctor` and resolve every failed prerequisite.
2. Run `fantop --discover` and verify the detected controller and channels.
3. Run `fantop --setup` to draft a configuration from active channels. The
   saved configuration and any active schedule keep running.
4. Launch `fantop` to open the draft, label each active header, select
   temperature sources, and review every curve.
5. Save from the TUI. Saving requests sudo access, applies the curves immediately,
   and creates or updates the managed systemd timer or root cron fallback. The
   saved configuration changes only after application and scheduler setup succeed.
6. Confirm that the footer shows green `SCHEDULE ACTIVE` and run
   `fantop --status` to verify temperatures, requested PWM, live PWM, and RPM.
7. Test cooling under load before relying on unattended operation.

To set the interval from the command line instead of the TUI:

```bash
fantop --schedule 5
sudo fantop --install-scheduler
```

Supported intervals are 1, 2, 3, 5, 10, 15, 30, and 60 minutes.
The JSON `scheduler` setting accepts `auto`, `systemd`, or `cron`. `auto` uses
systemd when it is running and otherwise uses cron. Selecting an unavailable
scheduler fails with an error instead of silently selecting another one.

## Usage

| Command | Description |
|---|---|
| `fantop` | Open the interactive editor |
| `fantop --status` | Show current temperatures, requested PWM, live PWM, and RPM |
| `fantop --doctor` | Check prerequisites and available hardware support |
| `fantop --discover` | List active controllable PWM channels |
| `fantop --discover --all-channels` | List all controllable PWM channels, including inactive or zero-RPM headers |
| `fantop --setup` | Draft curves for active discovered channels |
| `fantop --dry-run` | Calculate targets without writing PWM values |
| `sudo fantop --calibrate --yes` | Run bounded PWM/RPM calibration |
| `sudo fantop --restore-auto` | Stop managed scheduling and restore firmware fan control |
| `fantop --schedule 5` | Save a five-minute scheduler interval |
| `sudo fantop --install-scheduler` | Install the systemd timer or cron fallback |
| `sudo fantop --install-cron` | Select cron and replace an existing systemd timer |
| `sudo fantop --uninstall-scheduler` | Remove the managed scheduler |
| `fantop --log-tail 50` | Show the last 50 rotating log entries |
| `sudo fantop --apply` | Apply the saved curves once |
| `sudo fantop --fail-safe` | Force configured channels to full speed using the protected recovery config |

The setup draft lives at `INSTALL_DIR/.config/fantop/setup-draft.json` and is
removed after a successful Save. Exiting the editor without saving leaves the
draft for the next launch. If the editable configuration is malformed or
missing, scheduled application sets the previously configured channels to PWM
255 and reports an error. The emergency command uses the protected recovery
copy even when the editable file cannot be read. A fan with calibration data
and zero RPM receives a startup
pulse; fantop raises it to PWM 255 if necessary and reports a failure if RPM
does not appear. Keep fan tachometer feedback connected for this check.
Hardware controlled ramps can take several seconds. The fail-safe command
checks all configured channels until they read PWM 255 or the verification
window expires, and reports any channel that does not reach full speed.

### TUI controls

#### Keyboard controls

| Key | Action |
|---|---|
| `1`–`9` or `Tab` | Select a fan / PWM channel |
| Arrow keys or `+` / `-` | Edit the selected curve point |
| `A` / `D` | Add or delete a curve point |
| `M` | Toggle between step and linear curve mode |
| `N` | Rename / label the selected PWM channel |
| `C` | Cycle scheduler intervals |
| `T` or footer action `[T Temp Source]` | Select a temperature source from currently available sensors, with live temperatures shown |
| `F` | Set every point in the selected curve to PWM `255` |
| `S` | Save, apply immediately, and update the scheduler |
| `E` / `I` | Export or import a profile |
| `?` or `F1` | Open help |
| `Q` or `Ctrl+C` | Exit without saving |

`Esc` never exits the utility. It only cancels the currently active import,
export, rename, or selection dialog.

#### Mouse controls

Mouse selection, graph editing, and footer buttons work in terminals that support
mouse reporting.

| Mouse action | Result |
|---|---|
| Left-click a fan card, table row, graph area, or footer button | Select or activate that item |
| Right-click a yellow curve-point marker on the main editing graph | Select that curve point |
| `Ctrl` + right-click anywhere on the main editing graph | Insert a new point at the clicked temperature and PWM |

#### Help

The help screen is available through `?`, `F1`, or either clickable `[? Help]`
footer label. Help remains open until the next key press.

#### Visual indicators

A bold yellow dotted vertical line marks the selected fan's current controlling
sensor temperature on both the overview graph and the main editing graph.

The selected PWM card uses a red border and red title. Unselected cards remain
cyan, making the curve currently being edited easy to identify.

The bottom-right scheduler indicator flashes:

| Color | Meaning |
|---|---|
| Green | The exact managed systemd timer or cron fallback is active |
| Red | The scheduler is missing, inactive, or out of date |

#### Rename and temperature-source dialogs

PWM labels use a persistent Nano-style footer prompt:

```text
Renaming / Labeling PWMN to:
```

Use `Enter` to confirm or `Esc` to cancel.

Temperature-source changes remain unsaved until `Save` is selected.

### Configuration, profiles, and imports

Configuration is stored as versioned JSON at:

```text
INSTALL_DIR/.config/fantop/config.json
```

With the recommended installation layout, this resolves to:

```text
~/.local/share/fantop/.config/fantop/config.json
```

Existing settings from the former application name are migrated automatically on
first launch. The original configuration is retained as a backup in its old
location.

#### Exporting profiles

Export opens a Nano-style name prompt in the bottom status area. Type an optional
profile name, then press `Enter` to confirm or `Esc` to cancel.

Named exports use this format:

```text
INSTALL_DIR/FantopExport_NAME_YYYYMMDD_HHMMSS.json
```

Unnamed exports use this format:

```text
INSTALL_DIR/FantopExport_YYYYMMDD_HHMMSS.json
```

Named profile exports retain the full label inside the JSON file.

#### Importing profiles

In the import browser, press `N` to rename the selected profile and its file.

The import rename field uses the same focused bottom-footer layout, with explicit
`Enter` confirmation and `Esc` cancellation. Other actions are hidden while the
rename prompt is active.

Invalid imports are rejected. Missing sensors or non-writable PWM controls fail
closed without partially choosing fallback temperatures.

## Safety

Discovering channels is read-only. Applying switches configured channels to
manual mode. Keep a firmware/BIOS fallback available and test curves under load.
The default profile includes HDD and board-temperature airflow floors. Review
and adapt every sensor mapping and safety threshold for the target hardware.
If required temperatures cannot be read, configured channels are driven to the
fail-safe PWM 255, and the apply command exits with an error.
Sensor reads time out after five seconds. Sensors used by active safety rules
are required even when their dedicated fan group is disabled.
If a PWM write fails, fantop attempts fail-safe writes on every configured
channel and verifies manual mode and exact PWM readback for each emergency write. It reports
any recovery failures. An unchanged PWM readback counts as
a failed write; a progressing hardware ramp is accepted unless strict PWM
verification is enabled. Upward fan changes are immediate; downward
changes use configurable hysteresis and smoothing. Calibration attempts to restore
the original PWM values and enable modes in a `finally` path, and shares the
controller lock with scheduled application.
The systemd service also has an `OnFailure` emergency unit that forces fail-safe
PWM if the normal apply process crashes before its internal handler completes.
Every normal PWM write is polled for asynchronous readback. Exact convergence
or repeated movement toward the target is recorded. Controllers with immediate
readback can opt into `strict_pwm_verification` in the JSON config, which
requires exact convergence. Persistent mismatches activate the emergency
fail-safe.
The scheduled controller code, launcher, state, and logs live in root-owned
directories. The editable configuration remains at
`INSTALL_DIR/.config/fantop/config.json`; state is stored in
`/var/lib/fantop/state.json` and logs in `/var/lib/fantop/fantop.log`.
Upgrades leave older state and log files in the previous installation directory;
new state is recorded after the next successful scheduled run.

To uninstall safely, run `./uninstall.sh`; it offers to restore firmware control
before removing the scheduler and application files.

## Development and testing

Run the complete local validation suite with:

```bash
make check
```

GitHub Actions runs unit tests on Python 3.10 and 3.12, compiles the application,
and validates every shell entry point on pushes and pull requests.
