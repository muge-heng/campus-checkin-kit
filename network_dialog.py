from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from campus_network import ISP_DISPLAY_LIST, NetworkLoginConfig


class NetworkLoginDialog(QDialog):
    def __init__(self, config: NetworkLoginConfig, parent=None, holiday_label: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("校园网登录配置")
        self.setModal(False)
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)

        title = QLabel("校园网登录")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #111;")
        root.addWidget(title)

        hint = QLabel("用于到点提醒前后手动登录，或在断网时自动恢复连接。\n"
                      "默认对接中国矿业大学（CUMT）ePortal（10.2.5.251:801）；其他学校可在 campus_network.py 中修改门户地址。")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 13px; color: #555;")
        root.addWidget(hint)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        self.enabled_box = QCheckBox("启用校园网登录功能")
        self.enabled_box.setChecked(config.enabled)
        form.addRow("", self.enabled_box)

        self.username_edit = QLineEdit(config.username)
        self.username_edit.setPlaceholderText("学号/账号")
        form.addRow("账号", self.username_edit)

        self.password_edit = QLineEdit(config.password)
        self.password_edit.setPlaceholderText("校园网密码")
        self.password_edit.setEchoMode(QLineEdit.Password)
        form.addRow("密码", self.password_edit)

        self.isp_combo = QComboBox()
        self.isp_combo.addItems(ISP_DISPLAY_LIST)
        self.isp_combo.setCurrentText(config.isp if config.isp in ISP_DISPLAY_LIST else ISP_DISPLAY_LIST[0])
        form.addRow("运营商", self.isp_combo)

        self.wifi_edit = QLineEdit(config.wifi_ssid or "CUMT_Stu")
        form.addRow("Wi-Fi 名称", self.wifi_edit)

        self.auto_login_box = QCheckBox("程序启动后自动尝试登录")
        self.auto_login_box.setChecked(config.auto_login)
        form.addRow("", self.auto_login_box)

        self.keep_alive_box = QCheckBox("断网后自动检测并重连")
        self.keep_alive_box.setChecked(config.keep_alive)
        form.addRow("", self.keep_alive_box)

        self.probe_interval_spin = QSpinBox()
        self.probe_interval_spin.setRange(10, 60)
        self.probe_interval_spin.setSingleStep(5)
        self.probe_interval_spin.setSuffix(" 秒")
        self.probe_interval_spin.setValue(config.probe_interval_seconds)
        self.probe_interval_spin.setToolTip("断网保活开启时的网络巡检间隔，默认 15 秒。")
        form.addRow("巡检间隔", self.probe_interval_spin)

        self.auto_wifi_box = QCheckBox("重连前先尝试连接指定 Wi-Fi")
        self.auto_wifi_box.setChecked(config.auto_wifi)
        form.addRow("", self.auto_wifi_box)

        self.night_mode_box = QCheckBox("夜间失败过多时暂停重连")
        self.night_mode_box.setChecked(config.night_mode)
        form.addRow("", self.night_mode_box)

        self.holiday_box = QCheckBox("节假日/寒暑假智能暂停保活（自动拉取法定节假日）")
        self.holiday_box.setChecked(config.suspend_on_holiday)
        form.addRow("", self.holiday_box)

        root.addLayout(form)

        if holiday_label:
            holiday_note = QFrame()
            holiday_note.setObjectName("holidayNote")
            holiday_note.setStyleSheet(
                "QFrame#holidayNote { background: #f6f1e7; border: 1px solid #e2d5b8; border-radius: 6px; }"
            )
            holiday_layout = QVBoxLayout(holiday_note)
            holiday_layout.setContentsMargins(12, 9, 12, 9)
            holiday_text = QLabel(holiday_label)
            holiday_text.setWordWrap(True)
            holiday_text.setStyleSheet("font-size: 12px; color: #6b5a35;")
            holiday_layout.addWidget(holiday_text)
            root.addWidget(holiday_note)

        recovery_note = QFrame()
        recovery_note.setObjectName("recoveryNote")
        recovery_note.setStyleSheet(
            "QFrame#recoveryNote { background: #eef7f2; border: 1px solid #c9e7d6; border-radius: 6px; }"
        )
        recovery_layout = QVBoxLayout(recovery_note)
        recovery_layout.setContentsMargins(12, 9, 12, 9)
        recovery_title = QLabel("快速恢复已启用")
        recovery_title.setStyleSheet("font-weight: 700; color: #17663e;")
        recovery_hint = QLabel("Windows 解锁或回到桌面后，会立即尝试校园网登录；夜间暂停会在 07:00 自动解除。")
        recovery_hint.setWordWrap(True)
        recovery_hint.setStyleSheet("font-size: 12px; color: #31684b;")
        recovery_layout.addWidget(recovery_title)
        recovery_layout.addWidget(recovery_hint)
        root.addWidget(recovery_note)

        quick_row = QHBoxLayout()
        self.login_button = QPushButton("立即登录")
        self.check_button = QPushButton("检测网络")
        quick_row.addWidget(self.login_button)
        quick_row.addWidget(self.check_button)
        quick_row.addStretch()
        root.addLayout(quick_row)

        self.status_label = QLabel("配置保存后会同步到主菜单和托盘菜单。")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-size: 12px; color: #666;")
        root.addWidget(self.status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def get_config(self) -> NetworkLoginConfig:
        return NetworkLoginConfig(
            enabled=self.enabled_box.isChecked(),
            username=self.username_edit.text().strip(),
            password=self.password_edit.text(),
            isp=self.isp_combo.currentText(),
            auto_login=self.auto_login_box.isChecked(),
            keep_alive=self.keep_alive_box.isChecked(),
            auto_wifi=self.auto_wifi_box.isChecked(),
            wifi_ssid=self.wifi_edit.text().strip() or "CUMT_Stu",
            night_mode=self.night_mode_box.isChecked(),
            probe_interval_seconds=self.probe_interval_spin.value(),
            suspend_on_holiday=self.holiday_box.isChecked(),
        )

    def set_busy(self, busy: bool, text: str) -> None:
        self.login_button.setEnabled(not busy)
        self.check_button.setEnabled(not busy)
        self.status_label.setText(text)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)
