import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List


APP_CONFIG_DIR_NAME = "CampusCheckinKit"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "app_name": "CampusCheckinKit",
    "enable_reminder": True,
    "enable_network": True,
    "onboarding_completed": False,
    "start_with_main_window": False,
    "quiet_start": False,
    # 今日校园提醒
    "remind_time": "21:00",
    "snooze_minutes": 10,
    "skip_holidays": False,
    "skip_weekends": False,
    "pause_ranges": [],
    "last_ack_date": "",
    "last_reminded_date": "",
    # CUMT 校园网自动登录与保活
    "network_login_enabled": True,
    "network_username": "",
    "network_password": "",
    "network_isp": "校园网",
    "network_auto_login": False,
    "network_keep_alive": False,
    "network_auto_wifi": False,
    "network_wifi_ssid": "CUMT_Stu",
    "network_night_mode": True,
    "network_probe_interval_seconds": 15,
    "network_suspend_on_holiday": True,
    "last_network_login_at": "",
    "last_network_login_status": "",
    # 通知配置 - 支持 system(系统推送)、toast(简洁通知)、none(关闭通知)
    "notification_startup": "toast",
    "notification_checkin": "toast",
    "notification_network": "toast",
    "notification_debug": "system",
}


@dataclass(frozen=True)
class PauseRange:
    start: date
    end: date


def _config_dir() -> Path:
    appdata = Path.home() / "AppData" / "Roaming"
    return appdata / APP_CONFIG_DIR_NAME


