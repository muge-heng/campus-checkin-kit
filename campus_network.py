import random
import socket
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, time as dt_time
from typing import Any


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
    suspend_on_holiday: bool = True

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


class KeepAlivePolicy:
    NIGHT_RECOVERY_HOUR = 7

    def __init__(self) -> None:
        self.consecutive_failures = 0
        self.next_retry_at = 0.0
        self.night_failures: list[float] = []
        self.night_suspended = False

    def resume_daytime_recovery_if_due(self, now: datetime | None = None) -> bool:
        current_time = now or datetime.now()
        if not self.night_suspended or current_time.hour < self.NIGHT_RECOVERY_HOUR:
            return False
        self.night_suspended = False
        self.night_failures = []
        self.next_retry_at = 0.0
        self.consecutive_failures = 0
        return True

    def can_attempt(self, night_mode: bool, now: datetime | None = None) -> tuple[bool, str]:
        current_time = now or datetime.now()
        now = time.time()
        self.resume_daytime_recovery_if_due(current_time)
        if night_mode:
            if self.night_suspended:
                return False, f"夜间省电暂停中，{self.NIGHT_RECOVERY_HOUR:02d}:00 后自动恢复。"
            if self._is_night_window(current_time):
                self.night_failures = [t for t in self.night_failures if now - t <= 60]
                if len(self.night_failures) >= 3:
                    self.night_suspended = True
                    return False, f"夜间重连失败较多，已暂停到 {self.NIGHT_RECOVERY_HOUR:02d}:00。"

        if now < self.next_retry_at:
            return False, f"重试退避中，约 {int(self.next_retry_at - now)} 秒后再试。"
        return True, ""

    def on_success(self) -> None:
        self.consecutive_failures = 0
        self.next_retry_at = 0.0
        self.night_failures = []

    def on_failure(self, night_mode: bool, now: datetime | None = None) -> None:
        self.consecutive_failures += 1
        backoff = min(60, 2 ** min(self.consecutive_failures, 6))
        self.next_retry_at = time.time() + backoff
        if night_mode and self._is_night_window(now or datetime.now()):
            self.night_failures.append(time.time())

    @staticmethod
    def _is_night_window(now: datetime) -> bool:
        current_time = now.time()
        return current_time >= dt_time(23, 30) or current_time < dt_time(KeepAlivePolicy.NIGHT_RECOVERY_HOUR, 0)
