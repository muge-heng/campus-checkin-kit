import subprocess
import sys
import tempfile
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStyle,
    QSystemTrayIcon,
)

from campus_network import (
    KeepAlivePolicy,
    NetworkLoginConfig,
    NetworkLoginResult,
    NetworkLoginService,
    NightCutSchedule,
)
from holiday_service import HolidayService
from main_window import MainWindow
from network_dialog import NetworkLoginDialog
from notification_manager import NotificationManager
from notification_settings_dialog import NotificationSettingsDialog
from onboarding import OnboardingWizard
from reminder_dialog import ReminderDialog
from settings_store import SettingsStore
from windows_session_monitor import WindowsSessionMonitor

APP_NAME = "CampusCheckinKit"
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "CampusCheckinKit"
FORCE_RETRY_MINUTES = 5
ICON_RELATIVE_PATH = Path("assets") / "today-campus.png"
MAIN_TICK_MS = 30 * 1000
NETWORK_FUTURE_POLL_MS = 400
NETWORK_MONITOR_TICK_MS = 5 * 1000
SESSION_RELOGIN_DEBOUNCE_SECONDS = 10


def resource_path(relative_path: Path) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative_path
    return Path(__file__).resolve().parent / relative_path


class ReminderApp:
    def __init__(self) -> None:
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)

        self.settings = SettingsStore()
        self.holidays = HolidayService(self.settings.cache_dir / "holidays.json")
        self._rebuild_schedule()
        self.next_retry_at: datetime | None = None
        self.dialog: ReminderDialog | None = None
        self.preview_dialog: ReminderDialog | None = None
        self.network_dialog: NetworkLoginDialog | None = None
        self.notification_settings_dialog: NotificationSettingsDialog | None = None
        self.main_window: QMainWindow | None = None
        self.wizard: OnboardingWizard | None = None

        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="campus-kit")
        self.network_service = NetworkLoginService()
        self.keep_alive_policy = KeepAlivePolicy()
        self.night_cut = NightCutSchedule()
        self._cut_active_last: bool | None = None
        self.network_future: Future | None = None
        self.network_future_kind = ""
        self.last_keep_alive_check_at: datetime | None = None
        self.last_session_relogin_at: datetime | None = None
        self.pending_session_relogin = False
        self._last_status_text = ""
        self._last_network_status_text = ""

        self.app_icon = self._app_icon()
        self.qt_app.setWindowIcon(self.app_icon)
        self.session_monitor = WindowsSessionMonitor()
        self.session_monitor.session_restored.connect(self._on_windows_session_restored)

        self.tray_icon = QSystemTrayIcon(self.app_icon, self.qt_app)
        self.tray_menu = QMenu()

        self.notification_manager = NotificationManager(self.tray_icon, self.settings)

        self.status_action = QAction("状态: 运行中")
        self.status_action.setEnabled(False)

        self.network_status_action = QAction("校园网: 未启用")
        self.network_status_action.setEnabled(False)

        self.open_main_action = QAction("打开主菜单")
        self.open_main_action.triggered.connect(self.show_main_window)

        self.preview_action = QAction("预览提醒（调试）")
        self.preview_action.triggered.connect(self.show_preview_reminder)

        self.network_login_action = QAction("校园网立即登录")
        self.network_login_action.triggered.connect(self.login_network_now)

        self.network_check_action = QAction("检测校园网连通")
        self.network_check_action.triggered.connect(self.check_network_now)

        self.network_settings_action = QAction("校园网登录配置")
        self.network_settings_action.triggered.connect(self.open_network_settings)

        self.notification_settings_action = QAction("通知设置")
        self.notification_settings_action.triggered.connect(self.open_notification_settings)

        self.open_settings_action = QAction("打开配置文件")
        self.open_settings_action.triggered.connect(self.open_settings_file)

        self.exit_action = QAction("退出")
        self.exit_action.triggered.connect(self.quit_app)

        self.tray_icon.activated.connect(self._on_tray_activated)

        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)

        self.network_timer = QTimer()
        self.network_timer.timeout.connect(self._network_monitor_tick)

        self._rebuild_tray_menu()
        self.tray_icon.show()

        self._run_onboarding_if_needed()

        self.apply_feature_flags()

        if self.settings.get_bool("start_with_main_window", False):
            QTimer.singleShot(300, self.show_main_window)

        if not self.settings.get_bool("quiet_start", False):
            self.notification_manager.notify_startup(self._startup_message())

        self.tick()
        QTimer.singleShot(1500, self._maybe_auto_login_network)

    # ---------- 启动流程 ----------

    def _app_icon(self) -> QIcon:
        icon_path = resource_path(ICON_RELATIVE_PATH)
        if icon_path.exists():
            icon = QIcon(str(icon_path))
            if not icon.isNull():
                return icon

        style = self.qt_app.style()
        return style.standardIcon(QStyle.SP_ComputerIcon)

    def _startup_message(self) -> str:
        parts = []
        if self.settings.is_reminder_enabled():
            parts.append(f"将在 {self.settings.get_remind_time()} 进行强提醒")
        if self.settings.is_network_enabled():
            parts.append("校园网模块已启用")
        if not parts:
            parts.append("两个功能模块均已关闭，可在主菜单中开启")
        return "程序已启动，" + "，".join(parts) + "。"

    def _run_onboarding_if_needed(self) -> None:
        if self.settings.get_bool("onboarding_completed", False):
            return
        wizard = OnboardingWizard(self.settings, logo_icon=self.app_icon)
        wizard.setWindowIcon(self.app_icon)
        self.wizard = wizard
        wizard.exec()
        open_main = wizard.apply_result(self)
        self.wizard = None
        if open_main:
            QTimer.singleShot(200, self.show_main_window)

    def run(self) -> int:
        return self.qt_app.exec()

    def apply_feature_flags(self) -> None:
        reminder_on = self.settings.is_reminder_enabled()
        network_on = self.settings.is_network_enabled()
        if reminder_on and not self.timer.isActive():
            self.timer.start(MAIN_TICK_MS)
        if not reminder_on:
            self.timer.stop()
        if network_on and not self.network_timer.isActive():
            self.network_timer.start(NETWORK_MONITOR_TICK_MS)
        if not network_on:
            self.network_timer.stop()
        self._rebuild_tray_menu()
        self._refresh_network_actions()

    def _rebuild_tray_menu(self) -> None:
        self.tray_menu.clear()
        self.tray_menu.addAction(self.status_action)
        if self.settings.is_network_enabled():
            self.tray_menu.addAction(self.network_status_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.open_main_action)
        if self.settings.is_reminder_enabled():
            self.tray_menu.addAction(self.preview_action)
        if self.settings.is_network_enabled():
            self.tray_menu.addSeparator()
            self.tray_menu.addAction(self.network_login_action)
            self.tray_menu.addAction(self.network_check_action)
            self.tray_menu.addAction(self.network_settings_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.notification_settings_action)
        self.tray_menu.addAction(self.open_settings_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.exit_action)
        self.tray_icon.setContextMenu(self.tray_menu)

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_main_window()

    # ---------- 主菜单 ----------

    def show_main_window(self) -> None:
        if self.main_window is not None:
            self.main_window.show()
            self.main_window.raise_()
            self.main_window.activateWindow()
            self.main_window.refresh_all()
            return
        window = _TrayAwareWindow(self)
        window.setWindowIcon(self.app_icon)
        self.main_window = window
        window.show()

    # ---------- 提醒 ----------

    def tick(self) -> None:
        if not self.settings.is_reminder_enabled():
            return
        now = datetime.now()
        today = now.date()
        today_iso = today.isoformat()

        reminded_today = self.settings.get_last_reminded_date() == today_iso
        status_text = f"状态: 运行中 | 今日已提醒: {'是' if reminded_today else '否'}"
        if status_text != self._last_status_text:
            self.status_action.setText(status_text)
            self._last_status_text = status_text

        if self.settings.is_paused_on(today):
            self.next_retry_at = None
            return

        if self.settings.get_last_ack_date() == today_iso:
            self.next_retry_at = None
            return

        due_time = self._today_due_datetime(now)

        if self.next_retry_at is not None and now >= self.next_retry_at:
            self.show_reminder_dialog(preview=False)
            return

        if now >= due_time and not reminded_today:
            if self._should_skip_today(today):
                self.settings.set_last_reminded_date(today_iso)
                self.notification_manager.notify_checkin(f"{self.settings.get_remind_time()} 为休息日，今日跳过签到提醒。")
                return
            self.settings.set_last_reminded_date(today_iso)
            self.show_reminder_dialog(preview=False)

    def _should_skip_today(self, today) -> bool:
        if self.settings.is_skip_weekends() and today.weekday() >= 5:
            return True
        if self.settings.is_skip_holidays():
            info = self.holidays.get_day_info(today)
            return info.is_break
        return False

    def _today_due_datetime(self, now: datetime) -> datetime:
        remind_time = self.settings.get_remind_time()
        hour, minute = remind_time.split(":")
        return now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)

    def _reminder_message(self) -> str:
        return f"{self.settings.get_remind_time()} 已开始，请使用手机在今日校园完成查寝签到。"

    def show_reminder_dialog(self, preview: bool) -> None:
        if preview:
            if self.preview_dialog is not None and self.preview_dialog.isVisible():
                self.preview_dialog.raise_()
                self.preview_dialog.activateWindow()
                self._beep()
                return
        else:
            if self.dialog is not None and self.dialog.isVisible():
                self.dialog.raise_()
                self.dialog.activateWindow()
                self._beep()
                return

        self._beep()
        dialog = ReminderDialog(
            on_ack=(self._preview_ack if preview else self.on_ack),
            on_snooze=(self._preview_snooze if preview else self.on_snooze),
            on_add_pause_range=(self._preview_pause_range if preview else self.on_add_pause_range),
            on_force_retry=(self._preview_force_retry if preview else self.on_force_retry),
            preview_mode=preview,
            logo_icon=self.app_icon,
            message=self._reminder_message(),
        )
        dialog.setWindowIcon(self.app_icon)

        if preview:
            self.preview_dialog = dialog
            self.preview_dialog.finished.connect(self._clear_preview_dialog)
            self.preview_dialog.show()
            self.preview_dialog.raise_()
            self.preview_dialog.activateWindow()
            return

        self.dialog = dialog
        self.dialog.finished.connect(self._clear_real_dialog)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def _clear_real_dialog(self) -> None:
        self.dialog = None

    def _clear_preview_dialog(self) -> None:
        self.preview_dialog = None

    def show_preview_reminder(self) -> None:
        self.show_reminder_dialog(preview=True)

    def on_reminder_settings_changed(self) -> None:
        self.next_retry_at = None
        self._refresh_status_labels()

    def on_ack(self) -> None:
        today = datetime.now().date().isoformat()
        self.settings.set_last_ack_date(today)
        self.next_retry_at = None
        self.notification_manager.notify_checkin("今日已确认签到，不再提醒。")
        self._refresh_status_labels()

    def on_snooze(self) -> None:
        minutes = self.settings.get_snooze_minutes()
        self.next_retry_at = datetime.now() + timedelta(minutes=minutes)
        self.notification_manager.notify_checkin(f"已稍后提醒，{minutes} 分钟后再次提醒。")

    def on_force_retry(self) -> None:
        self.next_retry_at = datetime.now() + timedelta(minutes=FORCE_RETRY_MINUTES)

    def on_add_pause_range(self, start, end) -> None:
        self.settings.add_pause_range(start, end)
        today = datetime.now().date()
        if start <= today <= end:
            self.next_retry_at = None
            self.notification_manager.notify_checkin("当前日期位于暂停区间，今日不再提醒。")

    def _preview_ack(self) -> None:
        self.notification_manager.notify_debug("预览模式：不会修改真实签到状态。")

    def _preview_snooze(self) -> None:
        self.notification_manager.notify_debug("预览模式：不会写入稍后提醒状态。")

    def _preview_pause_range(self, start, end) -> None:
        self.notification_manager.notify_debug("预览模式：不会保存暂停区间。")

    def _preview_force_retry(self) -> None:
        pass

    # ---------- 校园网 ----------

    def _network_config(self) -> NetworkLoginConfig:
        return NetworkLoginConfig(**self.settings.get_network_login_config())

    def network_status_summary(self) -> str:
        cfg = self._network_config()
        if not self.settings.is_network_enabled():
            return "模块已关闭"
        if not cfg.enabled:
            return "未启用自动登录"
        keep_alive = "保活开启" if cfg.keep_alive else "保活关闭"
        cut = "当前处于断网时段" if self._night_cut_active(datetime.now(), cfg) else self.tonight_cut_text()
        return f"{self.settings.get_last_network_login_status()} | {keep_alive} | {cut}"

    def _refresh_network_actions(self) -> None:
        cfg = self._network_config()
        if not self.settings.is_network_enabled():
            text = "校园网: 模块已关闭"
        elif not cfg.enabled:
            text = "校园网: 未启用"
        else:
            keep_alive = " | 保活开启" if cfg.keep_alive else ""
            interval = f" | {cfg.probe_interval_seconds} 秒巡检" if cfg.keep_alive else ""
            text = f"校园网: {self.settings.get_last_network_login_status()}{keep_alive}{interval}"
        if text != self._last_network_status_text:
            self.network_status_action.setText(text)
            self._last_network_status_text = text
        enabled = cfg.enabled and self.network_future is None
        self.network_login_action.setEnabled(enabled)
        self.network_check_action.setEnabled(self.network_future is None)

    def _refresh_status_labels(self) -> None:
        self._refresh_network_actions()
        if self.main_window is not None and self.main_window.isVisible():
            self.main_window.refresh_all()

    def open_network_settings(self) -> None:
        if self.network_dialog is not None and self.network_dialog.isVisible():
            self.network_dialog.raise_()
            self.network_dialog.activateWindow()
            return

        dialog = NetworkLoginDialog(self._network_config(), holiday_label="今晚断网预判：" + self.tonight_cut_text())
        dialog.setWindowIcon(self.app_icon)
        dialog.accepted.connect(lambda: self._save_network_dialog(dialog))
        dialog.login_button.clicked.connect(lambda _checked=False: self._run_network_from_dialog(dialog, "login"))
        dialog.check_button.clicked.connect(lambda _checked=False: self._run_network_from_dialog(dialog, "check"))
        dialog.finished.connect(self._clear_network_dialog)
        self.network_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _clear_network_dialog(self) -> None:
        self.network_dialog = None

    def open_notification_settings(self) -> None:
        if self.notification_settings_dialog is not None and self.notification_settings_dialog.isVisible():
            self.notification_settings_dialog.raise_()
            self.notification_settings_dialog.activateWindow()
            return

        dialog = NotificationSettingsDialog(self.settings)
        dialog.setWindowIcon(self.app_icon)
        dialog.finished.connect(self._clear_notification_settings_dialog)
        self.notification_settings_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _clear_notification_settings_dialog(self) -> None:
        self.notification_settings_dialog = None

    def _save_network_dialog(self, dialog: NetworkLoginDialog) -> None:
        cfg = dialog.get_config()
        self.settings.set_network_login_config(cfg.__dict__)
        self._rebuild_schedule()
        self.last_keep_alive_check_at = None
        self._refresh_network_actions()
        self.notification_manager.notify_network("校园网登录", "校园网登录配置已保存。", success=True)

    def _run_network_from_dialog(self, dialog: NetworkLoginDialog, kind: str) -> None:
        cfg = dialog.get_config()
        self.settings.set_network_login_config(cfg.__dict__)
        dialog.set_busy(True, "正在登录..." if kind == "login" else "正在检测网络...")
        started = self._start_network_task("manual-login" if kind == "login" else "manual-check", cfg)
        if not started:
            dialog.set_busy(False, "任务未启动，请检查配置。")

    def login_network_now(self) -> None:
        self._start_network_task("manual-login", self._network_config())

    def check_network_now(self) -> None:
        self._start_network_task("manual-check", self._network_config())

    def request_network_task(self, kind: str) -> None:
        """主菜单窗口触发网络任务。"""
        self._start_network_task(kind, self._network_config())

    def on_network_config_saved(self) -> None:
        self._rebuild_schedule()
        self.last_keep_alive_check_at = None
        self._refresh_status_labels()

    def _maybe_auto_login_network(self) -> None:
        if not self.settings.is_network_enabled():
            return
        cfg = self._network_config()
        if cfg.enabled and cfg.auto_login and cfg.has_credentials():
            now = datetime.now()
            if self._night_cut_active(now, cfg):
                self.notification_manager.notify_network(
                    "校园网保活", "当前处于学校安排的夜间断网时段，跳过自动登录；可在主菜单手动登录。", success=True
                )
                return
            self._start_network_task("auto-login", cfg)

    def _network_monitor_tick(self) -> None:
        if not self.settings.is_network_enabled():
            return
        self.session_monitor.poll_for_activity_resume()
        now = datetime.now()
        cfg = self._network_config()
        cut = self._night_cut_active(now, cfg)
        if self._cut_active_last is not None and cut != self._cut_active_last:
            self.last_keep_alive_check_at = None
            if cut:
                start, end = self.night_cut.current_window(now)
                self.notification_manager.notify_network(
                    "校园网保活",
                    f"进入学校安排的夜间断网时段（{start:%H:%M} 至次日 {end:%H:%M}），保活暂停。",
                    success=True,
                )
            else:
                self.keep_alive_policy.on_success()
                self.notification_manager.notify_network("校园网保活", "断网时段结束，恢复网络巡检。", success=True)
        self._cut_active_last = cut
        self._tick_network_keep_alive(now)

    def _night_cut_active(self, now: datetime, cfg: NetworkLoginConfig) -> bool:
        if cfg.smart_night_cut:
            return self.night_cut.is_cut_at(now, self.holidays.is_workday)
        return bool(cfg.night_mode and KeepAlivePolicy._is_night_window(now))

    def _rebuild_schedule(self) -> None:
        cfg = self.settings.get_network_login_config()
        self.night_cut = NightCutSchedule(
            str(cfg.get("cut_start_time", "23:30")), str(cfg.get("cut_end_time", "07:00"))
        )

    def tonight_cut_text(self) -> str:
        """今晚是否会断网的说明，供主菜单展示。"""
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        if not self.night_cut.cuts_on(today, self.holidays.is_workday):
            return f"今晚不断网（明日 {tomorrow:%m-%d} {self.holidays.workday_label(tomorrow)}），保活全天可用。"
        start, end = self.night_cut.window_of(today)
        return (
            f"今晚 {start:%H:%M} 至次日 {end:%H:%M} 按学校安排断网"
            f"（明日 {tomorrow:%m-%d} {self.holidays.workday_label(tomorrow)}），该时段保活自动暂停。"
        )

    def _on_windows_session_restored(self, source: str) -> None:
        if not self.settings.is_network_enabled():
            return
        now = datetime.now()
        if self.last_session_relogin_at and (now - self.last_session_relogin_at).total_seconds() < SESSION_RELOGIN_DEBOUNCE_SECONDS:
            return
        self.last_session_relogin_at = now

        cfg = self._network_config()
        if not cfg.enabled or not cfg.has_credentials():
            return
        if self._night_cut_active(now, cfg):
            return
        if self.network_future is not None:
            self.pending_session_relogin = True
            return

        self.keep_alive_policy.next_retry_at = 0.0
        self.last_keep_alive_check_at = now
        QTimer.singleShot(1200, lambda: self._start_session_relogin(source))

    def _start_session_relogin(self, source: str) -> None:
        cfg = self._network_config()
        if not cfg.enabled or not cfg.has_credentials():
            return
        if self.network_future is not None:
            self.pending_session_relogin = True
            return
        self.pending_session_relogin = False
        self._start_network_task("session-resume", cfg)

    def _start_network_task(self, kind: str, cfg: NetworkLoginConfig) -> bool:
        if not self.settings.is_network_enabled():
            QMessageBox.information(None, "校园网", "“CUMT 校园网”模块当前已关闭，请先在主菜单总览页启用。")
            return False
        if self.network_future is not None:
            return False
        if kind in {"manual-login", "auto-login", "session-resume"} and (not cfg.enabled or not cfg.has_credentials()):
            QMessageBox.warning(None, "校园网登录", "请先启用校园网登录功能并填写账号密码。")
            return False

        self.network_future_kind = kind
        if kind.endswith("check"):
            self.network_future = self.executor.submit(self._check_network_worker)
        else:
            self.network_future = self.executor.submit(self._login_network_worker, cfg)
        self._refresh_network_actions()
        QTimer.singleShot(NETWORK_FUTURE_POLL_MS, self._poll_network_future)
        return True

    def _check_network_worker(self) -> NetworkLoginResult:
        ok = self.network_service.check_connectivity()
        return NetworkLoginResult(ok, "网络已连通。" if ok else "未检测到外网连通。")

    def _login_network_worker(self, cfg: NetworkLoginConfig) -> NetworkLoginResult:
        return self.network_service.login_and_verify(cfg)

    def _poll_network_future(self) -> None:
        if self.network_future is None:
            return
        if not self.network_future.done():
            QTimer.singleShot(NETWORK_FUTURE_POLL_MS, self._poll_network_future)
            return

        future = self.network_future
        kind = self.network_future_kind
        self.network_future = None
        self.network_future_kind = ""
        try:
            result = future.result()
        except Exception as exc:
            result = NetworkLoginResult(False, f"校园网任务异常: {exc}")

        if kind.endswith("login") or kind in {"keep-alive", "session-resume"}:
            self.settings.set_last_network_login_result(result.ok, result.message)
            if result.ok:
                self.keep_alive_policy.on_success()
            else:
                self.keep_alive_policy.on_failure(datetime.now())

        self._refresh_status_labels()

        if self.network_dialog is not None and self.network_dialog.isVisible():
            self.network_dialog.set_busy(False, result.message)

        title = "校园网登录" if kind.endswith("login") or kind in {"keep-alive", "session-resume"} else "校园网检测"
        should_notify = True
        if kind == "keep-alive" and result.ok and result.message == "网络连接正常。":
            should_notify = False
        if should_notify:
            self.notification_manager.notify_network(title, result.message, success=result.ok)
        if kind.startswith("manual") and not result.ok:
            QMessageBox.warning(None, title, result.message)
        if self.pending_session_relogin and self.network_future is None:
            self.pending_session_relogin = False
            QTimer.singleShot(1200, lambda: self._start_session_relogin("回到桌面后"))

    def _tick_network_keep_alive(self, now: datetime) -> None:
        cfg = self._network_config()
        if not cfg.enabled or not cfg.keep_alive or self.network_future is not None:
            return
        if self.last_keep_alive_check_at and (now - self.last_keep_alive_check_at).total_seconds() < cfg.probe_interval_seconds:
            return
        self.last_keep_alive_check_at = now

        cut_active = self._night_cut_active(now, cfg)
        can_attempt, reason = self.keep_alive_policy.can_attempt(cut_active, now)
        if not can_attempt:
            if reason:
                text = f"校园网: {reason}"
                if text != self._last_network_status_text:
                    self.network_status_action.setText(text)
                    self._last_network_status_text = text
            return

        self.network_future_kind = "keep-alive"
        self.network_future = self.executor.submit(self._keep_alive_worker, cfg)
        self._refresh_network_actions()
        QTimer.singleShot(NETWORK_FUTURE_POLL_MS, self._poll_network_future)

    def _keep_alive_worker(self, cfg: NetworkLoginConfig) -> NetworkLoginResult:
        if self.network_service.check_connectivity():
            return NetworkLoginResult(True, "网络连接正常。")
        if cfg.auto_wifi:
            wifi_ok = self.network_service.connect_wifi(cfg.wifi_ssid)
            if not wifi_ok:
                return NetworkLoginResult(False, f"Wi-Fi {cfg.wifi_ssid} 连接失败。")
            import time

            time.sleep(2.0)
        return self.network_service.login_and_verify(cfg)

    def _beep(self) -> None:
        try:
            import winsound

            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            QApplication.beep()

    # ---------- 开机自启 / 快捷方式 ----------

    def _startup_command(self) -> str:
        if getattr(sys, "frozen", False):
            return f'"{Path(sys.executable)}"'

        pythonw = Path(sys.executable)
        script = Path(__file__).resolve()
        return f'"{pythonw}" "{script}"'

    def _exe_path(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable)
        return Path(__file__).resolve()

    def get_autostart_registry_value(self) -> str:
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, RUN_VALUE_NAME)
            return str(value)
        except OSError:
            return ""

    def is_startup_enabled(self) -> bool:
        return bool(self.get_autostart_registry_value())

    def autostart_status(self) -> tuple[bool, bool]:
        """(是否已设置自启, 是否指向当前程序)"""
        value = self.get_autostart_registry_value()
        if not value:
            return False, False
        return True, value.strip('"').lower() == self._startup_command().strip('"').lower()

    def set_startup(self, enabled: bool) -> bool:
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                if enabled:
                    winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, self._startup_command())
                else:
                    try:
                        winreg.DeleteValue(key, RUN_VALUE_NAME)
                    except FileNotFoundError:
                        pass
            self.settings.set_bool("autostart_user_enabled", enabled)
            return True
        except OSError:
            return False

    def create_desktop_shortcut(self) -> tuple[bool, str]:
        target = self._exe_path()
        if getattr(sys, "frozen", False):
            cmd_target = str(target)
            arguments = ""
            working = str(target.parent)
        else:
            cmd_target = str(Path(sys.executable).with_name("pythonw.exe"))
            if not Path(cmd_target).exists():
                cmd_target = sys.executable
            arguments = f'"{target}"'
            working = str(target.parent)

        desktop = Path.home() / "Desktop"
        lnk_path = desktop / "校园提醒与校园网助手.lnk"
        ps = (
            "$ws = New-Object -ComObject WScript.Shell; "
            f"$sc = $ws.CreateShortcut('{str(lnk_path).replace(chr(39), chr(39) * 2)}'); "
            f"$sc.TargetPath = '{cmd_target.replace(chr(39), chr(39) * 2)}'; "
            f"$sc.Arguments = '{arguments.replace(chr(39), chr(39) * 2)}'; "
            f"$sc.WorkingDirectory = '{working.replace(chr(39), chr(39) * 2)}'; "
            "$sc.Description = '校园提醒与校园网助手'; "
            f"$sc.IconLocation = '{str(resource_path(ICON_RELATIVE_PATH)).replace(chr(39), chr(39) * 2)}'; "
            "$sc.Save()"
        )
        try:
            tmp = Path(tempfile.mkstemp(suffix=".ps1")[1])
            tmp.write_text(ps, encoding="utf-8")
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(tmp)],
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            tmp.unlink(missing_ok=True)
            if proc.returncode == 0 and lnk_path.exists():
                return True, f"快捷方式已创建：{lnk_path}"
            return False, f"创建失败：{proc.stderr.strip() or proc.stdout.strip() or '请检查桌面路径权限'}"
        except Exception as exc:
            return False, f"创建失败：{exc}"

    # ---------- 其他 ----------

    def open_settings_file(self) -> None:
        settings_path = self.settings.settings_path
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        if not settings_path.exists():
            self.settings.save()

        subprocess.Popen(["notepad.exe", str(settings_path)])

    def quit_app(self) -> None:
        self.timer.stop()
        self.network_timer.stop()
        self.session_monitor.close()
        self.tray_icon.hide()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.qt_app.quit()


class _TrayAwareWindow(QMainWindow):
    """主菜单窗口：关闭时按设置回到托盘，而不是退出程序。"""

    def __init__(self, ctx: ReminderApp) -> None:
        super().__init__()
        self.ctx = ctx
        self.setCentralWidget(MainWindow(ctx))

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()
        self.ctx.notification_manager.notify_debug("已返回系统托盘，程序继续驻留后台。")


if __name__ == "__main__":
    app = ReminderApp()
    sys.exit(app.run())
