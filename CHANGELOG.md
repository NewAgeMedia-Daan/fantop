# Changelog

All notable changes to fantop are documented here.

## 4.0.0 - 2026-07-11

### Changed

- Renamed the utility, executable, module, runtime paths, systemd units, profiles,
  installer variables, documentation, and repository to `fantop`
- Added automatic migration from legacy configuration and profile locations
- Added automatic cleanup of legacy cron entries, systemd units, and launchers
- Highlighted the selected PWM card border and title in red
- Installed `fantop` into the user PATH for launching from any directory

## 3.0.0 - 2026-07-11

### Added

- Fail-safe PWM behavior for sensor and calculation failures
- Downward hysteresis and smoothing with immediate heat-response ramp-up
- Persistent controller state and rotating operational logs
- Dynamic hwmon controller selection and active-channel setup
- Bounded PWM/RPM calibration with automatic restoration
- Firmware/automatic mode restore and scheduler uninstall commands
- Systemd timer scheduling with automatic cron fallback
- Confirmation prompts for destructive curve actions
- Portable installer, uninstaller, MIT license, and automated unit tests

## 2.0.0 - 2026-07-11

### Added

- Color curses interface with keyboard and mouse control
- Simultaneous fan-curve overview and focused curve editor
- Live temperature, PWM, RPM, and managed-cron status
- Step and linear curves, point editing, and maximum-curve action
- Active PWM discovery and prerequisite diagnostics
- Configurable cron intervals and immediate Save-and-Apply workflow
- Named JSON profile import and export
- Channel labels, safety airflow floors, and fail-closed sensor handling

## 1.0.0

- Initial NCT6687 Bash-based fan controller
