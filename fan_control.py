#!/usr/bin/env python3
"""NAM server fan-control engine and terminal curve editor."""

from __future__ import annotations

import argparse
import copy
import curses
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import shutil
from typing import Any

SCRIPT = Path(__file__).resolve()
USER_HOME = SCRIPT.parent
CONFIG_FILE = USER_HOME / ".config" / "nam-fan-control" / "config.json"
LOCK_FILE = Path("/run/nam-fan-control.lock")
CRON_MARKER = "# fan-control-tui (managed; do not edit)"
APP_VERSION = "2.0.0"

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 2,
    "schedule_minutes": 1,
    "controller": "auto",
    "fans": [
        {"id": "cpu", "name": "CPU", "pwm": 1, "fan_input": 1,
         "sensor": "cpu", "mode": "step",
         "points": [[0, 80], [48, 90], [55, 110], [62, 135], [68, 175], [75, 215], [85, 255]]},
        {"id": "hdd", "name": "HDD / Input", "pwm": 5, "fan_input": 5,
         "sensor": "hdd", "mode": "step",
         "points": [[0, 90], [35, 100], [38, 135], [40, 165], [42, 200], [46, 230], [50, 255]]},
        {"id": "middle", "name": "Middle chassis", "pwm": 4, "fan_input": 4,
         "sensor": "board", "mode": "step",
         "points": [[0, 90], [54, 105], [57, 145], [60, 180], [65, 220], [70, 255]]},
        {"id": "exhaust", "name": "Rear exhaust", "pwm": 3, "fan_input": 3,
         "sensor": "case", "mode": "step",
         "points": [[0, 85], [54, 100], [58, 130], [62, 170], [68, 210], [75, 255]]},
    ],
    "safety": {
        "hdd": [{"temp": 42, "middle": 185, "exhaust": 155},
                {"temp": 45, "middle": 210, "exhaust": 180}],
        "board": [{"temp": 60, "middle": 190, "exhaust": 165},
                  {"temp": 65, "middle": 225, "exhaust": 205}],
    },
}


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def profile_slug(label: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", label.strip()).strip("-._")
    return slug[:48] or "Profile"


def validate_config(data: Any) -> dict[str, Any]:
    if isinstance(data, dict) and data.get("version") == 1:
        data["version"] = 2
        data.setdefault("schedule_minutes", 1)
        data.setdefault("controller", "auto")
        for fan in data.get("fans", []): fan.setdefault("enabled", True)
    if not isinstance(data, dict) or data.get("version") != 2:
        raise ValueError("Unsupported or missing config version")
    fans = data.get("fans")
    if not isinstance(fans, list) or not fans:
        raise ValueError("Config must contain at least one fan group")
    if len({fan.get("id") for fan in fans}) != len(fans):
        raise ValueError("Fan IDs must be unique")
    if data.get("schedule_minutes", 1) not in (1, 2, 3, 5, 10, 15, 30, 60):
        raise ValueError("Invalid schedule interval")
    for fan in fans:
        if fan.get("mode") not in {"step", "linear"}:
            raise ValueError(f"Invalid curve mode for {fan.get('id')}")
        if not isinstance(fan.get("pwm"), int) or fan["pwm"] not in range(1, 9):
            raise ValueError(f"Invalid PWM channel for {fan.get('id')}")
        points = fan.get("points")
        if not isinstance(points, list) or len(points) < 2:
            raise ValueError(f"{fan.get('id')} needs at least two curve points")
        previous = -1
        for point in points:
            if not (isinstance(point, list) and len(point) == 2
                    and all(isinstance(value, int) for value in point)):
                raise ValueError("Every curve point must be [integer temperature, integer PWM]")
            temp, pwm = point
            if not 0 <= temp <= 100 or not 0 <= pwm <= 255 or temp <= previous:
                raise ValueError("Temperatures must increase from 0-100; PWM must be 0-255")
            previous = temp
    return data


def prerequisites() -> list[tuple[str, bool, str]]:
    return [("Python 3.10+", sys.version_info >= (3, 10), sys.version.split()[0]),
            ("curses", hasattr(curses, "wrapper"), "standard library"),
            ("lm-sensors", shutil.which("sensors") is not None, shutil.which("sensors") or "not found"),
            ("cron", shutil.which("crontab") is not None, shutil.which("crontab") or "not found"),
            ("hwmon sysfs", Path("/sys/class/hwmon").is_dir(), "/sys/class/hwmon")]


def discover_controllers(active_only: bool = True) -> list[dict[str, Any]]:
    found = []
    for hwmon in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
        try: name = (hwmon / "name").read_text().strip()
        except OSError: continue
        channels = []
        for pwm_path in sorted(hwmon.glob("pwm[0-9]*")):
            if not re.fullmatch(r"pwm\d+", pwm_path.name): continue
            number = int(pwm_path.name[3:]); enable = hwmon / f"pwm{number}_enable"; tach = hwmon / f"fan{number}_input"
            if not enable.exists(): continue
            try: rpm = int(tach.read_text()) if tach.exists() else None
            except (OSError, ValueError): rpm = None
            active = rpm is not None and rpm > 0
            if active_only and not active: continue
            channels.append({"pwm": number, "rpm": rpm, "active": active,
                             "writable": os.access(pwm_path, os.W_OK) and os.access(enable, os.W_OK)})
        if channels: found.append({"name": name, "path": str(hwmon.resolve()), "channels": channels})
    return found


def load_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return copy.deepcopy(DEFAULT_CONFIG)
    with CONFIG_FILE.open(encoding="utf-8") as handle:
        return validate_config(json.load(handle))


def atomic_save(data: dict[str, Any], path: Path = CONFIG_FILE) -> None:
    validate_config(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_sensors() -> dict[str, float]:
    output = subprocess.run(["sensors"], text=True, capture_output=True, check=True).stdout
    values: dict[str, float] = {}
    current_adapter = ""
    drives: list[float] = []
    wanted = {"Tctl": "cpu", "CPU": "cpu_fallback", "System": "system",
              "VRM MOS": "vrm", "PCH": "pch"}
    for line in output.splitlines():
        if line and not line[0].isspace() and ":" not in line:
            current_adapter = line.strip()
            continue
        match = re.match(r"^([^:]+):\s*\+?(-?\d+(?:\.\d+)?)°C", line)
        if not match:
            continue
        label, raw = match.group(1).strip(), float(match.group(2))
        if current_adapter.startswith("drivetemp-") and label == "temp1":
            drives.append(raw)
        if label in wanted and wanted[label] not in values:
            values[wanted[label]] = raw
    if "cpu" not in values and "cpu_fallback" in values:
        values["cpu"] = values["cpu_fallback"]
    if drives:
        values["hdd"] = max(drives)
    board = [values[key] for key in ("system", "vrm", "pch") if key in values]
    case = [values[key] for key in ("cpu", "system", "pch") if key in values]
    if board:
        values["board"] = max(board)
    if case:
        values["case"] = max(case)
    return values


def find_hwmon() -> Path:
    for path in Path("/sys/class/hwmon").glob("hwmon*"):
        try:
            if (path / "name").read_text().strip() == "nct6687":
                return path
        except OSError:
            pass
    raise RuntimeError("Could not find the nct6687 hwmon controller")


def curve_value(fan: dict[str, Any], temperature: float) -> int:
    points = fan["points"]
    if fan["mode"] == "step":
        result = points[0][1]
        for temp, pwm in points:
            if temperature < temp:
                break
            result = pwm
        return result
    if temperature <= points[0][0]:
        return points[0][1]
    for (t1, p1), (t2, p2) in zip(points, points[1:]):
        if temperature <= t2:
            return round(p1 + (temperature - t1) / (t2 - t1) * (p2 - p1))
    return points[-1][1]


def requested_pwms(config: dict[str, Any], temps: dict[str, float]) -> tuple[dict[str, int], list[str]]:
    missing = sorted({fan["sensor"] for fan in config["fans"]} - temps.keys())
    if missing:
        raise RuntimeError(f"Missing required temperatures: {', '.join(missing)}")
    values = {fan["id"]: curve_value(fan, temps[fan["sensor"]]) for fan in config["fans"]}
    overrides: list[str] = []
    for sensor in ("hdd", "board"):
        for rule in config.get("safety", {}).get(sensor, []):
            if temps.get(sensor, -999) >= rule["temp"]:
                for fan_id in ("middle", "exhaust"):
                    floor = rule.get(fan_id)
                    if floor is not None and values[fan_id] < floor:
                        values[fan_id] = floor
                        overrides.append(f"{sensor}>={rule['temp']}C: {fan_id}>={floor}")
    return values, overrides


def read_live(config: dict[str, Any]) -> tuple[dict[str, float], dict[str, int], dict[str, int], list[str]]:
    temps, hwmon = read_sensors(), find_hwmon()
    pwms: dict[str, int] = {}
    rpms: dict[str, int] = {}
    for fan in config["fans"]:
        try:
            pwms[fan["id"]] = int((hwmon / f"pwm{fan['pwm']}").read_text())
        except (OSError, ValueError):
            pass
        try:
            rpms[fan["id"]] = int((hwmon / f"fan{fan['fan_input']}_input").read_text())
        except (OSError, ValueError):
            pass
    _, overrides = requested_pwms(config, temps)
    return temps, pwms, rpms, overrides


def apply_config(config: dict[str, Any], quiet: bool = False) -> None:
    lock_fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if not quiet:
                print("fan control is already running; skipped")
            return
        temps = read_sensors()
        values, overrides = requested_pwms(config, temps)
        hwmon = find_hwmon()
        for fan in config["fans"]:
            pwm = fan["pwm"]
            enable_path, pwm_path = hwmon / f"pwm{pwm}_enable", hwmon / f"pwm{pwm}"
            if not os.access(enable_path, os.W_OK) or not os.access(pwm_path, os.W_OK):
                raise PermissionError(f"PWM{pwm} is not writable; run with sudo")
            enable_path.write_text("1\n")
            pwm_path.write_text(f"{values[fan['id']]}\n")
        if not quiet:
            keys = ("cpu", "hdd", "system", "vrm", "pch")
            print("Temps: " + " ".join(f"{key}={temps[key]:.1f}C" for key in keys if key in temps))
            print("PWM: " + " ".join(f"{key}={value}" for key, value in values.items()))
            if overrides:
                print("Safety: " + "; ".join(overrides))
    finally:
        os.close(lock_fd)


def cron_line(config: dict[str, Any]) -> str:
    minutes = config.get("schedule_minutes", 1)
    expression = "* * * * *" if minutes == 1 else f"*/{minutes} * * * *"
    return f"{expression} /usr/bin/python3 {SCRIPT} --apply >/dev/null 2>&1"


def install_cron(config: dict[str, Any]) -> None:
    if os.geteuid() != 0:
        raise PermissionError("Cron installation must run as root")
    proc = subprocess.run(["crontab", "-l"], text=True, capture_output=True)
    lines = proc.stdout.splitlines() if proc.returncode == 0 else []
    cleaned: list[str] = []
    skip_next = False
    for line in lines:
        if line.strip() in (CRON_MARKER, "# nam-fan-control (managed by fan_control.py)"):
            skip_next = True
            continue
        if skip_next and ("fan_control.py" in line or "fan_control.sh" in line):
            skip_next = False
            continue
        skip_next = False
        if "fan_control.sh" in line or "fan_control.py" in line:
            continue
        cleaned.append(line)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    line = cron_line(config)
    content = "\n".join(cleaned + [CRON_MARKER, line, ""])
    subprocess.run(["crontab", "-"], input=content, text=True, check=True)
    print(f"Root cron ensured: {line}")


class FanTUI:
    def __init__(self, screen: curses.window, config: dict[str, Any]):
        self.screen = screen
        self.config, self.saved = copy.deepcopy(config), copy.deepcopy(config)
        self.fan_index = self.point_index = 0
        self.status, self.status_error = "Ready — edits are unsaved until Save", False
        self.last_live = 0.0
        self.temps: dict[str, float] = {}
        self.pwms: dict[str, int] = {}
        self.rpms: dict[str, int] = {}
        self.overrides: list[str] = []
        self.schedule_active = False
        self.last_schedule_check = 0.0
        self.regions: list[tuple[int, int, int, int, str, int]] = []
        self.running = True

    @property
    def dirty(self) -> bool:
        return self.config != self.saved

    @property
    def fan(self) -> dict[str, Any]:
        return self.config["fans"][self.fan_index]

    def setup(self) -> None:
        curses.curs_set(0)
        self.screen.keypad(True)
        curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
        curses.mouseinterval(100)
        self.screen.timeout(500)
        if curses.has_colors():
            curses.start_color(); curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN, -1)
            curses.init_pair(2, curses.COLOR_GREEN, -1)
            curses.init_pair(3, curses.COLOR_YELLOW, -1)
            curses.init_pair(4, curses.COLOR_RED, -1)
            curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_CYAN)

    def put(self, y: int, x: int, text: str, attr: int = 0, width: int | None = None) -> None:
        rows, columns = self.screen.getmaxyx()
        if not (0 <= y < rows and 0 <= x < columns):
            return
        if width is not None:
            text = text[:width].ljust(width)
        try:
            self.screen.addstr(y, x, text[:max(0, columns - x - 1)], attr)
        except curses.error:
            pass

    def box(self, y: int, x: int, h: int, w: int, title: str, selected: bool = False) -> None:
        if h < 3 or w < 5:
            return
        attr = curses.color_pair(1) | (curses.A_BOLD if selected else 0)
        self.put(y, x, "+" + "-" * (w - 2) + "+", attr)
        for row in range(y + 1, y + h - 1):
            self.put(row, x, "|", attr); self.put(row, x + w - 1, "|", attr)
        self.put(y + h - 1, x, "+" + "-" * (w - 2) + "+", attr)
        self.put(y, x + 2, f" {title} ", attr | curses.A_BOLD)

    def refresh_live(self, force: bool = False) -> None:
        if not force and time.monotonic() - self.last_live < 2:
            return
        self.last_live = time.monotonic()
        try:
            self.temps, self.pwms, self.rpms, self.overrides = read_live(self.config)
        except Exception as exc:
            self.status, self.status_error = f"Live data: {exc}", True

    def refresh_schedule(self, force: bool = False) -> None:
        if not force and time.monotonic() - self.last_schedule_check < 5:
            return
        self.last_schedule_check = time.monotonic()
        daemon = subprocess.run(["systemctl", "is-active", "cron"], capture_output=True, text=True).stdout.strip() == "active"
        root_cron = subprocess.run(["sudo", "-n", "crontab", "-l"], capture_output=True, text=True)
        expected = cron_line(self.config)
        self.schedule_active = daemon and root_cron.returncode == 0 and CRON_MARKER in root_cron.stdout and expected in root_cron.stdout

    def graph_line(self, fan: dict[str, Any], y: int, x: int, h: int, w: int) -> None:
        for col in range(max(5, w)):
            value = curve_value(fan, col * 100 / max(1, w - 1))
            row = h - 1 - round(value * (h - 1) / 255)
            self.put(y + row, x + col, "#", curses.color_pair(2))
        sensor_temp = self.temps.get(fan["sensor"])
        if sensor_temp is not None:
            col = clamp(round(sensor_temp * (w - 1) / 100), 0, w - 1)
            for row in range(h):
                self.put(y + row, x + col, ":", curses.color_pair(3))

    def draw_cards(self, top: int, height: int, columns: int) -> None:
        gap, card_w, card_h = 1, (columns - 1) // 2, height // 2
        for index, fan in enumerate(self.config["fans"]):
            row, col = divmod(index, 2)
            y, x = top + row * card_h, col * (card_w + gap)
            h, w = (card_h if row == 0 else height - card_h), (card_w if col == 0 else columns - x)
            self.box(y, x, h, w, f"{index + 1} {fan['name']}  pwm{fan['pwm']}  [{fan['mode']}]",
                     index == self.fan_index)
            temp, live, rpm = self.temps.get(fan["sensor"]), self.pwms.get(fan["id"]), self.rpms.get(fan["id"])
            requested = curve_value(fan, temp) if temp is not None else None
            details = f"{fan['sensor']}: {temp:.1f}C" if temp is not None else f"{fan['sensor']}: --"
            details += f"  request {requested if requested is not None else '--'}  live {live if live is not None else '--'}  {rpm if rpm is not None else '--'} RPM"
            self.put(y + 1, x + 2, details, width=max(0, w - 4))
            self.graph_line(fan, y + 2, x + 2, max(1, h - 3), max(5, w - 4))
            self.regions.append((y, x, y + h - 1, x + w - 1, "fan", index))

    def draw_editor(self, y: int, height: int, columns: int) -> None:
        fan = self.fan
        table_w, graph_w = min(29, max(22, columns // 4)), columns - min(29, max(22, columns // 4)) - 1
        self.box(y, 0, height, graph_w, f"Edit {fan['name']} — click graph to move selected point")
        gy, gx, gh, gw = y + 2, 5, max(3, height - 4), max(10, graph_w - 7)
        for level, label in ((0, "255"), (64, "192"), (128, "128"), (192, " 64"), (255, "  0")):
            row = gy + round(level * (gh - 1) / 255)
            self.put(row, 1, label, curses.color_pair(1))
            for col in range(0, gw, 2): self.put(row, gx + col, ".", curses.A_DIM)
        previous = None
        for col in range(gw):
            value = curve_value(fan, col * 100 / max(1, gw - 1))
            row = gy + gh - 1 - round(value * (gh - 1) / 255)
            if previous is not None and fan["mode"] == "step":
                for vertical in range(min(previous, row), max(previous, row) + 1):
                    self.put(vertical, gx + col, "#", curses.color_pair(2))
            self.put(row, gx + col, "#", curses.color_pair(2)); previous = row
        sensor_temp = self.temps.get(fan["sensor"])
        if sensor_temp is not None:
            live_col = gx + clamp(round(sensor_temp * (gw - 1) / 100), 0, gw - 1)
            for live_row in range(gy, gy + gh):
                self.put(live_row, live_col, ":", curses.color_pair(3) | curses.A_BOLD)
            marker = f" {sensor_temp:.1f}C "
            marker_x = clamp(live_col - len(marker) // 2, gx, gx + gw - len(marker))
            self.put(gy, marker_x, marker, curses.color_pair(3) | curses.A_BOLD)
        self.regions.append((gy, gx, gy + gh - 1, gx + gw - 1, "graph", 0))
        for index, (temp, pwm) in enumerate(fan["points"]):
            col, row = gx + round(temp * (gw - 1) / 100), gy + gh - 1 - round(pwm * (gh - 1) / 255)
            self.put(row, col, "O" if index == self.point_index else "o",
                     curses.color_pair(3) | (curses.A_BOLD if index == self.point_index else 0))
            self.regions.append((row - 1, col - 1, row + 1, col + 1, "graph_point", index))
        self.put(gy + gh, gx, "0C" + " " * max(0, gw - 7) + "100C", curses.color_pair(1))
        tx = graph_w + 1
        self.box(y, tx, height, table_w, "Curve points")
        self.put(y + 1, tx + 2, " #   Temp    PWM   Percent", curses.A_BOLD)
        room, start = max(1, height - 4), max(0, self.point_index - max(1, height - 4) + 1)
        for visible, index in enumerate(range(start, min(len(fan["points"]), start + room))):
            temp, pwm = fan["points"][index]
            attr = curses.color_pair(5) | curses.A_BOLD if index == self.point_index else 0
            self.put(y + 2 + visible, tx + 1,
                     f" {index + 1:>2}   {temp:>3}C    {pwm:>3}    {pwm * 100 // 255:>3}% ", attr, table_w - 2)
            self.regions.append((y + 2 + visible, tx + 1, y + 2 + visible, tx + table_w - 2, "point", index))
        self.put(y + height - 2, tx + 2, "Arrows edit  A add  D delete", curses.A_DIM)

    def draw(self) -> None:
        self.refresh_live(); self.refresh_schedule(); self.screen.erase(); self.regions = []
        rows, columns = self.screen.getmaxyx()
        if rows < 28 or columns < 90:
            self.put(0, 0, f"Terminal too small ({columns}x{rows}); resize to at least 90x28.", curses.color_pair(4) | curses.A_BOLD)
            self.screen.refresh(); return
        self.put(0, 0, " NAM Fan Control " + ("[UNSAVED]" if self.dirty else "[saved]"), curses.color_pair(1) | curses.A_BOLD)
        header_help = "[? Help]"
        help_x = max(0, columns - 48)
        self.put(0, help_x, f"1-4 select | Tab cycle | {header_help} | q exit")
        self.regions.append((0, help_x + 25, 0, help_x + 32, "help", 0))
        cards_h = min(16, max(12, rows // 2 - 1))
        self.draw_cards(1, cards_h, columns)
        editor_y = 1 + cards_h
        self.draw_editor(editor_y, rows - editor_y - 3, columns)
        buttons = "[S Save] [F Max] [C Schedule] [T Temp] [E Export] [I Import] [M Mode] [? Help] [Q Exit]"
        self.put(rows - 2, 0, buttons, curses.color_pair(1) | curses.A_BOLD, columns - 1)
        cursor = 0
        for action, label in (("save", "[S Save]"), ("max", "[F Max]"),
                              ("schedule", "[C Schedule]"), ("temp", "[T Temp]"), ("export", "[E Export]"),
                              ("import", "[I Import]"), ("mode", "[M Mode]"),
                              ("help", "[? Help]"), ("exit", "[Q Exit]")):
            pos = buttons.find(label, cursor); cursor = pos + len(label)
            self.regions.append((rows - 2, pos, rows - 2, cursor - 1, action, 0))
        safety = " | Safety: " + "; ".join(self.overrides) if self.overrides else ""
        indicator = " CRON ACTIVE " if self.schedule_active else " CRON INACTIVE "
        indicator_x = max(0, columns - len(indicator) - 1)
        flash = curses.A_BOLD if int(time.monotonic() * 2) % 2 else curses.A_DIM
        self.put(rows - 1, 0, self.status + safety, curses.color_pair(4 if self.status_error else 3), indicator_x)
        self.put(rows - 1, indicator_x, indicator, curses.color_pair(2 if self.schedule_active else 4) | flash)
        self.screen.refresh()

    def change_point(self, temp_delta: int = 0, pwm_delta: int = 0) -> None:
        points, index = self.fan["points"], self.point_index
        temp, pwm = points[index]
        low = points[index - 1][0] + 1 if index else 0
        high = points[index + 1][0] - 1 if index + 1 < len(points) else 100
        points[index] = [clamp(temp + temp_delta, low, high), clamp(pwm + pwm_delta, 0, 255)]
        self.status, self.status_error = f"Edited {self.fan['name']} point {index + 1}", False

    def max_curve(self) -> None:
        for point in self.fan["points"]: point[1] = 255
        self.status, self.status_error = f"{self.fan['name']}: all points set to PWM 255; unsaved", False

    def add_point(self) -> None:
        points, index = self.fan["points"], self.point_index
        if len(points) >= 20:
            self.status, self.status_error = "Maximum 20 points per curve", True; return
        if index + 1 < len(points):
            left, right = points[index], points[index + 1]
            if right[0] - left[0] < 2:
                self.status, self.status_error = "No temperature space between points", True; return
            self.point_index += 1
            points.insert(self.point_index, [(left[0] + right[0]) // 2, (left[1] + right[1]) // 2])
        elif points[-1][0] < 100:
            points.append([min(100, points[-1][0] + 5), points[-1][1]]); self.point_index += 1
        else:
            self.status, self.status_error = "Last point is already at 100C", True; return
        self.status, self.status_error = "Curve point added", False

    def add_point_at(self, temp: int, pwm: int) -> None:
        points = self.fan["points"]
        if len(points) >= 20:
            self.status, self.status_error = "Maximum 20 points per curve", True; return
        temp, pwm = clamp(temp, 0, 100), clamp(pwm, 0, 255)
        if any(existing[0] == temp for existing in points):
            self.status, self.status_error = f"A point already exists at {temp}C", True; return
        insert_at = next((i for i, point in enumerate(points) if point[0] > temp), len(points))
        points.insert(insert_at, [temp, pwm]); self.point_index = insert_at
        self.status, self.status_error = f"Added point at {temp}C / PWM {pwm}", False

    def delete_point(self) -> None:
        if len(self.fan["points"]) <= 2:
            self.status, self.status_error = "A curve needs at least two points", True; return
        del self.fan["points"][self.point_index]
        self.point_index = min(self.point_index, len(self.fan["points"]) - 1)
        self.status, self.status_error = "Curve point deleted", False

    def terminal_command(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        curses.def_prog_mode(); curses.endwin()
        try:
            print("\nRunning: " + " ".join(command))
            result = subprocess.run(command, text=True)
            input("Press Enter to return to Fan Control...")
            return result
        finally:
            curses.reset_prog_mode(); curses.curs_set(0); self.screen.keypad(True); self.screen.clear()

    def save_apply(self) -> None:
        try:
            atomic_save(self.config)
            result = self.terminal_command(["sudo", sys.executable, str(SCRIPT), "--install-cron", "--apply"])
            if result.returncode == 0:
                self.saved = copy.deepcopy(self.config)
                self.status, self.status_error = "Saved, applied, and root cron ensured", False
                self.refresh_live(True)
            else:
                self.status, self.status_error = "Config saved, but apply/cron failed", True
        except Exception as exc:
            self.status, self.status_error = f"Save failed: {exc}", True

    def export_config(self) -> None:
        confirmed, label = self.export_name_prompt()
        if not confirmed:
            self.status, self.status_error = "Export cancelled", False
            return
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = f"FanExport_{profile_slug(label)}_{stamp}" if label else f"FanExport_{stamp}"
        path, counter = USER_HOME / f"{prefix}.json", 1
        while path.exists():
            path = USER_HOME / f"{prefix}_{counter}.json"; counter += 1
        try:
            exported = copy.deepcopy(self.config)
            if label: exported["profile_name"] = label[:80]
            atomic_save(exported, path)
            self.status, self.status_error = f"Exported to {path.name}", False
        except Exception as exc:
            self.status, self.status_error = f"Export failed: {exc}", True

    def choose_import(self) -> None:
        exports = sorted(USER_HOME.glob("FanExport_*.json"), reverse=True)
        if not exports:
            self.status, self.status_error = "No FanExport_*.json files found in your home", True; return
        choice = 0
        while True:
            self.screen.erase(); rows, columns = self.screen.getmaxyx()
            self.box(1, 2, min(rows - 3, len(exports) + 5), columns - 4, "Import fan template")
            self.put(2, 4, "Import loads into the editor; Save applies it.")
            room, start = max(1, rows - 7), max(0, choice - max(1, rows - 7) + 1)
            for visible, index in enumerate(range(start, min(len(exports), start + room))):
                try:
                    with exports[index].open(encoding="utf-8") as handle: label = json.load(handle).get("profile_name")
                except (OSError, ValueError, AttributeError): label = None
                display = f"{label}  [{exports[index].name}]" if label else exports[index].name
                self.put(4 + visible, 4, display, curses.color_pair(5) if index == choice else 0, columns - 8)
            self.put(rows - 2, 4, "Up/Down select   Enter import   N rename   Esc cancel", curses.color_pair(1)); self.screen.refresh()
            key = self.screen.getch()
            if key in (27, ord("q")): return
            if key in (curses.KEY_UP, ord("k")): choice = (choice - 1) % len(exports)
            elif key in (curses.KEY_DOWN, ord("j")): choice = (choice + 1) % len(exports)
            elif key in (ord("n"), ord("N")):
                try:
                    with exports[choice].open(encoding="utf-8") as handle: profile = validate_config(json.load(handle))
                    confirmed, label = self.import_rename_prompt(str(profile.get("profile_name", "")))
                    if confirmed and label:
                        profile["profile_name"] = label[:80]
                        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                        destination = USER_HOME / f"FanExport_{profile_slug(label)}_{stamp}.json"
                        counter = 1
                        while destination.exists():
                            destination = USER_HOME / f"FanExport_{profile_slug(label)}_{stamp}_{counter}.json"; counter += 1
                        atomic_save(profile, destination); exports[choice].unlink(); exports[choice] = destination
                        self.status, self.status_error = f"Profile renamed to {label}", False
                except Exception as exc: self.status, self.status_error = f"Rename failed: {exc}", True
            elif key in (10, 13, curses.KEY_ENTER):
                try:
                    with exports[choice].open(encoding="utf-8") as handle: self.config = validate_config(json.load(handle))
                    self.fan_index = self.point_index = 0
                    self.status, self.status_error = f"Imported {exports[choice].name}; unsaved", False
                except Exception as exc:
                    self.status, self.status_error = f"Import failed: {exc}", True
                return

    def toggle_mode(self) -> None:
        self.fan["mode"] = "linear" if self.fan["mode"] == "step" else "step"
        self.status, self.status_error = f"{self.fan['name']} mode: {self.fan['mode']}", False

    def text_prompt(self, title: str, initial: str = "") -> str | None:
        curses.echo(); curses.curs_set(1); self.screen.timeout(-1)
        try:
            rows, columns = self.screen.getmaxyx(); width = min(68, columns - 8)
            self.box(rows // 2 - 2, 3, 5, width, title)
            self.put(rows // 2, 5, initial, curses.color_pair(5), width - 4)
            self.screen.move(rows // 2, 5); self.screen.refresh()
            value = self.screen.getstr(rows // 2, 5, width - 5).decode("utf-8", "replace").strip()
            return value or None
        finally: self.screen.timeout(500); curses.noecho(); curses.curs_set(0)

    def export_name_prompt(self) -> tuple[bool, str]:
        value = ""
        self.screen.timeout(-1); curses.curs_set(1)
        try:
            while True:
                rows, columns = self.screen.getmaxyx()
                prompt = "Export name (optional): "
                available = max(1, columns - len(prompt) - 2)
                visible = value[-available:]
                # Export mode owns the complete footer: remove the normal
                # Save/Import/Mode/Help/Exit buttons and status text first.
                self.screen.move(rows - 2, 0); self.screen.clrtoeol()
                self.screen.move(rows - 1, 0); self.screen.clrtoeol()
                self.put(rows - 2, 0, prompt + visible, curses.color_pair(5) | curses.A_BOLD)
                controls = "[Enter] Confirm Export    [Esc] Cancel Export"
                self.put(rows - 1, 0, controls, curses.color_pair(1) | curses.A_BOLD)
                self.screen.move(rows - 2, min(columns - 2, len(prompt) + len(visible)))
                self.screen.refresh()
                key = self.screen.getch()
                if key in (10, 13, curses.KEY_ENTER): return True, value.strip()[:80]
                if key == 27: return False, ""
                if key in (curses.KEY_BACKSPACE, 127, 8): value = value[:-1]
                elif 32 <= key <= 126 and len(value) < 80: value += chr(key)
        finally:
            self.screen.timeout(500); curses.curs_set(0)

    def import_rename_prompt(self, initial: str = "") -> tuple[bool, str]:
        value = initial[:80]
        self.screen.timeout(-1); curses.curs_set(1)
        try:
            while True:
                rows, columns = self.screen.getmaxyx()
                prompt = "Rename profile: "
                available = max(1, columns - len(prompt) - 2)
                visible = value[-available:]
                # Rename mode owns the footer, hiding the normal import actions.
                self.screen.move(rows - 2, 0); self.screen.clrtoeol()
                self.screen.move(rows - 1, 0); self.screen.clrtoeol()
                self.put(rows - 2, 0, prompt + visible, curses.color_pair(5) | curses.A_BOLD)
                controls = "[Enter] Confirm Rename    [Esc] Cancel Rename"
                self.put(rows - 1, 0, controls, curses.color_pair(1) | curses.A_BOLD)
                self.screen.move(rows - 2, min(columns - 2, len(prompt) + len(visible)))
                self.screen.refresh()
                key = self.screen.getch()
                if key in (10, 13, curses.KEY_ENTER): return True, value.strip()[:80]
                if key == 27: return False, ""
                if key in (curses.KEY_BACKSPACE, 127, 8): value = value[:-1]
                elif 32 <= key <= 126 and len(value) < 80: value += chr(key)
        finally:
            self.screen.timeout(500); curses.curs_set(0)

    def rename_fan(self) -> None:
        confirmed, name = self.pwm_rename_prompt()
        if confirmed and name:
            self.fan["name"] = name[:48]
            self.status, self.status_error = f"PWM{self.fan['pwm']} renamed / labeled", False
        elif not confirmed:
            self.status, self.status_error = "PWM rename cancelled", False

    def pwm_rename_prompt(self) -> tuple[bool, str]:
        value = self.fan["name"][:48]
        self.screen.timeout(-1); curses.curs_set(1)
        try:
            while True:
                rows, columns = self.screen.getmaxyx()
                prompt = f"Renaming / Labeling PWM{self.fan['pwm']} to: "
                available = max(1, columns - len(prompt) - 2)
                visible = value[-available:]
                self.screen.move(rows - 2, 0); self.screen.clrtoeol()
                self.screen.move(rows - 1, 0); self.screen.clrtoeol()
                self.put(rows - 2, 0, prompt + visible, curses.color_pair(5) | curses.A_BOLD)
                self.put(rows - 1, 0, "[Enter] Confirm Label    [Esc] Cancel Label", curses.color_pair(1) | curses.A_BOLD)
                self.screen.move(rows - 2, min(columns - 2, len(prompt) + len(visible)))
                self.screen.refresh()
                key = self.screen.getch()
                if key in (10, 13, curses.KEY_ENTER): return True, value.strip()
                if key == 27: return False, ""
                if key in (curses.KEY_BACKSPACE, 127, 8): value = value[:-1]
                elif 32 <= key <= 126 and len(value) < 48: value += chr(key)
        finally:
            self.screen.timeout(500); curses.curs_set(0)

    def choose_temp_source(self) -> None:
        labels = {"cpu": "CPU", "hdd": "Hottest HDD", "system": "System",
                  "vrm": "VRM MOS", "pch": "PCH / Chipset",
                  "board": "Board maximum", "case": "Case maximum"}
        sources = [(key, labels[key], self.temps[key]) for key in labels if key in self.temps]
        if not sources:
            self.status, self.status_error = "No temperature sources are currently available", True; return
        current = self.fan["sensor"]
        choice = next((i for i, source in enumerate(sources) if source[0] == current), 0)
        self.screen.timeout(-1)
        try:
            while True:
                self.screen.erase(); rows, columns = self.screen.getmaxyx()
                width = min(72, columns - 4); height = min(rows - 4, len(sources) + 7)
                self.box(1, 2, height, width, f"Temperature source for PWM{self.fan['pwm']} — {self.fan['name']}")
                self.put(2, 4, "Select the sensor that controls this fan curve:", curses.A_BOLD)
                row_map: dict[int, int] = {}
                for index, (key, label, temp) in enumerate(sources):
                    row = 4 + index; row_map[row] = index
                    marker = "CURRENT" if key == current else ""
                    text = f" {label:<20} {temp:>6.1f}C   {marker} "
                    self.put(row, 4, text, curses.color_pair(5) if index == choice else 0, width - 6)
                self.put(2 + height - 2, 4, "Up/Down or mouse select   Enter confirm   Esc cancel", curses.color_pair(1))
                self.screen.refresh(); key = self.screen.getch()
                if key == 27:
                    self.status, self.status_error = "Temperature-source change cancelled", False; return
                if key in (curses.KEY_UP, ord("k")): choice = (choice - 1) % len(sources)
                elif key in (curses.KEY_DOWN, ord("j")): choice = (choice + 1) % len(sources)
                elif key == curses.KEY_MOUSE:
                    try: _, mx, my, _, state = curses.getmouse()
                    except curses.error: continue
                    if state & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED) and my in row_map and 4 <= mx < width:
                        choice = row_map[my]
                elif key in (10, 13, curses.KEY_ENTER):
                    source, label, temp = sources[choice]
                    self.fan["sensor"] = source
                    self.status, self.status_error = f"PWM{self.fan['pwm']} source: {label} ({temp:.1f}C); unsaved", False
                    return
        finally: self.screen.timeout(500)

    def cycle_schedule(self) -> None:
        choices = (1, 2, 3, 5, 10, 15, 30, 60); current = self.config.get("schedule_minutes", 1)
        self.config["schedule_minutes"] = choices[(choices.index(current) + 1) % len(choices)]
        self.status = f"Schedule every {self.config['schedule_minutes']} minute(s); Save to activate"

    def help(self) -> None:
        lines = ["1-4 / Tab       Select fan group", "Up / Down       Select curve point",
                 "Left / Right    Change point temperature by 1C", "- / +           Change PWM by 5",
                 "A / D           Add or delete point", "M               Toggle step/linear curve",
                 "F               Set every selected-curve point to maximum",
                 "C               Adjust / cycle cron schedule interval",
                 "T               Choose temperature source; shows live values",
                 "N               Rename / Label selected PWM Channel",
                 "Left click      Select cards/rows; move selected point on graph",
                 "Right click O   Select that curve point on the main graph",
                 "Ctrl+right      Add a point at that graph position",
                 "S               Save, apply now, and ensure configured root cron",
                 "E / I           Export current state / import template",
                 "Green/Red CRON  Managed schedule active / inactive",
                 "Q / Ctrl+C      Exit; unsaved changes are discarded",
                 "Esc             Cancel the current dialog only"]
        self.screen.erase(); rows, columns = self.screen.getmaxyx(); width = min(columns - 4, 78)
        self.box(2, 2, min(rows - 4, len(lines) + 5), width, "Help")
        for index, line in enumerate(lines): self.put(4 + index, 4, line)
        self.put(min(rows - 3, 5 + len(lines)), 4, "Press any key to return", curses.color_pair(1))
        self.screen.refresh()
        self.screen.timeout(-1)
        try: self.screen.getch()
        finally: self.screen.timeout(500)

    def mouse(self) -> None:
        try: _, mx, my, _, state = curses.getmouse()
        except curses.error: return
        left = bool(state & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED | curses.BUTTON1_RELEASED))
        right = bool(state & (curses.BUTTON3_CLICKED | curses.BUTTON3_PRESSED | curses.BUTTON3_RELEASED))
        controlled = bool(state & curses.BUTTON_CTRL)
        if not (left or right): return
        for y1, x1, y2, x2, action, value in reversed(self.regions):
            if y1 <= my <= y2 and x1 <= mx <= x2:
                if action == "fan" and left: self.fan_index, self.point_index = value, 0
                elif action == "point" and left: self.point_index = value
                elif action == "graph_point" and right and not controlled:
                    self.point_index = value; self.status = f"Selected curve point {value + 1}"
                elif action == "graph":
                    temp = round((mx - x1) * 100 / max(1, x2 - x1)); pwm = round((y2 - my) * 255 / max(1, y2 - y1))
                    if right and controlled: self.add_point_at(temp, pwm)
                    elif left:
                        old_temp, old_pwm = self.fan["points"][self.point_index]
                        self.change_point(temp - old_temp, pwm - old_pwm)
                elif action == "save": self.save_apply()
                elif action == "max": self.max_curve()
                elif action == "schedule": self.cycle_schedule()
                elif action == "temp": self.choose_temp_source()
                elif action == "export": self.export_config()
                elif action == "import": self.choose_import()
                elif action == "mode": self.toggle_mode()
                elif action == "help": self.help()
                elif action == "exit": self.running = False
                return

    def handle(self, key: int) -> None:
        if key == curses.KEY_MOUSE: self.mouse(); return
        if key in (-1, curses.KEY_RESIZE): return
        if ord("1") <= key <= ord("4"): self.fan_index, self.point_index = key - ord("1"), 0
        elif key == 9: self.fan_index, self.point_index = (self.fan_index + 1) % 4, 0
        elif key in (curses.KEY_UP, ord("k")): self.point_index = (self.point_index - 1) % len(self.fan["points"])
        elif key in (curses.KEY_DOWN, ord("j")): self.point_index = (self.point_index + 1) % len(self.fan["points"])
        elif key in (curses.KEY_LEFT, ord("h")): self.change_point(temp_delta=-1)
        elif key in (curses.KEY_RIGHT, ord("l")): self.change_point(temp_delta=1)
        elif key in (ord("-"), ord("_")): self.change_point(pwm_delta=-5 if key == ord("-") else -10)
        elif key in (ord("+"), ord("=")): self.change_point(pwm_delta=10 if key == ord("+") else 5)
        elif key in (ord("a"), ord("A")): self.add_point()
        elif key in (ord("d"), ord("D"), curses.KEY_DC): self.delete_point()
        elif key in (ord("m"), ord("M")): self.toggle_mode()
        elif key in (ord("f"), ord("F")): self.max_curve()
        elif key in (ord("n"), ord("N")): self.rename_fan()
        elif key in (ord("c"), ord("C")): self.cycle_schedule()
        elif key in (ord("t"), ord("T")): self.choose_temp_source()
        elif key in (ord("s"), ord("S")): self.save_apply()
        elif key in (ord("e"), ord("E")): self.export_config()
        elif key in (ord("i"), ord("I")): self.choose_import()
        elif key in (ord("?"), curses.KEY_F1): self.help()
        elif key in (ord("q"), ord("Q")): self.running = False

    def run(self) -> None:
        self.setup()
        while self.running:
            self.draw(); self.handle(self.screen.getch())


def run_tui(config: dict[str, Any]) -> None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError("The editor needs an interactive terminal")
    curses.wrapper(lambda screen: FanTUI(screen, config).run())


def print_status(config: dict[str, Any]) -> None:
    temps, pwms, rpms, overrides = read_live(config)
    values, _ = requested_pwms(config, temps)
    print("Fan group       Sensor       Temp   Requested   Live PWM   RPM")
    print("--------------- ------------ ------ ----------- ---------- ------")
    for fan in config["fans"]:
        fan_id = fan["id"]
        print(f"{fan['name']:<15} {fan['sensor']:<12} {temps[fan['sensor']]:>5.1f}C"
              f" {values[fan_id]:>9} {pwms.get(fan_id, 0):>10} {rpms.get(fan_id, 0):>6}")
    if overrides: print("Safety overrides: " + "; ".join(overrides))


def main() -> int:
    parser = argparse.ArgumentParser(description="NCT6687 fan controller and terminal UI")
    parser.add_argument("--apply", action="store_true", help="apply saved curves once")
    parser.add_argument("--install-cron", action="store_true", help="ensure root one-minute cron")
    parser.add_argument("--status", action="store_true", help="print temperatures, PWM, and RPM")
    parser.add_argument("--init-config", action="store_true", help="write defaults if absent")
    parser.add_argument("--doctor", action="store_true", help="check prerequisites and hardware")
    parser.add_argument("--discover", action="store_true", help="list controllable PWM channels")
    parser.add_argument("--all-channels", action="store_true", help="include zero-RPM channels")
    parser.add_argument("--schedule", type=int, choices=(1,2,3,5,10,15,30,60), help="cron interval in minutes")
    parser.add_argument("--version", action="version", version=f"fan-control-tui {APP_VERSION}")
    args = parser.parse_args()
    try:
        config = load_config()
        if args.init_config and not CONFIG_FILE.exists(): atomic_save(config); print(f"Created {CONFIG_FILE}")
        if args.schedule: config["schedule_minutes"] = args.schedule; atomic_save(config)
        if args.install_cron: install_cron(config)
        if args.apply: apply_config(config)
        if args.status: print_status(config)
        if args.doctor:
            for name, ok, detail in prerequisites(): print(f"[{'OK' if ok else 'FAIL'}] {name}: {detail}")
            controllers = discover_controllers(False)
            print(f"[{'OK' if controllers else 'FAIL'}] PWM controllers: {len(controllers)}")
        if args.discover:
            for controller in discover_controllers(not args.all_channels):
                print(f"{controller['name']}  {controller['path']}")
                for channel in controller['channels']:
                    state = "active" if channel['active'] else "inactive"
                    print(f"  PWM{channel['pwm']}: {state}, RPM={channel['rpm']}, writable={channel['writable']}")
        actions = (args.apply, args.install_cron, args.status, args.init_config, args.doctor, args.discover, args.schedule)
        if not any(actions): run_tui(config)
        return 0
    except KeyboardInterrupt: return 130
    except Exception as exc: print(f"fan-control: {exc}", file=sys.stderr); return 1


if __name__ == "__main__":
    raise SystemExit(main())
