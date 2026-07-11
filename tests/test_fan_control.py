import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

MODULE_PATH = Path(__file__).parents[1] / "fan_control.py"
SPEC = importlib.util.spec_from_file_location("fan_control", MODULE_PATH)
fan_control = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(fan_control)


class ConfigTests(unittest.TestCase):
    def test_v2_migrates_to_v3(self):
        config = copy.deepcopy(fan_control.DEFAULT_CONFIG)
        config["version"] = 2
        config["controller"] = "auto"
        config.pop("control")
        config.pop("scheduler")
        migrated = fan_control.validate_config(config)
        self.assertEqual(migrated["version"], 3)
        self.assertEqual(migrated["controller"]["name"], "nct6687")
        self.assertEqual(migrated["control"]["fail_safe_pwm"], 255)

    def test_invalid_control_values_rejected(self):
        config = copy.deepcopy(fan_control.DEFAULT_CONFIG)
        config["control"]["smoothing_alpha"] = 0
        with self.assertRaises(ValueError):
            fan_control.validate_config(config)

    def test_duplicate_pwm_rejected(self):
        config = copy.deepcopy(fan_control.DEFAULT_CONFIG)
        config["fans"][1]["pwm"] = config["fans"][0]["pwm"]
        with self.assertRaises(ValueError): fan_control.validate_config(config)


class CurveTests(unittest.TestCase):
    def test_step_curve(self):
        fan = {"mode": "step", "points": [[0, 80], [50, 120], [80, 255]]}
        self.assertEqual(fan_control.curve_value(fan, 49), 80)
        self.assertEqual(fan_control.curve_value(fan, 50), 120)

    def test_linear_curve(self):
        fan = {"mode": "linear", "points": [[0, 0], [100, 200]]}
        self.assertEqual(fan_control.curve_value(fan, 50), 100)

    def test_dynamic_safety_ignores_absent_named_groups(self):
        config = copy.deepcopy(fan_control.DEFAULT_CONFIG)
        config["fans"] = [config["fans"][0]]
        values, _ = fan_control.requested_pwms(config, {"cpu": 70, "hdd": 50, "board": 70})
        self.assertIn("cpu", values)


class StabilityTests(unittest.TestCase):
    def setUp(self):
        self.config = copy.deepcopy(fan_control.DEFAULT_CONFIG)
        self.config["fans"] = [self.config["fans"][0]]

    def test_ramp_up_is_immediate(self):
        state = {"temps": {"cpu": 60}, "pwms": {"cpu": 100}}
        result = fan_control.stabilize_pwms(self.config, {"cpu": 70}, {"cpu": 200}, state)
        self.assertEqual(result["cpu"], 200)

    def test_ramp_down_is_smoothed(self):
        state = {"temps": {"cpu": 80}, "pwms": {"cpu": 200}}
        result = fan_control.stabilize_pwms(self.config, {"cpu": 70}, {"cpu": 100}, state)
        self.assertGreater(result["cpu"], 100)
        self.assertLess(result["cpu"], 200)

    def test_downward_hysteresis_holds_value(self):
        state = {"temps": {"cpu": 70}, "pwms": {"cpu": 180}}
        result = fan_control.stabilize_pwms(self.config, {"cpu": 69}, {"cpu": 100}, state)
        self.assertEqual(result["cpu"], 180)

    def test_calibrated_minimum_is_enforced(self):
        self.config["fans"][0]["calibration"] = {"minimum_pwm": 120}
        result = fan_control.stabilize_pwms(self.config, {"cpu": 40}, {"cpu": 80}, {})
        self.assertEqual(result["cpu"], 120)


class FailSafeTests(unittest.TestCase):
    def test_verified_pwm_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "pwm1").write_text("0\n"); (root / "pwm1_enable").write_text("99\n")
            with mock.patch("os.access", return_value=True), mock.patch("time.sleep"):
                self.assertEqual(fan_control.write_pwm_verified(root, 1, 173), 173)
            self.assertEqual((root / "pwm1_enable").read_text().strip(), "1")

    def test_sensor_failure_writes_fail_safe_pwm(self):
        config = copy.deepcopy(fan_control.DEFAULT_CONFIG)
        config["fans"] = [config["fans"][0]]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pwm1").write_text("80\n")
            (root / "pwm1_enable").write_text("99\n")
            with mock.patch.object(fan_control, "LOCK_FILE", root / "lock"), \
                 mock.patch.object(fan_control, "STATE_FILE", root / "state.json"), \
                 mock.patch.object(fan_control, "find_hwmon", return_value=root), \
                 mock.patch.object(fan_control, "read_sensors", side_effect=RuntimeError("sensor offline")), \
                 mock.patch.object(fan_control, "get_logger", return_value=mock.Mock()), \
                 mock.patch("os.access", return_value=True):
                fan_control.apply_config(config, quiet=True)
            self.assertEqual((root / "pwm1").read_text().strip(), "255")
            self.assertEqual((root / "pwm1_enable").read_text().strip(), "1")


if __name__ == "__main__":
    unittest.main()
