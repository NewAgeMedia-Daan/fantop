# Changelog

All notable changes to Fan Control TUI are documented here.

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
