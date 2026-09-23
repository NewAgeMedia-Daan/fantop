import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

MODULE_PATH = Path(__file__).parents[1] / "fantop.py"
SPEC = importlib.util.spec_from_file_location("fantop", MODULE_PATH)
fantop = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(fantop)


class ConfigTests(unittest.TestCase):
    def test_configured_controller_outside_hwmon_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory)
            (fake / "name").write_text("nct6687\n")
            (fake / "pwm1").write_text("80\n")
            (fake / "pwm1_enable").write_text("1\n")
            config = copy.deepcopy(fantop.DEFAULT_CONFIG)
            config["fans"] = config["fans"][:1]
            config["controller"]["path"] = str(fake)
            original_glob = Path.glob
            with mock.patch.object(Path, "glob", autospec=True,
                                   side_effect=lambda path, pattern: [] if str(path) == "/sys/class/hwmon" else original_glob(path, pattern)):
                with self.assertRaisesRegex(RuntimeError, "Could not find"):
                    fantop.find_hwmon(config)

    def test_hwmon_path_requires_identity_and_channels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad, good = root / "bad", root / "good"
            bad.mkdir(); good.mkdir()
            (bad / "name").write_text("wrong\n")
            (bad / "pwm1").write_text("80\n")
            (bad / "pwm1_enable").write_text("1\n")
            (good / "name").write_text("expected\n")
            (good / "pwm1").write_text("80\n")
            (good / "pwm1_enable").write_text("1\n")
            config = copy.deepcopy(fantop.DEFAULT_CONFIG)
            config["fans"] = config["fans"][:1]
            config["controller"] = {"name": "expected", "path": str(bad)}
            original_glob = Path.glob
            with mock.patch.object(Path, "glob", autospec=True,
                                   side_effect=lambda path, pattern: [good] if str(path) == "/sys/class/hwmon" else original_glob(path, pattern)):
                self.assertEqual(fantop.find_hwmon(config), good)

    def test_legacy_config_location_migrates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); old = root / "old"; old.mkdir(); new = root / "new" / "config.json"
            (old / "config.json").write_text(__import__("json").dumps(fantop.DEFAULT_CONFIG))
            with mock.patch.object(fantop, "CONFIG_FILE", new), \
                 mock.patch.object(fantop, "LEGACY_CONFIG_DIRS", (old,)):
                loaded = fantop.load_config()
            self.assertEqual(loaded["version"], 3)
            self.assertTrue(new.exists())

    def test_v2_migrates_to_v3(self):
        config = copy.deepcopy(fantop.DEFAULT_CONFIG)
        config["version"] = 2
        config["controller"] = "auto"
        config.pop("control")
        config.pop("scheduler")
        migrated = fantop.validate_config(config)
        self.assertEqual(migrated["version"], 3)
        self.assertEqual(migrated["controller"]["name"], "nct6687")
        self.assertEqual(migrated["control"]["fail_safe_pwm"], 255)

    def test_invalid_control_values_rejected(self):
        config = copy.deepcopy(fantop.DEFAULT_CONFIG)
        config["control"]["smoothing_alpha"] = 0
        with self.assertRaises(ValueError):
            fantop.validate_config(config)

    def test_logging_and_boolean_control_values_are_validated(self):
        for key, value in (("log_max_bytes", "bad"), ("log_max_bytes", 0),
                           ("log_backups", "bad"), ("log_backups", 0),
                           ("auto_mode", 1), ("strict_pwm_verification", "false"),
                           ("respect_calibration_min", "false"),
                           ("hysteresis_c", float("nan"))):
            config = copy.deepcopy(fantop.DEFAULT_CONFIG)
            config["control"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                fantop.validate_config(config)

    def test_schedule_and_safety_shapes_are_validated(self):
        for key, value in (("schedule_minutes", 1.0), ("schedule_minutes", True),
                           ("safety", {"hdd": [{"temp": 42, "middle": "200"}]}),
                           ("safety", {"board": [{"temp": float("nan"), "middle": 200}]})):
            config = copy.deepcopy(fantop.DEFAULT_CONFIG)
            config[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                fantop.validate_config(config)

    def test_controller_path_rejects_embedded_nul(self):
        config = copy.deepcopy(fantop.DEFAULT_CONFIG)
        config["controller"]["path"] = "/sys/class/hwmon/\x00"
        with self.assertRaises(ValueError):
            fantop.validate_config(config)

    def test_fail_safe_pwm_must_be_full_speed(self):
        for value in (0, 128, 254):
            config = copy.deepcopy(fantop.DEFAULT_CONFIG)
            config["control"]["fail_safe_pwm"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "must be 255"):
                fantop.validate_config(config)

    def test_recovery_config_is_saved_with_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            recovery = Path(directory) / "recovery.json"
            with mock.patch.object(fantop, "RECOVERY_CONFIG_FILE", recovery), \
                 mock.patch.object(fantop, "SCRIPT", fantop.SYSTEM_SCRIPT), \
                 mock.patch.object(fantop, "verify_root_runtime"), \
                 mock.patch("os.geteuid", return_value=0):
                fantop.save_recovery_config(copy.deepcopy(fantop.DEFAULT_CONFIG))
            self.assertEqual(recovery.stat().st_mode & 0o777, 0o600)
            self.assertEqual(__import__("json").loads(recovery.read_text())["control"]["fail_safe_pwm"], 255)

    def test_duplicate_pwm_rejected(self):
        config = copy.deepcopy(fantop.DEFAULT_CONFIG)
        config["fans"][1]["pwm"] = config["fans"][0]["pwm"]
        with self.assertRaises(ValueError): fantop.validate_config(config)


class CurveTests(unittest.TestCase):
    def test_step_curve(self):
        fan = {"mode": "step", "points": [[0, 80], [50, 120], [80, 255]]}
        self.assertEqual(fantop.curve_value(fan, 49), 80)
        self.assertEqual(fantop.curve_value(fan, 50), 120)

    def test_linear_curve(self):
        fan = {"mode": "linear", "points": [[0, 0], [100, 200]]}
        self.assertEqual(fantop.curve_value(fan, 50), 100)

    def test_dynamic_safety_ignores_absent_named_groups(self):
        config = copy.deepcopy(fantop.DEFAULT_CONFIG)
        config["fans"] = [config["fans"][0]]
        values, _ = fantop.requested_pwms(config, {"cpu": 70, "hdd": 50, "board": 70})
        self.assertIn("cpu", values)

    def test_missing_sensor_used_by_safety_rule_fails_closed(self):
        config = copy.deepcopy(fantop.DEFAULT_CONFIG)
        config["fans"] = [fan for fan in config["fans"] if fan["id"] != "hdd"]
        with self.assertRaisesRegex(RuntimeError, "hdd"):
            fantop.requested_pwms(config, {"cpu": 70, "board": 60, "case": 70})


class StabilityTests(unittest.TestCase):
    def setUp(self):
        self.config = copy.deepcopy(fantop.DEFAULT_CONFIG)
        self.config["fans"] = [self.config["fans"][0]]

    def test_ramp_up_is_immediate(self):
        state = {"temps": {"cpu": 60}, "pwms": {"cpu": 100}}
        result = fantop.stabilize_pwms(self.config, {"cpu": 70}, {"cpu": 200}, state)
        self.assertEqual(result["cpu"], 200)

    def test_ramp_down_is_smoothed(self):
        state = {"temps": {"cpu": 80}, "pwms": {"cpu": 200}}
        result = fantop.stabilize_pwms(self.config, {"cpu": 70}, {"cpu": 100}, state)
        self.assertGreater(result["cpu"], 100)
        self.assertLess(result["cpu"], 200)

    def test_downward_hysteresis_holds_value(self):
        state = {"temps": {"cpu": 70}, "pwms": {"cpu": 180}}
        result = fantop.stabilize_pwms(self.config, {"cpu": 69}, {"cpu": 100}, state)
        self.assertEqual(result["cpu"], 180)

    def test_calibrated_minimum_is_enforced(self):
        self.config["fans"][0]["calibration"] = {"minimum_pwm": 120}
        result = fantop.stabilize_pwms(self.config, {"cpu": 40}, {"cpu": 80}, {})
        self.assertEqual(result["cpu"], 120)


class FailSafeTests(unittest.TestCase):
    def test_apply_reports_busy_controller_as_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            live = Path(directory) / "config.json"
            live.write_text(__import__("json").dumps(fantop.DEFAULT_CONFIG))
            with mock.patch.object(fantop, "CONFIG_FILE", live), \
                 mock.patch.object(fantop, "apply_config", return_value=False), \
                 mock.patch("sys.argv", ["fantop", "--apply"]):
                self.assertEqual(fantop.main(), 1)

    def test_malformed_config_forces_recovery_on_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            bad_config = Path(directory) / "config.json"
            bad_config.write_text("{broken")
            with mock.patch.object(fantop, "CONFIG_FILE", bad_config), \
                 mock.patch.object(fantop, "load_recovery_config", return_value=copy.deepcopy(fantop.DEFAULT_CONFIG)), \
                 mock.patch.object(fantop, "force_fail_safe") as recover, \
                 mock.patch("sys.argv", ["fantop", "--apply"]):
                self.assertEqual(fantop.main(), 1)
            recover.assert_called_once()

    def test_fail_safe_uses_recovery_when_live_config_is_malformed(self):
        with mock.patch.object(fantop, "load_recovery_config", return_value=copy.deepcopy(fantop.DEFAULT_CONFIG)), \
             mock.patch.object(fantop, "load_config", side_effect=AssertionError("live config read")), \
             mock.patch.object(fantop, "force_fail_safe") as recover, \
             mock.patch("sys.argv", ["fantop", "--fail-safe"]):
            self.assertEqual(fantop.main(), 0)
        recover.assert_called_once()

    def test_stopped_calibrated_fan_gets_startup_then_full_speed(self):
        fan = {"pwm": 1, "fan_input": 1, "calibration": {"startup_pwm": 40}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tach = root / "fan1_input"
            tach.write_text("0\n")
            def write(_, __, value, strict=False):
                if value == 255: tach.write_text("800\n")
                return value
            with mock.patch.object(fantop, "write_pwm_verified", side_effect=write) as pwm, \
                 mock.patch("time.sleep"):
                fantop.ensure_fan_started(root, fan, 80)
            self.assertEqual([call.args[2] for call in pwm.call_args_list], [80, 255])

    def test_stopped_fan_without_rpm_is_rejected(self):
        fan = {"pwm": 1, "fan_input": 1, "calibration": {"startup_pwm": 40}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "fan1_input").write_text("0\n")
            with mock.patch.object(fantop, "write_pwm_verified", return_value=255), \
                 mock.patch("time.sleep"), \
                 self.assertRaisesRegex(RuntimeError, "did not start"):
                fantop.ensure_fan_started(root, fan, 80)

    def test_sensor_command_has_timeout(self):
        import subprocess
        with mock.patch.object(fantop.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("sensors", 5)) as run:
            with self.assertRaises(subprocess.TimeoutExpired):
                fantop.read_sensors()
        self.assertEqual(run.call_args.kwargs["timeout"], fantop.SENSOR_TIMEOUT_SECONDS)

    def test_verified_pwm_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "pwm1").write_text("0\n"); (root / "pwm1_enable").write_text("99\n")
            with mock.patch("os.access", return_value=True), mock.patch("time.sleep"):
                self.assertEqual(fantop.write_pwm_verified(root, 1, 173), 173)
            self.assertEqual((root / "pwm1_enable").read_text().strip(), "1")

    def test_sensor_failure_writes_fail_safe_pwm(self):
        config = copy.deepcopy(fantop.DEFAULT_CONFIG)
        config["fans"] = [config["fans"][0]]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pwm1").write_text("80\n")
            (root / "pwm1_enable").write_text("99\n")
            with mock.patch.object(fantop, "LOCK_FILE", root / "lock"), \
                 mock.patch.object(fantop, "STATE_FILE", root / "state.json"), \
                 mock.patch.object(fantop, "find_hwmon", return_value=root), \
                 mock.patch.object(fantop, "read_sensors", side_effect=RuntimeError("sensor offline")), \
                 mock.patch.object(fantop, "get_logger", return_value=mock.Mock()), \
                 mock.patch("os.access", return_value=True):
                with self.assertRaisesRegex(RuntimeError, "Sensor failure"):
                    fantop.apply_config(config, quiet=True)
            self.assertEqual((root / "pwm1").read_text().strip(), "255")
            self.assertEqual((root / "pwm1_enable").read_text().strip(), "1")

    def test_sensor_failure_requires_exact_fail_safe_readback(self):
        config = copy.deepcopy(fantop.DEFAULT_CONFIG)
        config["fans"] = config["fans"][:1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pwm1").write_text("100\n")
            with mock.patch.object(fantop, "LOCK_FILE", root / "lock"), \
                 mock.patch.object(fantop, "find_hwmon", return_value=root), \
                 mock.patch.object(fantop, "read_sensors", side_effect=RuntimeError("sensor offline")), \
                 mock.patch.object(fantop, "get_logger", return_value=mock.Mock()), \
                 mock.patch.object(fantop, "set_pwm_target", return_value=(root / "pwm1", 100)) as write, \
                 mock.patch("time.sleep"), \
                 self.assertRaisesRegex(RuntimeError, "fail-safe errors"):
                fantop.apply_config(config, quiet=True)
            write.assert_called_once_with(root, 1, 255)

    def test_fail_safe_waits_for_all_hardware_ramps(self):
        config = copy.deepcopy(fantop.DEFAULT_CONFIG)
        config["fans"] = config["fans"][:2]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for number in (1, 5):
                (root / f"pwm{number}").write_text("100\n")
            def ramp(_):
                for number in (1, 5):
                    path = root / f"pwm{number}"
                    path.write_text(f"{min(255, int(path.read_text()) + 5)}\n")
            with mock.patch.object(fantop, "set_pwm_target",
                                   side_effect=lambda _, number, __: (root / f"pwm{number}", 100)) as write, \
                 mock.patch("time.sleep", side_effect=ramp):
                self.assertEqual(fantop.write_fail_safe(root, config), [])
            self.assertEqual(write.call_count, 2)
            self.assertEqual((root / "pwm1").read_text().strip(), "255")
            self.assertEqual((root / "pwm5").read_text().strip(), "255")

    def test_failed_channel_recovers_all_channels(self):
        config = copy.deepcopy(fantop.DEFAULT_CONFIG)
        config["fans"] = config["fans"][:2]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for number in (1, 5):
                (root / f"pwm{number}").write_text("80\n")
                (root / f"pwm{number}_enable").write_text("99\n")
            def write(_, number, value, strict=False):
                if number == 1 and value != 255: raise OSError("controller rejected write")
                (root / f"pwm{number}").write_text(f"{value}\n")
                return value
            with mock.patch.object(fantop, "LOCK_FILE", root / "lock"), \
                 mock.patch.object(fantop, "find_hwmon", return_value=root), \
                 mock.patch.object(fantop, "read_sensors", return_value={"cpu": 50, "hdd": 35, "board": 40}), \
                 mock.patch.object(fantop, "load_state", return_value={}), \
                 mock.patch.object(fantop, "get_logger", return_value=mock.Mock()), \
                 mock.patch.object(fantop, "write_pwm_verified", side_effect=write):
                with self.assertRaisesRegex(RuntimeError, "PWM write failed"):
                    fantop.apply_config(config, quiet=True)
            self.assertEqual((root / "pwm1").read_text().strip(), "255")
            self.assertEqual((root / "pwm5").read_text().strip(), "255")

    def test_ramping_readback_is_saved_as_observed_state(self):
        config = copy.deepcopy(fantop.DEFAULT_CONFIG)
        config["fans"] = config["fans"][:1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(fantop, "LOCK_FILE", root / "lock"), \
                 mock.patch.object(fantop, "find_hwmon", return_value=root), \
                 mock.patch.object(fantop, "read_sensors", return_value={"cpu": 50}), \
                 mock.patch.object(fantop, "load_state", return_value={}), \
                 mock.patch.object(fantop, "get_logger", return_value=mock.Mock()), \
                 mock.patch.object(fantop, "write_pwm_verified", return_value=88), \
                 mock.patch.object(fantop, "save_state") as state:
                self.assertTrue(fantop.apply_config(config, quiet=True))
            state.assert_called_once_with({"cpu": 50}, {"cpu": 88})

    def test_unresponsive_pwm_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pwm1").write_text("80\n")
            (root / "pwm1_enable").write_text("99\n")
            original_read = Path.read_text
            with mock.patch("os.access", return_value=True), mock.patch("time.sleep"), \
                 mock.patch.object(Path, "read_text", autospec=True,
                                   side_effect=lambda path, *args, **kwargs: "80\n" if path.name == "pwm1" else original_read(path, *args, **kwargs)):
                with self.assertRaisesRegex(RuntimeError, "verification failed"):
                    fantop.write_pwm_verified(root, 1, 173)

    def test_stalled_partial_ramp_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pwm1").write_text("80\n")
            (root / "pwm1_enable").write_text("1\n")
            readings = iter([80, 90, 100] + [100] * 60)
            original_read = Path.read_text
            def read(path, *args, **kwargs):
                return f"{next(readings)}\n" if path.name == "pwm1" else original_read(path, *args, **kwargs)
            with mock.patch("os.access", return_value=True), mock.patch("time.sleep"), \
                 mock.patch.object(Path, "read_text", autospec=True, side_effect=read), \
                 self.assertRaisesRegex(RuntimeError, "verification failed"):
                fantop.write_pwm_verified(root, 1, 200)

    def test_manual_mode_must_be_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pwm1").write_text("255\n")
            (root / "pwm1_enable").write_text("99\n")
            original_read = Path.read_text
            with mock.patch("os.access", return_value=True), \
                 mock.patch.object(Path, "read_text", autospec=True,
                                   side_effect=lambda path, *args, **kwargs: "99\n" if path.name == "pwm1_enable" else original_read(path, *args, **kwargs)):
                with self.assertRaisesRegex(RuntimeError, "manual mode was not accepted"):
                    fantop.write_pwm_verified(root, 1, 255, strict=True)

    def test_unresponsive_fail_safe_is_reported(self):
        config = copy.deepcopy(fantop.DEFAULT_CONFIG)
        config["fans"] = config["fans"][:1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pwm1").write_text("80\n")
            (root / "pwm1_enable").write_text("99\n")
            with mock.patch.object(fantop, "set_pwm_target", side_effect=RuntimeError("readback stuck")):
                self.assertIn("readback stuck", fantop.write_fail_safe(root, config)[0])


class SchedulerTests(unittest.TestCase):
    def test_scheduler_removal_reports_failed_timer_stop(self):
        import subprocess
        with mock.patch.object(fantop.shutil, "which", return_value="/usr/bin/systemctl"), \
             mock.patch.object(Path, "exists", return_value=True), \
             mock.patch.object(Path, "unlink") as unlink, \
             mock.patch.object(fantop.subprocess, "run",
                               side_effect=subprocess.CalledProcessError(1, "systemctl")):
            with self.assertRaises(subprocess.CalledProcessError):
                fantop.remove_systemd()
        unlink.assert_not_called()

    def test_restore_auto_disables_schedule_and_verifies_modes(self):
        config = copy.deepcopy(fantop.DEFAULT_CONFIG)
        config["fans"] = config["fans"][:1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mode = root / "pwm1_enable"
            mode.write_text("1\n")
            with mock.patch.object(fantop, "LOCK_FILE", root / "lock"), \
                 mock.patch.object(fantop, "find_hwmon", return_value=root), \
                 mock.patch.object(fantop, "uninstall_scheduler") as uninstall, \
                 mock.patch("os.geteuid", return_value=0):
                fantop.restore_auto(config)
            uninstall.assert_called_once()
            self.assertEqual(mode.read_text().strip(), "99")

    def test_restore_auto_reverts_to_full_speed_if_mode_is_rejected(self):
        config = copy.deepcopy(fantop.DEFAULT_CONFIG)
        config["fans"] = config["fans"][:1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mode = root / "pwm1_enable"
            mode.write_text("1\n")
            original_read = Path.read_text
            with mock.patch.object(fantop, "LOCK_FILE", root / "lock"), \
                 mock.patch.object(fantop, "find_hwmon", return_value=root), \
                 mock.patch.object(fantop, "uninstall_scheduler"), \
                 mock.patch.object(fantop, "write_fail_safe", return_value=[]) as emergency, \
                 mock.patch.object(Path, "read_text", autospec=True,
                                   side_effect=lambda path, *a, **kw: "1\n" if path == mode else original_read(path, *a, **kw)), \
                 mock.patch("os.geteuid", return_value=0), \
                 self.assertRaisesRegex(RuntimeError, "mode was not accepted"):
                fantop.restore_auto(config)
            emergency.assert_called_once_with(root, config)

    def test_restore_auto_uses_fail_safe_if_scheduler_cannot_stop(self):
        config = copy.deepcopy(fantop.DEFAULT_CONFIG)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(fantop, "LOCK_FILE", root / "lock"), \
                 mock.patch.object(fantop, "find_hwmon", return_value=root), \
                 mock.patch.object(fantop, "uninstall_scheduler", side_effect=RuntimeError("stop failed")), \
                 mock.patch.object(fantop, "write_fail_safe", return_value=[]) as emergency, \
                 mock.patch("os.geteuid", return_value=0), \
                 self.assertRaisesRegex(RuntimeError, "Could not stop scheduler"):
                fantop.restore_auto(config)
            emergency.assert_called_once_with(root, config)

    def test_recovery_commands_work_with_malformed_live_config(self):
        with mock.patch.object(fantop, "load_config", side_effect=ValueError("malformed")), \
             mock.patch.object(fantop, "load_recovery_config", return_value=copy.deepcopy(fantop.DEFAULT_CONFIG)), \
             mock.patch.object(fantop, "restore_auto") as restore, \
             mock.patch("sys.argv", ["fantop", "--restore-auto"]):
            self.assertEqual(fantop.main(), 0)
        restore.assert_called_once()
        with mock.patch.object(fantop, "load_config", side_effect=AssertionError("config loaded")), \
             mock.patch.object(fantop, "uninstall_scheduler") as uninstall, \
             mock.patch("sys.argv", ["fantop", "--uninstall-scheduler"]):
            self.assertEqual(fantop.main(), 0)
        uninstall.assert_called_once()

    def test_log_tail_rejects_nonpositive_counts_without_opening_editor(self):
        with mock.patch.object(fantop, "load_config", side_effect=AssertionError("config loaded")), \
             mock.patch.object(fantop, "run_tui") as editor, \
             mock.patch("sys.argv", ["fantop", "--log-tail", "0"]):
            self.assertEqual(fantop.main(), 1)
        editor.assert_not_called()

    def test_setup_stages_draft_without_replacing_scheduled_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            live, draft = root / "config.json", root / "setup-draft.json"
            old = copy.deepcopy(fantop.DEFAULT_CONFIG)
            live.write_text(__import__("json").dumps(old))
            discovered = [{"name": "nct6687", "channels": [{"pwm": 1}, {"pwm": 4}]}]
            with mock.patch.object(fantop, "CONFIG_FILE", live), \
                 mock.patch.object(fantop, "SETUP_DRAFT_FILE", draft), \
                 mock.patch.object(fantop, "discover_controllers", return_value=discovered):
                fantop.setup_from_discovery()
            self.assertEqual(__import__("json").loads(live.read_text()), old)
            self.assertEqual([fan["id"] for fan in __import__("json").loads(draft.read_text())["fans"]],
                             ["pwm1", "pwm4"])

    def test_setup_can_stage_a_draft_with_malformed_live_config(self):
        with mock.patch.object(fantop, "load_config", side_effect=AssertionError("config loaded")), \
             mock.patch.object(fantop, "setup_from_discovery") as setup, \
             mock.patch("sys.argv", ["fantop", "--setup"]):
            self.assertEqual(fantop.main(), 0)
        setup.assert_called_once()

    def test_editor_loads_setup_draft_when_live_config_is_malformed(self):
        with tempfile.TemporaryDirectory() as directory:
            draft = Path(directory) / "setup-draft.json"
            draft.write_text(__import__("json").dumps(fantop.DEFAULT_CONFIG))
            with mock.patch.object(fantop, "SETUP_DRAFT_FILE", draft), \
                 mock.patch.object(fantop, "load_config", side_effect=ValueError("malformed")), \
                 mock.patch.object(fantop, "run_tui") as editor, \
                 mock.patch("sys.argv", ["fantop"]):
                self.assertEqual(fantop.main(), 0)
            editor.assert_called_once_with(mock.ANY, {})

    def test_successful_editor_save_removes_setup_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            draft = root / "setup-draft.json"
            draft.write_text("draft")
            editor = fantop.FantopTUI(mock.Mock(), copy.deepcopy(fantop.DEFAULT_CONFIG), {})
            with mock.patch.object(fantop, "CONFIG_FILE", root / "config.json"), \
                 mock.patch.object(fantop, "SETUP_DRAFT_FILE", draft), \
                 mock.patch.object(editor, "terminal_command", return_value=mock.Mock(returncode=0)), \
                 mock.patch.object(editor, "refresh_live"):
                editor.save_apply()
            self.assertFalse(draft.exists())
            self.assertFalse(editor.status_error)

    def test_direct_cron_install_selects_cron_scheduler(self):
        with tempfile.TemporaryDirectory() as directory:
            live = Path(directory) / "config.json"
            live.write_text(__import__("json").dumps(fantop.DEFAULT_CONFIG))
            with mock.patch.object(fantop, "CONFIG_FILE", live), \
                 mock.patch.object(fantop, "save_recovery_config"), \
                 mock.patch.object(fantop, "install_scheduler") as scheduler, \
                 mock.patch("sys.argv", ["fantop", "--install-cron"]):
                self.assertEqual(fantop.main(), 0)
            self.assertEqual(scheduler.call_args.args[0]["scheduler"], "cron")
            self.assertEqual(__import__("json").loads(live.read_text())["scheduler"], "cron")

    def test_direct_scheduler_install_saves_recovery_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text(__import__("json").dumps(fantop.DEFAULT_CONFIG))
            with mock.patch.object(fantop, "CONFIG_FILE", config_path), \
                 mock.patch.object(fantop, "save_recovery_config") as recovery, \
                 mock.patch.object(fantop, "install_scheduler") as scheduler, \
                 mock.patch("sys.argv", ["fantop", "--install-scheduler"]):
                self.assertEqual(fantop.main(), 0)
            recovery.assert_called_once()
            scheduler.assert_called_once()

    def test_systemd_install_completes_after_enabling_timer(self):
        config = copy.deepcopy(fantop.DEFAULT_CONFIG)
        with mock.patch("os.geteuid", return_value=0), \
             mock.patch.object(fantop, "verify_root_runtime"), \
             mock.patch.object(Path, "write_text"), \
             mock.patch.object(fantop, "remove_legacy_systemd"), \
             mock.patch.object(fantop, "remove_cron"), \
             mock.patch.object(fantop.subprocess, "run") as run:
            fantop.install_systemd(config)
        self.assertIn(mock.call(["systemctl", "enable", "--now", "fantop.timer"], check=True),
                      run.call_args_list)

    def test_crontab_read_error_never_replaces_jobs(self):
        import subprocess
        failed = subprocess.CompletedProcess([], 1, "", "permission denied")
        with mock.patch.object(fantop.subprocess, "run", return_value=failed) as run:
            with self.assertRaisesRegex(RuntimeError, "permission denied"):
                fantop.root_crontab_lines()
        self.assertEqual(run.call_count, 1)

    def test_cron_cleanup_preserves_unmarked_jobs(self):
        lines = ["# keep", "* * * * * /opt/check_fantop.py", fantop.CRON_MARKER,
                 "* * * * * /usr/local/bin/fantop --apply", "0 * * * * /opt/backup"]
        self.assertEqual(fantop.without_managed_cron(lines),
                         ["# keep", "* * * * * /opt/check_fantop.py", "0 * * * * /opt/backup"])

    def test_root_runtime_rejects_writable_paths(self):
        import stat
        from types import SimpleNamespace
        def details(path):
            is_file = path in (fantop.SYSTEM_SCRIPT, fantop.SYSTEM_LAUNCHER)
            mode = (stat.S_IFREG if is_file else stat.S_IFDIR) | (0o777 if path == fantop.SYSTEM_SCRIPT else 0o755)
            return SimpleNamespace(st_mode=mode, st_uid=0)
        with mock.patch.object(Path, "lstat", autospec=True, side_effect=details):
            with self.assertRaisesRegex(RuntimeError, "not protected"):
                fantop.verify_root_runtime()

    def test_crond_counts_as_active(self):
        config = copy.deepcopy(fantop.DEFAULT_CONFIG)
        config["scheduler"] = "cron"
        root_cron = f"{fantop.CRON_MARKER}\n{fantop.cron_line(config)}\n"
        import subprocess
        responses = [subprocess.CompletedProcess([], 3, ""),
                     subprocess.CompletedProcess([], 0, "active\n"),
                     subprocess.CompletedProcess([], 0, root_cron)]
        original_exists = Path.exists
        with mock.patch.object(Path, "exists", autospec=True,
                               side_effect=lambda path: True if str(path) == "/run/systemd/system" else original_exists(path)), \
             mock.patch.object(fantop.shutil, "which", return_value="/usr/bin/mock"), \
             mock.patch.object(fantop.subprocess, "run", side_effect=responses):
            self.assertTrue(fantop.scheduler_active(config))

    def test_explicit_cron_is_honored(self):
        config = copy.deepcopy(fantop.DEFAULT_CONFIG)
        config["scheduler"] = "cron"
        with mock.patch.object(fantop, "install_cron") as cron, \
             mock.patch.object(fantop, "install_systemd") as systemd, \
             mock.patch.object(fantop, "remove_systemd") as remove, \
             mock.patch.object(fantop, "verify_root_runtime"):
            fantop.install_scheduler(config)
        cron.assert_called_once_with(config)
        systemd.assert_not_called()
        remove.assert_called_once()

    def test_calibration_refuses_active_controller(self):
        config = copy.deepcopy(fantop.DEFAULT_CONFIG)
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "lock"
            import fcntl
            import os
            fd = os.open(lock, os.O_CREAT | os.O_RDWR)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with mock.patch.object(fantop, "LOCK_FILE", lock), \
                     mock.patch("os.geteuid", return_value=0), \
                     mock.patch.object(fantop, "_calibrate_locked") as calibrate:
                    with self.assertRaisesRegex(RuntimeError, "already running"):
                        fantop.calibrate(config, confirmed=True)
                calibrate.assert_not_called()
            finally:
                os.close(fd)

    def test_activation_does_not_save_when_apply_is_busy(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pending = root / "pending.json"
            live = root / "config.json"
            pending.write_text(json.dumps(fantop.DEFAULT_CONFIG))
            with mock.patch.object(fantop, "CONFIG_FILE", live), \
                 mock.patch.object(fantop, "SCRIPT", fantop.SYSTEM_SCRIPT), \
                 mock.patch("os.geteuid", return_value=0), \
                 mock.patch.object(fantop, "verify_root_runtime"), \
                 mock.patch.object(fantop, "apply_config", return_value=False), \
                 mock.patch.object(fantop, "install_scheduler") as scheduler:
                with self.assertRaisesRegex(RuntimeError, "not activated"):
                    fantop.activate_config(pending)
            self.assertFalse(live.exists())
            scheduler.assert_not_called()

    def test_activation_does_not_save_when_scheduler_fails(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pending = root / "pending.json"
            live = root / "config.json"
            pending.write_text(json.dumps(fantop.DEFAULT_CONFIG))
            with mock.patch.object(fantop, "CONFIG_FILE", live), \
                 mock.patch.object(fantop, "SCRIPT", fantop.SYSTEM_SCRIPT), \
                 mock.patch("os.geteuid", return_value=0), \
                 mock.patch.object(fantop, "verify_root_runtime"), \
                 mock.patch.object(fantop, "apply_config", return_value=True), \
                 mock.patch.object(fantop, "install_scheduler", side_effect=RuntimeError("scheduler failed")):
                with self.assertRaisesRegex(RuntimeError, "scheduler failed"):
                    fantop.activate_config(pending)
            self.assertFalse(live.exists())

    def test_live_data_clears_after_error(self):
        tui = fantop.FantopTUI(mock.Mock(), copy.deepcopy(fantop.DEFAULT_CONFIG))
        tui.temps, tui.pwms, tui.rpms = {"cpu": 60}, {"cpu": 100}, {"cpu": 1200}
        with mock.patch.object(fantop, "read_live", side_effect=RuntimeError("sensor offline")):
            tui.refresh_live(force=True)
        self.assertEqual((tui.temps, tui.pwms, tui.rpms), ({}, {}, {}))
        self.assertTrue(tui.status_error)


if __name__ == "__main__":
    unittest.main()
