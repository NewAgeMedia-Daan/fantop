# Changelog

All notable changes to fantop are documented here.

## 4.0.2 - 2026-09-23

### Fixed

- Run scheduled control from a verified root-owned launcher and runtime
- Restrict configured controller paths to devices discovered by Linux hwmon
- Keep controller state and logs in root-owned directories
- Time out stalled sensor reads so normal fail-safe handling can run
- Verify manual mode and emergency PWM readback, reporting channels that did not reach the target
- Preserve unrelated root cron entries and refuse ambiguous crontab read failures
- Require sensors referenced by active safety rules
- Repoint existing managed schedules during installation upgrades

## 4.0.1 - 2026-09-23

### Fixed

- Attempt fail-safe recovery on all configured channels after PWM write failures
- Reject unresponsive PWM readback and retain observed PWM state during ramps
- Lock calibration against scheduled control and restore enable mode after PWM restore errors
- Verify configured hwmon identity and required channels before use
- Stage TUI saves until application and scheduler setup succeed
- Honor explicit systemd or cron scheduler selection and recognize `crond` status
- Clear stale live values after sensor errors and check managed systemd unit contents
- Replace installed runtime files atomically during updates

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