class SettingsStore:
    def __init__(self, settings_path: Path | None = None) -> None:
        self.settings_path = settings_path or (_config_dir() / "settings.json")
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_dir = self.settings_path.parent / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._settings = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.settings_path.exists():
            self._save(DEFAULT_SETTINGS.copy())
            return DEFAULT_SETTINGS.copy()

        try:
            raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
            merged = DEFAULT_SETTINGS.copy()
            merged.update(raw)
            merged["pause_ranges"] = self._normalize_pause_ranges(merged.get("pause_ranges", []))
            return merged
        except Exception:
            self._save(DEFAULT_SETTINGS.copy())
            return DEFAULT_SETTINGS.copy()

    def _save(self, settings: Dict[str, Any]) -> None:
        self.settings_path.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save(self) -> None:
        self._settings["pause_ranges"] = self._normalize_pause_ranges(self._settings.get("pause_ranges", []))
        self._save(self._settings)

    # ---- 通用开关 ----

    def get_bool(self, key: str, default: bool = False) -> bool:
        return bool(self._settings.get(key, default))

    def set_bool(self, key: str, value: bool) -> None:
        self._settings[key] = bool(value)
        self.save()

    # ---- 提醒 ----

    def is_reminder_enabled(self) -> bool:
        return self.get_bool("enable_reminder", True)

    def is_network_enabled(self) -> bool:
        return self.get_bool("enable_network", True)

    def get_remind_time(self) -> str:
        value = str(self._settings.get("remind_time", DEFAULT_SETTINGS["remind_time"]))
        parts = value.split(":")
        if len(parts) != 2:
            return DEFAULT_SETTINGS["remind_time"]
        try:
            hour = int(parts[0])
            minute = int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return DEFAULT_SETTINGS["remind_time"]
        except Exception:
            return DEFAULT_SETTINGS["remind_time"]
        return value

    def set_remind_time(self, value: str) -> None:
        self._settings["remind_time"] = value
        self.save()

    def get_snooze_minutes(self) -> int:
        value = self._settings.get("snooze_minutes", DEFAULT_SETTINGS["snooze_minutes"])
        try:
            parsed = int(value)
            return parsed if parsed > 0 else DEFAULT_SETTINGS["snooze_minutes"]
        except Exception:
            return DEFAULT_SETTINGS["snooze_minutes"]

    def set_snooze_minutes(self, value: int) -> None:
        self._settings["snooze_minutes"] = max(1, int(value))
        self.save()

    def get_last_ack_date(self) -> str:
        return str(self._settings.get("last_ack_date", ""))

    def set_last_ack_date(self, value: str) -> None:
        self._settings["last_ack_date"] = value
        self.save()

    def clear_last_ack_date(self) -> None:
        self._settings["last_ack_date"] = ""
        self.save()

    def get_last_reminded_date(self) -> str:
        return str(self._settings.get("last_reminded_date", ""))

    def set_last_reminded_date(self, value: str) -> None:
        self._settings["last_reminded_date"] = value
        self.save()

    def clear_last_reminded_date(self) -> None:
        self._settings["last_reminded_date"] = ""
        self.save()

    def get_pause_ranges(self) -> List[PauseRange]:
        result: List[PauseRange] = []
        for item in self._settings.get("pause_ranges", []):
            try:
                start = datetime.strptime(item["start"], "%Y-%m-%d").date()
                end = datetime.strptime(item["end"], "%Y-%m-%d").date()
                result.append(PauseRange(start=start, end=end))
            except Exception:
                continue
        return sorted(result, key=lambda r: (r.start, r.end))

    def set_pause_ranges(self, ranges: List[Dict[str, str]]) -> None:
        self._settings["pause_ranges"] = self._merge_ranges(self._normalize_pause_ranges(ranges))
        self.save()

    def add_pause_range(self, start: date, end: date) -> None:
        if end < start:
            raise ValueError("结束日期不能早于开始日期。")
        ranges = self._settings.get("pause_ranges", [])
        ranges.append({"start": start.isoformat(), "end": end.isoformat()})
        self._settings["pause_ranges"] = self._merge_ranges(self._normalize_pause_ranges(ranges))
        self.save()

    def is_paused_on(self, day: date) -> bool:
        for pause_range in self.get_pause_ranges():
            if pause_range.start <= day <= pause_range.end:
                return True
        return False

    # ---- 校园网 ----

    def get_network_login_config(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self._settings.get("network_login_enabled", False)) and self.is_network_enabled(),
            "username": str(self._settings.get("network_username", "")),
            "password": str(self._settings.get("network_password", "")),
            "isp": str(self._settings.get("network_isp", DEFAULT_SETTINGS["network_isp"])),
            "auto_login": bool(self._settings.get("network_auto_login", False)),
            "keep_alive": bool(self._settings.get("network_keep_alive", False)),
            "auto_wifi": bool(self._settings.get("network_auto_wifi", False)),
            "wifi_ssid": str(self._settings.get("network_wifi_ssid", DEFAULT_SETTINGS["network_wifi_ssid"])),
            "night_mode": bool(self._settings.get("network_night_mode", True)),
            "probe_interval_seconds": self.get_network_probe_interval_seconds(),
            "suspend_on_holiday": bool(self._settings.get("network_suspend_on_holiday", True)),
        }

    def set_network_login_config(self, config: Dict[str, Any]) -> None:
        self._settings["network_login_enabled"] = bool(config.get("enabled", False))
        self._settings["network_username"] = str(config.get("username", ""))
        self._settings["network_password"] = str(config.get("password", ""))
        self._settings["network_isp"] = str(config.get("isp", DEFAULT_SETTINGS["network_isp"]))
        self._settings["network_auto_login"] = bool(config.get("auto_login", False))
        self._settings["network_keep_alive"] = bool(config.get("keep_alive", False))
        self._settings["network_auto_wifi"] = bool(config.get("auto_wifi", False))
        self._settings["network_wifi_ssid"] = str(config.get("wifi_ssid", DEFAULT_SETTINGS["network_wifi_ssid"]))
        self._settings["network_night_mode"] = bool(config.get("night_mode", True))
        self._settings["network_probe_interval_seconds"] = self._normalize_network_probe_interval(
            config.get("probe_interval_seconds", DEFAULT_SETTINGS["network_probe_interval_seconds"])
        )
        self._settings["network_suspend_on_holiday"] = bool(config.get("suspend_on_holiday", True))
        self.save()

    def get_network_probe_interval_seconds(self) -> int:
        return self._normalize_network_probe_interval(
            self._settings.get("network_probe_interval_seconds", DEFAULT_SETTINGS["network_probe_interval_seconds"])
        )

    @staticmethod
    def _normalize_network_probe_interval(value: Any) -> int:
        try:
            return min(60, max(10, int(value)))
        except (TypeError, ValueError):
            return int(DEFAULT_SETTINGS["network_probe_interval_seconds"])

    def set_last_network_login_result(self, ok: bool, message: str) -> None:
        self._settings["last_network_login_at"] = datetime.now().isoformat(timespec="seconds")
        self._settings["last_network_login_status"] = ("成功" if ok else "失败") + f": {message}"
        self.save()

    def get_last_network_login_status(self) -> str:
        status = str(self._settings.get("last_network_login_status", ""))
        at = str(self._settings.get("last_network_login_at", ""))
        if not status:
            return "未登录"
        if at:
            return f"{status} ({at})"
        return status

    # ---- 通知 ----

    def get_notification_config(self) -> Dict[str, str]:
        """获取通知配置"""
        return {
            "startup": str(self._settings.get("notification_startup", "toast")),
            "checkin": str(self._settings.get("notification_checkin", "toast")),
            "network": str(self._settings.get("notification_network", "toast")),
            "debug": str(self._settings.get("notification_debug", "system")),
        }

    def set_notification_config(self, config: Dict[str, str]) -> None:
        """设置通知配置"""
        valid_types = ["system", "toast", "none"]
        for key, value in config.items():
            if key in ["startup", "checkin", "network", "debug"]:
                if value in valid_types:
                    self._settings[f"notification_{key}"] = value
        self.save()

    def get_notification_type(self, category: str) -> str:
        """获取指定分类的通知类型"""
        config = self.get_notification_config()
        return config.get(category, "toast")

    def set_notification_type(self, category: str, notification_type: str) -> None:
        """设置指定分类的通知类型"""
        valid_types = ["system", "toast", "none"]
        if category in ["startup", "checkin", "network", "debug"] and notification_type in valid_types:
            self._settings[f"notification_{category}"] = notification_type
            self.save()

    # ---- 假期 ----

    def is_skip_holidays(self) -> bool:
        return self.get_bool("skip_holidays", False)

    def is_skip_weekends(self) -> bool:
        return self.get_bool("skip_weekends", False)

    # ---- 内部 ----

    @staticmethod
    def _normalize_pause_ranges(ranges: List[Dict[str, str]]) -> List[Dict[str, str]]:
        normalized: List[Dict[str, str]] = []
        for item in ranges:
            if not isinstance(item, dict):
                continue
            start = item.get("start")
            end = item.get("end")
            try:
                start_date = datetime.strptime(str(start), "%Y-%m-%d").date()
                end_date = datetime.strptime(str(end), "%Y-%m-%d").date()
            except Exception:
                continue
            if end_date < start_date:
                continue
            normalized.append({"start": start_date.isoformat(), "end": end_date.isoformat()})
        return normalized

    @staticmethod
    def _merge_ranges(ranges: List[Dict[str, str]]) -> List[Dict[str, str]]:
        if not ranges:
            return []

        tuples = sorted(
            [
                (
                    datetime.strptime(item["start"], "%Y-%m-%d").date(),
                    datetime.strptime(item["end"], "%Y-%m-%d").date(),
                )
                for item in ranges
            ],
            key=lambda x: (x[0], x[1]),
        )

        merged: List[tuple[date, date]] = [tuples[0]]
        for start, end in tuples[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end.fromordinal(last_end.toordinal() + 1):
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))

        return [{"start": s.isoformat(), "end": e.isoformat()} for s, e in merged]
