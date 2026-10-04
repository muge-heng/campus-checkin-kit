"""主菜单窗口：集中查看状态、开关功能模块、各类设置与关于信息。"""

import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QTime, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QFrame,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from campus_network import ISP_DISPLAY_LIST, NetworkLoginConfig
from holiday_service import HolidayService
from settings_store import SettingsStore

APP_VERSION = "1.0.0"
GITHUB_URL = "https://github.com/muge-heng/campus-checkin-kit"


class MainWindow(QWidget):
    """通过 context（duck-typed 的 ReminderApp）读写状态并触发动作。"""

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        self.settings: SettingsStore = ctx.settings
        self.holidays: HolidayService = ctx.holidays
        self.setWindowTitle("校园提醒与校园网助手 · 主菜单")
        self.setWindowIcon(ctx.app_icon)
        self.resize(720, 560)
        self._build_ui()
        self.refresh_all()

    # ---------- UI ----------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)

        header = QLabel("校园提醒与校园网助手")
        header.setStyleSheet("font-size: 20px; font-weight: 700; color: #14231c;")
        sub = QLabel("今日校园强提醒 + CUMT 校园网自动登录保活，可按需模块化启用。")
        sub.setStyleSheet("font-size: 12px; color: #667; ")
        root.addWidget(header)
        root.addWidget(sub)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._home_tab(), "总览")
        self.tabs.addTab(self._reminder_tab(), "提醒设置")
        self.tabs.addTab(self._network_tab(), "校园网")
        self.tabs.addTab(self._startup_tab(), "启动与快捷方式")
        self.tabs.addTab(self._notification_tab(), "通知")
        self.tabs.addTab(self._holiday_tab(), "节假日")
        self.tabs.addTab(self._about_tab(), "关于")
        root.addWidget(self.tabs, 1)

        bottom = QHBoxLayout()
        open_cfg = QPushButton("打开配置文件")
        open_cfg.clicked.connect(self.ctx.open_settings_file)
        open_dir = QPushButton("打开配置目录")
        open_dir.clicked.connect(self._open_config_dir)
        restart = QPushButton("重置首次引导")
        restart.setToolTip("下次启动时重新显示首次启动引导。")
        restart.clicked.connect(self._reset_onboarding)
        quit_btn = QPushButton("退出程序")
        quit_btn.clicked.connect(self.ctx.quit_app)
        bottom.addWidget(open_cfg)
        bottom.addWidget(open_dir)
        bottom.addWidget(restart)
        bottom.addStretch()
        bottom.addWidget(quit_btn)
        root.addLayout(bottom)

    @staticmethod
    def _group(title: str) -> tuple[QGroupBox, QVBoxLayout]:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.setSpacing(8)
        return box, layout

    def _note(self, text: str, object_name: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName(object_name)
        frame.setStyleSheet(
            f"QFrame#{object_name} {{ background: #f6f1e7; border: 1px solid #e2d5b8; border-radius: 6px; }}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 9, 12, 9)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("font-size: 12px; color: #6b5a35; background: transparent; border: none;")
        layout.addWidget(label)
        return frame

    # ---------- 总览 ----------

    def _home_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        box, box_layout = self._group("功能模块（勾选即时生效，可随时切换）")
        self.reminder_switch = QCheckBox("今日校园查寝强提醒")
        self.reminder_switch.toggled.connect(self._on_reminder_switch)
        self.network_switch = QCheckBox("CUMT 校园网自动登录与保活")
        self.network_switch.toggled.connect(self._on_network_switch)
        box_layout.addWidget(self.reminder_switch)
        box_layout.addWidget(self.network_switch)
        box_layout.addWidget(QLabel("只想用其中一个功能？取消勾选另一个即可，程序只会运行启用的模块。"))
        layout.addWidget(box)

        status_box, status_layout = self._group("当前状态")
        self.status_reminder = QLabel("提醒：-")
        self.status_network = QLabel("校园网：-")
        self.status_autostart = QLabel("开机自启：-")
        self.status_holiday = QLabel("今天：-")
        for label in (self.status_reminder, self.status_network, self.status_autostart, self.status_holiday):
            label.setStyleSheet("font-size: 13px; color: #333;")
            status_layout.addWidget(label)
        layout.addWidget(status_box)

        self.start_main_window_box = QCheckBox("每次启动时自动打开本主菜单（取消则静默启动到托盘）")
        self.start_main_window_box.setChecked(self.settings.get_bool("start_with_main_window", False))
        self.start_main_window_box.toggled.connect(
            lambda v: self.settings.set_bool("start_with_main_window", v)
        )
        layout.addWidget(self.start_main_window_box)
        layout.addStretch()
        return page

    def _on_reminder_switch(self, checked: bool) -> None:
        self.settings.set_bool("enable_reminder", checked)
        self.ctx.apply_feature_flags()
        if not checked and not self.settings.is_network_enabled():
            QMessageBox.information(
                self, "提示", "两个模块都已关闭：程序将静默驻留托盘，不会有任何提醒或网络动作。\n"
                "可随时从托盘“打开主菜单”重新开启。"
            )

    def _on_network_switch(self, checked: bool) -> None:
        self.settings.set_bool("enable_network", checked)
        self.ctx.apply_feature_flags()
        if not checked and not self.settings.is_reminder_enabled():
            QMessageBox.information(
                self, "提示", "两个模块都已关闭：程序将静默驻留托盘，不会有任何提醒或网络动作。\n"
                "可随时从托盘“打开主菜单”重新开启。"
            )

    # ---------- 提醒设置 ----------

    def _reminder_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        box, box_layout = self._group("提醒时间（适配所有学校的查寝/签到时间）")
        form = QFormLayout()
        self.remind_time_edit = QDateTimeEdit()
        self.remind_time_edit.setDisplayFormat("HH:mm")
        self.remind_time_edit.setTimeSpec(Qt.TimeSpec.LocalTime)
        self.remind_time_edit.setCalendarPopup(False)
        form.addRow("每日提醒时间", self.remind_time_edit)
        self.snooze_spin = QSpinBox()
        self.snooze_spin.setRange(1, 120)
        self.snooze_spin.setSuffix(" 分钟")
        form.addRow("稍后提醒间隔", self.snooze_spin)
        box_layout.addLayout(form)
        save = QPushButton("保存提醒设置")
        save.clicked.connect(self._save_reminder_settings)
        box_layout.addWidget(save)
        layout.addWidget(box)

        hb, hl = self._group("智能跳过")
        self.skip_holiday_box = QCheckBox("法定节假日当天自动跳过提醒（联网自动拉取，含调休）")
        self.skip_holiday_box.setChecked(self.settings.is_skip_holidays())
        self.skip_holiday_box.toggled.connect(lambda v: self.settings.set_bool("skip_holidays", v))
        self.skip_weekend_box = QCheckBox("周末跳过提醒")
        self.skip_weekend_box.setChecked(self.settings.is_skip_weekends())
        self.skip_weekend_box.toggled.connect(lambda v: self.settings.set_bool("skip_weekends", v))
        hl.addWidget(self.skip_holiday_box)
        hl.addWidget(self.skip_weekend_box)
        hl.addWidget(self._note(
            "寒暑假、外出实习等无固定规律的日子，可在下方添加暂停日期区间；"
            "非 CUMT 的同学也完全可以只使用强提醒功能，只需把提醒时间改成贵校的签到时间。",
            "reminderNote",
        ))
        layout.addWidget(hb)

        pb, pl = self._group("暂停区间（寒暑假等）")
        self.pause_list = QListWidget()
        self.pause_list.setMinimumHeight(90)
        pl.addWidget(self.pause_list)
        row = QHBoxLayout()
        add_btn = QPushButton("添加区间")
        add_btn.clicked.connect(self._add_pause_range)
        del_btn = QPushButton("删除选中")
        del_btn.clicked.connect(self._remove_pause_range)
        row.addWidget(add_btn)
        row.addWidget(del_btn)
        row.addStretch()
        pl.addLayout(row)
        layout.addWidget(pb)

        preview = QPushButton("预览强提醒弹窗（不修改真实状态）")
        preview.clicked.connect(lambda _=False: self.ctx.show_preview_reminder())
        layout.addWidget(preview)
        layout.addStretch()
        return page

    def _save_reminder_settings(self) -> None:
        self.settings.set_remind_time(self.remind_time_edit.time().toString("HH:mm"))
        self.settings.set_snooze_minutes(self.snooze_spin.value())
        self.ctx.on_reminder_settings_changed()
        QMessageBox.information(self, "已保存", f"提醒时间：{self.settings.get_remind_time()}，"
                                f"稍后提醒 {self.settings.get_snooze_minutes()} 分钟。")

    def _add_pause_range(self) -> None:
        from reminder_dialog import PauseRangeDialog

        dialog = PauseRangeDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        start, end = dialog.get_date_range()
        if end < start:
            QMessageBox.warning(self, "日期错误", "结束日期不能早于开始日期。")
            return
        self.settings.add_pause_range(start, end)
        self._reload_pause_ranges()

    def _remove_pause_range(self) -> None:
        item = self.pause_list.currentItem()
        if item is None:
            QMessageBox.information(self, "提示", "请先在列表中选择要删除的区间。")
            return
        ranges = list(self.settings.get_pause_ranges())
        index = self.pause_list.currentRow()
        ranges.pop(index)
        self.settings.set_pause_ranges(
            [{"start": r.start.isoformat(), "end": r.end.isoformat()} for r in ranges]
        )
        self._reload_pause_ranges()

    def _reload_pause_ranges(self) -> None:
        self.pause_list.clear()
        for r in self.settings.get_pause_ranges():
            self.pause_list.addItem(f"{r.start.isoformat()} ~ {r.end.isoformat()}")

    # ---------- 校园网 ----------

    def _network_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        box, box_layout = self._group("校园网登录配置")
        form = QFormLayout()
        self.net_enabled_box = QCheckBox("在“校园网”模块启用的前提下，实际执行自动登录/保活")
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("学号/账号")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("校园网密码")
        self.isp_combo = QComboBox()
        self.isp_combo.addItems(ISP_DISPLAY_LIST)
        self.wifi_edit = QLineEdit()
        form.addRow("", self.net_enabled_box)
        form.addRow("账号", self.username_edit)
        form.addRow("密码", self.password_edit)
        form.addRow("运营商", self.isp_combo)
        form.addRow("Wi-Fi 名称", self.wifi_edit)

        self.auto_login_box = QCheckBox("程序启动后自动尝试登录")
        self.keep_alive_box = QCheckBox("断网后自动检测并重连")
        self.auto_wifi_box = QCheckBox("重连前先尝试连接指定 Wi-Fi")
        self.night_mode_box = QCheckBox("夜间失败过多时暂停重连（防重试风暴）")
        self.smart_cut_box = QCheckBox("智能判断夜间断网：明日上课则今晚的断网时段暂停保活")
        for box_widget in (self.auto_login_box, self.keep_alive_box, self.auto_wifi_box,
                           self.night_mode_box, self.smart_cut_box):
            form.addRow("", box_widget)

        cut_row = QHBoxLayout()
        self.cut_start_edit = QTimeEdit()
        self.cut_start_edit.setDisplayFormat("HH:mm")
        self.cut_end_edit = QTimeEdit()
        self.cut_end_edit.setDisplayFormat("HH:mm")
        cut_row.addWidget(QLabel("断网开始"))
        cut_row.addWidget(self.cut_start_edit)
        cut_row.addWidget(QLabel("恢复时刻"))
        cut_row.addWidget(self.cut_end_edit)
        cut_row.addStretch()
        form.addRow("断网时段", cut_row)
        self.tonight_label = QLabel("今晚断网预判：-")
        self.tonight_label.setWordWrap(True)
        self.tonight_label.setStyleSheet("font-size: 12px; color: #17663e;")
        form.addRow("", self.tonight_label)

        self.probe_spin = QSpinBox()
        self.probe_spin.setRange(10, 60)
        self.probe_spin.setSuffix(" 秒")
        form.addRow("巡检间隔", self.probe_spin)
        box_layout.addLayout(form)

        self.network_status_label = QLabel("状态：-")
        self.network_status_label.setWordWrap(True)
        self.network_status_label.setStyleSheet("font-size: 12px; color: #555;")
        box_layout.addWidget(self.network_status_label)

        row = QHBoxLayout()
        save = QPushButton("保存配置")
        save.clicked.connect(self._save_network_config)
        self.login_btn = QPushButton("立即登录")
        self.login_btn.clicked.connect(lambda _=False: self.ctx.request_network_task("manual-login"))
        self.check_btn = QPushButton("检测网络")
        self.check_btn.clicked.connect(lambda _=False: self.ctx.request_network_task("manual-check"))
        row.addWidget(save)
        row.addWidget(self.login_btn)
        row.addWidget(self.check_btn)
        row.addStretch()
        box_layout.addLayout(row)
        layout.addWidget(box)

        layout.addWidget(self._note(
            "夜间断网规则：CUMT 在上课日的前一夜断网（默认 23:30 至次日 07:00），"
            "因此周日到周四夜间会断、周五周六夜间不断；法定节假日与寒暑假期间其前一夜不断网，"
            "假期结束后的第一个上课日前夜恢复断网。程序据此只在真会断网的时段暂停保活，其余时间照常守护。",
            "netNote",
        ))
        layout.addWidget(self._note(
            "登录门户默认对接 CUMT ePortal（http://10.2.5.251:801/eportal/）。"
            "其他学校如需使用自动登录，可在 campus_network.py 中修改 EPORTAL_LOGIN_URL_BASE 与参数，"
            "并在此处填上贵校自己的断网时段；提醒功能则完全通用。",
            "netNote2",
        ))
        layout.addStretch()
        return page

    def _save_network_config(self) -> None:
        cfg = NetworkLoginConfig(
            enabled=self.net_enabled_box.isChecked(),
            username=self.username_edit.text().strip(),
            password=self.password_edit.text(),
            isp=self.isp_combo.currentText(),
            auto_login=self.auto_login_box.isChecked(),
            keep_alive=self.keep_alive_box.isChecked(),
            auto_wifi=self.auto_wifi_box.isChecked(),
            wifi_ssid=self.wifi_edit.text().strip() or "CUMT_Stu",
            night_mode=self.night_mode_box.isChecked(),
            probe_interval_seconds=self.probe_spin.value(),
            smart_night_cut=self.smart_cut_box.isChecked(),
            cut_start_time=self.cut_start_edit.time().toString("HH:mm"),
            cut_end_time=self.cut_end_edit.time().toString("HH:mm"),
        )
        self.settings.set_network_login_config(cfg.__dict__)
        self.ctx.on_network_config_saved()
        QMessageBox.information(self, "已保存", "校园网配置已保存并生效。")

    # ---------- 启动与快捷方式 ----------

    def _startup_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        box, box_layout = self._group("开机自启")
        self.autostart_box = QCheckBox("登录 Windows 后自动启动本程序")
        self.autostart_box.toggled.connect(self._toggle_autostart)
        box_layout.addWidget(self.autostart_box)
        self.autostart_detail = QLabel("状态：检测中…")
        self.autostart_detail.setWordWrap(True)
        self.autostart_detail.setStyleSheet("font-size: 12px; color: #555;")
        box_layout.addWidget(self.autostart_detail)
        row = QHBoxLayout()
        check_btn = QPushButton("立即检测自启状态")
        check_btn.clicked.connect(self._check_autostart)
        fix_btn = QPushButton("重新写入自启项")
        fix_btn.clicked.connect(self._fix_autostart)
        row.addWidget(check_btn)
        row.addWidget(fix_btn)
        row.addStretch()
        box_layout.addLayout(row)
        box_layout.addWidget(self._note(
            "手动引导：若自动写入失败，可按下 Win+R，输入 regedit 打开\n"
            "HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run，\n"
            "新建字符串值 CampusCheckinKit，数据为本程序 exe 的完整路径；\n"
            "或在任务管理器的“启动”页确认本程序已启用。",
            "startupNote",
        ))
        layout.addWidget(box)

        sb, sl = self._group("桌面快捷方式")
        srow = QHBoxLayout()
        self.shortcut_btn = QPushButton("发送快捷方式到桌面")
        self.shortcut_btn.clicked.connect(self._create_desktop_shortcut)
        self.shortcut_result = QLabel("尚未创建。")
        self.shortcut_result.setWordWrap(True)
        self.shortcut_result.setStyleSheet("font-size: 12px; color: #555;")
        srow.addWidget(self.shortcut_btn)
        srow.addWidget(self.shortcut_result, 1)
        sl.addLayout(srow)
        layout.addWidget(sb)
        layout.addStretch()
        return page

    def _toggle_autostart(self, checked: bool) -> None:
        ok = self.ctx.set_startup(checked)
        if not ok:
            QMessageBox.warning(self, "开机自启", "设置失败，请参考下方手动引导，或以普通用户权限重试。")
        self._check_autostart()

    def _check_autostart(self) -> None:
        enabled, matches = self.ctx.autostart_status()
        if enabled and matches:
            self.autostart_detail.setText("状态：已正确设置，指向当前程序。")
            self.autostart_box.setChecked(True)
        elif enabled:
            self.autostart_detail.setText(
                "状态：注册表里有自启项，但指向的不是当前程序（可能来自旧版本）。\n"
                "点击“重新写入自启项”修正。"
            )
            self.autostart_box.setChecked(True)
        else:
            self.autostart_detail.setText("状态：未设置开机自启。勾选上方复选框或点击“重新写入自启项”。")
            self.autostart_box.setChecked(False)

    def _fix_autostart(self) -> None:
        if self.ctx.set_startup(True):
            self.ctx.settings.set_bool("autostart_user_enabled", True)
        self._check_autostart()

    def _create_desktop_shortcut(self) -> None:
        ok, message = self.ctx.create_desktop_shortcut()
        self.shortcut_result.setText(message)
        if not ok:
            QMessageBox.warning(self, "快捷方式", message)

    # ---------- 通知 ----------

    def _notification_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        box, box_layout = self._group("各类通知的呈现方式（签到强提醒弹窗不受影响）")
        form = QFormLayout()
        self.notify_combos: dict[str, QComboBox] = {}
        from notification_settings_dialog import NOTIFICATION_CATEGORIES, NOTIFICATION_TYPE_OPTIONS

        for category, (name, description) in NOTIFICATION_CATEGORIES.items():
            combo = QComboBox()
            for type_value, type_name, _desc in NOTIFICATION_TYPE_OPTIONS:
                combo.addItem(type_name, type_value)
            form.addRow(f"{name}（{description}）", combo)
            self.notify_combos[category] = combo
        box_layout.addLayout(form)
        save = QPushButton("保存通知设置")
        save.clicked.connect(self._save_notifications)
        box_layout.addWidget(save)
        layout.addWidget(box)

        self.quiet_box = QCheckBox("静默启动（启动时不发送“程序已启动”通知）")
        self.quiet_box.setChecked(self.settings.get_bool("quiet_start", False))
        self.quiet_box.toggled.connect(lambda v: self.settings.set_bool("quiet_start", v))
        layout.addWidget(self.quiet_box)
        layout.addStretch()
        return page

    def _save_notifications(self) -> None:
        config = {category: combo.currentData() for category, combo in self.notify_combos.items()}
        self.settings.set_notification_config(config)
        QMessageBox.information(self, "已保存", "通知设置已保存。")

    # ---------- 节假日 ----------

    def _holiday_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        box, box_layout = self._group("法定节假日数据")
        self.holiday_today = QLabel("今天：-")
        self.holiday_tomorrow = QLabel("明天：-")
        self.holiday_cut = QLabel("今晚断网预判：-")
        self.holiday_status = QLabel("-")
        for widget in (self.holiday_today, self.holiday_tomorrow, self.holiday_cut):
            widget.setStyleSheet("font-size: 14px; font-weight: 600;")
        self.holiday_status.setWordWrap(True)
        self.holiday_status.setStyleSheet("font-size: 12px; color: #555;")
        box_layout.addWidget(self.holiday_today)
        box_layout.addWidget(self.holiday_tomorrow)
        box_layout.addWidget(self.holiday_cut)
        box_layout.addWidget(self.holiday_status)
        row = QHBoxLayout()
        refresh = QPushButton("拉取/刷新今年数据")
        refresh.clicked.connect(self._refresh_holidays)
        row.addWidget(refresh)
        row.addStretch()
        box_layout.addLayout(row)
        box_layout.addWidget(self._note(
            "数据来自公共节假日 API（timor.tech），含调休补班安排，缓存于本地配置目录；"
            "断网时自动回退为“按周末推断”。用途：判断明日是否上课，从而推算今晚校园网会不会断，"
            "以及可选地在节假日跳过签到提醒。",
            "holidayNoteTab",
        ))
        layout.addWidget(box)
        layout.addStretch()
        return page

    def _refresh_holidays(self) -> None:
        self.holidays.warm_year(date.today().year)
        self._reload_holiday_tab()

    def _reload_holiday_tab(self) -> None:
        today = date.today()
        tomorrow = today + timedelta(days=1)
        self.holiday_today.setText(self.holidays.describe(today))
        self.holiday_tomorrow.setText(
            f"明天：{tomorrow.isoformat()} {self.holidays.workday_label(tomorrow)}"
            f"（{'今晚校园网会断' if self.holidays.is_workday(tomorrow) else '今晚校园网不断'}）"
        )
        self.holiday_cut.setText("今晚断网预判：" + self.ctx.tonight_cut_text())
        self.holiday_status.setText(self.holidays.status_text())

    # ---------- 关于 ----------

    def _about_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(8)

        box, box_layout = self._group("关于")
        info = QLabel(
            f"<b>校园提醒与校园网助手（CampusCheckinKit）</b><br>"
            f"版本：v{APP_VERSION}<br>"
            "开源协议：MIT License<br>"
            "功能：今日校园查寝强提醒（适用于任何学校） + CUMT 校园网自动登录与断网保活。<br>"
            "本程序为个人开源工具，与今日校园 APP、中国矿业大学官方均无隶属关系；"
            "校园网登录仅使用你自己账号的常规 ePortal 请求，请遵守所在学校网络使用规定。"
        )
        info.setWordWrap(True)
        info.setTextFormat(Qt.TextFormat.RichText)
        box_layout.addWidget(info)
        path = QLabel(f"配置文件：{self.settings.settings_path}")
        path.setWordWrap(True)
        path.setStyleSheet("font-size: 12px; color: #666;")
        box_layout.addWidget(path)
        link_btn = QPushButton("项目主页 / 问题反馈（GitHub）")
        link_btn.clicked.connect(lambda _=False: QDesktopServices.openUrl(QUrl(GITHUB_URL)))
        box_layout.addWidget(link_btn)
        layout.addWidget(box)
        layout.addStretch()
        return page

    def _open_config_dir(self) -> None:
        subprocess.Popen(["explorer", str(self.settings.settings_path.parent)])

    def _reset_onboarding(self) -> None:
        self.settings.set_bool("onboarding_completed", False)
        QMessageBox.information(self, "已重置", "下次启动时将重新显示首次启动引导。")

    # ---------- 刷新 ----------

    def refresh_all(self) -> None:
        self.reminder_switch.setChecked(self.settings.is_reminder_enabled())
        self.network_switch.setChecked(self.settings.is_network_enabled())
        self.remind_time_edit.setTime(QTime.fromString(self.settings.get_remind_time(), "HH:mm"))
        self.snooze_spin.setValue(self.settings.get_snooze_minutes())
        self._reload_pause_ranges()

        cfg = self.settings.get_network_login_config()
        self.net_enabled_box.setChecked(bool(cfg["enabled"]))
        self.username_edit.setText(cfg["username"])
        self.password_edit.setText(cfg["password"])
        self.isp_combo.setCurrentText(cfg["isp"] if cfg["isp"] in ISP_DISPLAY_LIST else ISP_DISPLAY_LIST[0])
        self.wifi_edit.setText(cfg["wifi_ssid"])
        self.auto_login_box.setChecked(cfg["auto_login"])
        self.keep_alive_box.setChecked(cfg["keep_alive"])
        self.auto_wifi_box.setChecked(cfg["auto_wifi"])
        self.night_mode_box.setChecked(cfg["night_mode"])
        self.smart_cut_box.setChecked(bool(cfg.get("smart_night_cut", True)))
        self.cut_start_edit.setTime(QTime.fromString(str(cfg.get("cut_start_time", "23:30")), "HH:mm"))
        self.cut_end_edit.setTime(QTime.fromString(str(cfg.get("cut_end_time", "07:00")), "HH:mm"))
        self.tonight_label.setText("今晚断网预判：" + self.ctx.tonight_cut_text())
        self.probe_spin.setValue(cfg["probe_interval_seconds"])

        notify = self.settings.get_notification_config()
        for category, combo in self.notify_combos.items():
            for i in range(combo.count()):
                if combo.itemData(i) == notify.get(category, "toast"):
                    combo.setCurrentIndex(i)
                    break

        self._check_autostart()
        self._reload_holiday_tab()
        self._refresh_status_labels()

    def _refresh_status_labels(self) -> None:
        from datetime import datetime

        now = datetime.now()
        today_iso = now.date().isoformat()
        if self.settings.is_reminder_enabled():
            reminded = "今日已提醒" if self.settings.get_last_reminded_date() == today_iso else "今日未提醒"
            acked = "，已确认签到" if self.settings.get_last_ack_date() == today_iso else ""
            self.status_reminder.setText(f"提醒：已启用 · {self.settings.get_remind_time()} · {reminded}{acked}")
        else:
            self.status_reminder.setText("提醒：模块已关闭")
        if self.settings.is_network_enabled():
            self.status_network.setText(
                f"校园网：已启用 · 最近状态：{self.ctx.network_status_summary()}"
            )
        else:
            self.status_network.setText("校园网：模块已关闭")
        autostart, matches = self.ctx.autostart_status()
        self.status_autostart.setText(
            "开机自启：已设置" if autostart and matches else ("开机自启：注册表项待修正" if autostart else "开机自启：未设置")
        )
        self.status_holiday.setText("今天：" + self.holidays.describe(now.date()))
        network_text = self.ctx.network_status_summary()
        self.network_status_label.setText(f"状态：{network_text}")
