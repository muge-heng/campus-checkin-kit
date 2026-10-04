import random
import socket
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from typing import Any, Callable


EPORTAL_LOGIN_URL_BASE = "http://10.2.5.251:801/eportal/"

ISP_ACCOUNT_SUFFIX_MAP = {
    "校园网": "",
    "中国电信": "@telecom",
    "中国移动": "@cmcc",
    "中国联通": "@unicom",
}
ISP_DISPLAY_LIST = list(ISP_ACCOUNT_SUFFIX_MAP.keys())


@dataclass
class NetworkLoginConfig:
    enabled: bool
    username: str
    password: str
    isp: str
    auto_login: bool
    keep_alive: bool
    auto_wifi: bool
    wifi_ssid: str
    night_mode: bool
    probe_interval_seconds: int
    smart_night_cut: bool = True
    cut_start_time: str = "23:30"
    cut_end_time: str = "07:00"

    def has_credentials(self) -> bool:
        return bool(self.username.strip() and self.password)


@dataclass
class NetworkLoginResult:
    ok: bool
    message: str
    detail: dict[str, Any] | None = None


class NetworkLoginService:
    def __init__(self) -> None:
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )

    @staticmethod
    def local_ip() -> str:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(0.2)
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except Exception:
            pass
        finally:
            if sock:
                sock.close()

        try:
            host = socket.gethostname()
            for ip in socket.gethostbyname_ex(host)[2]:
                if not ip.startswith("127."):
                    return ip
        except Exception:
            pass
        return "10.0.0.1"

    @staticmethod
    def mac() -> str:
        try:
            return format(uuid.getnode(), "012x").upper()
        except Exception:
            return "000000000000"

    def check_connectivity(self, timeout: float = 3.0) -> bool:
        urls = (
            "https://www.baidu.com",
            "https://connectivitycheck.gstatic.com/generate_204",
        )
        for url in urls:
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent}, method="HEAD")
            try:
                with urllib.request.urlopen(req, timeout=timeout):
                    return True
            except Exception:
                continue
        return False

    def login(self, username: str, password: str, isp: str, timeout: float = 8.0) -> None:
        suffix = ISP_ACCOUNT_SUFFIX_MAP.get(isp, "")
        ts = int(time.time() * 1000)
        callback = f"dr{ts}{random.randint(100, 999)}"
        params = {
            "c": "ACSetting",
            "a": "Login",
            "DDDDD": f"{username}{suffix}",
            "upass": password,
            "callback": callback,
            "login_method": "1",
            "wlan_user_ip": self.local_ip(),
            "wlan_user_mac": self.mac(),
            "wlan_ac_ip": "",
            "wlan_ac_name": "",
            "jsVersion": "3.0",
            "_": str(ts),
        }
        url = f"{EPORTAL_LOGIN_URL_BASE}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent}, method="GET")
        with urllib.request.urlopen(req, timeout=timeout):
            pass

    def login_and_verify(self, config: NetworkLoginConfig) -> NetworkLoginResult:
        if not config.has_credentials():
            return NetworkLoginResult(False, "缺少校园网账号或密码。")

        try:
            self.login(config.username.strip(), config.password, config.isp)
            time.sleep(1.5)
            if self.check_connectivity():
                return NetworkLoginResult(True, "校园网登录成功，网络已连通。")
            return NetworkLoginResult(False, "已发送登录请求，但仍未检测到外网连通。")
        except TimeoutError:
            return NetworkLoginResult(False, "登录请求超时。")
        except Exception as exc:
            return NetworkLoginResult(False, f"登录失败: {type(exc).__name__}: {exc}")

    @staticmethod
    def connect_wifi(ssid: str = "CUMT_Stu") -> bool:
        if not ssid.strip():
            return False
        try:
            proc = subprocess.run(
                ["netsh", "wlan", "connect", f"name={ssid.strip()}"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            output = f"{proc.stdout}\n{proc.stderr}".lower()
            return proc.returncode == 0 or "completed successfully" in output or "已成功完成连接请求" in output
        except Exception:
            return False


class NightCutSchedule:
    """校园网夜间断网窗口。

    CUMT 规则：断网发生在"上课日的前一天夜间"，即 [D 23:30, D+1 07:00]
    当且仅当 D+1 需要上课。因此周日到周四夜间断网，周五、周六夜间不断网；
    法定节假日（含调休放假）期间其前一晚不断网，而假期结束后的第一个上课日
    前夜恢复断网。
    """

    DEFAULT_START = dt_time(23, 30)
    DEFAULT_END = dt_time(7, 0)

    def __init__(self, start: str = "23:30", end: str = "07:00") -> None:
        self.start = self.parse(start, self.DEFAULT_START)
        self.end = self.parse(end, self.DEFAULT_END)

    @staticmethod
    def parse(value: str, default: dt_time) -> dt_time:
        try:
            hour, minute = str(value).split(":")
            parsed = dt_time(int(hour), int(minute))
        except Exception:
            return default
        return parsed

    def window_of(self, day: date) -> tuple[datetime, datetime]:
        """返回以 day 为起始日的断网窗口 [day start, day+1 end]。"""
        return datetime.combine(day, self.start), datetime.combine(day + timedelta(days=1), self.end)

    def cuts_on(self, day: date, is_workday: Callable[[date], bool]) -> bool:
        """day 当晚是否会断网（取决于次日是否上课）。"""
        return bool(is_workday(day + timedelta(days=1)))

    def is_cut_at(self, moment: datetime, is_workday: Callable[[date], bool]) -> bool:
        """给定时刻是否处于断网时段内。"""
        current = moment.time()
        if current >= self.start:
            return self.cuts_on(moment.date(), is_workday)
        if current < self.end:
            return self.cuts_on(moment.date() - timedelta(days=1), is_workday)
        return False

    def current_window(self, moment: datetime) -> tuple[datetime, datetime]:
        """包含 moment 的断网窗口（若 moment 在 00:00–end 之间，窗口起始于前一天）。"""
        day = moment.date() if moment.time() >= self.start else moment.date() - timedelta(days=1)
        return self.window_of(day)

    def next_window_start(self, moment: datetime, is_workday: Callable[[date], bool]) -> datetime | None:
        """下一个真正会断网的夜晚的起始时刻。"""
        day = moment.date()
        for offset in range(0, 15):
            candidate = day + timedelta(days=offset)
            start, _ = self.window_of(candidate)
            if start > moment and self.cuts_on(candidate, is_workday):
                return start
        return None


class KeepAlivePolicy:
    """保活重试策略：断网时段不打扰，失败按指数退避重试。"""

    def __init__(self) -> None:
        self.consecutive_failures = 0
        self.next_retry_at = 0.0

    def can_attempt(self, cut_active: bool, now: datetime | None = None) -> tuple[bool, str]:
        current_ts = time.time()
        if cut_active:
            return False, "处于学校安排的夜间断网时段"
        if current_ts < self.next_retry_at:
            return False, f"重试退避中，约 {int(self.next_retry_at - current_ts)} 秒后再试。"
        return True, ""

    def on_success(self) -> None:
        self.consecutive_failures = 0
        self.next_retry_at = 0.0

    def on_failure(self, now: datetime | None = None) -> None:
        self.consecutive_failures += 1
        backoff = min(60, 2 ** min(self.consecutive_failures, 6))
        self.next_retry_at = time.time() + backoff

    @staticmethod
    def _is_night_window(now: datetime) -> bool:
        """固定夜间窗口（不参考节假日），供未启用智能判断时使用。"""
        current_time = now.time()
        return current_time >= NightCutSchedule.DEFAULT_START or current_time < NightCutSchedule.DEFAULT_END
