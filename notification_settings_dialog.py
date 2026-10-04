"""
通知设置对话框 - 用于自定义各类通知的通知方式
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QComboBox,
    QVBoxLayout,
    QHBoxLayout,
)

from settings_store import SettingsStore


# 通知类型选项
NOTIFICATION_TYPE_OPTIONS = [
    ("system", "系统推送", "Windows 系统级通知，有音效"),
    ("toast", "简洁通知", "右下角小弹窗，无音效，自动消失"),
    ("none", "关闭通知", "不显示通知"),
]

# 通知分类说明
NOTIFICATION_CATEGORIES = {
    "startup": ("启动通知", "程序启动、配置保存等"),
    "checkin": ("签到通知", "确认签到、稍后提醒、暂停区间等"),
    "network": ("校园网通知", "登录成功/失败、网络检测、保活状态等"),
    "debug": ("调试通知", "预览模式、调试信息等"),
}


class NotificationSettingsDialog(QDialog):
    """通知设置对话框"""

    def __init__(self, settings: SettingsStore, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("通知设置")
        self.setModal(True)
        self.setMinimumWidth(450)

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        """设置 UI 界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        # 标题
        title = QLabel("通知设置")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #111;")
        layout.addWidget(title)

        # 说明
        hint = QLabel("自定义各类通知的通知方式。签到弹窗提醒不受此设置影响。")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 13px; color: #555;")
        layout.addWidget(hint)

        # 通知分类设置组
        group_box = QGroupBox("通知分类设置")
        group_layout = QVBoxLayout(group_box)
        group_layout.setSpacing(12)

        self.combo_boxes = {}

        for category, (name, description) in NOTIFICATION_CATEGORIES.items():
            row = QHBoxLayout()
            row.setSpacing(12)

            # 标签
            label = QLabel(name)
            label.setFixedWidth(100)
            label.setStyleSheet("font-weight: 500;")
            row.addWidget(label)

            # 下拉框
            combo = QComboBox()
            combo.setFixedWidth(150)
            for type_value, type_name, type_desc in NOTIFICATION_TYPE_OPTIONS:
                combo.addItem(type_name, type_value)
            combo.currentIndexChanged.connect(lambda idx, c=category: self._on_combo_changed(c, idx))
            row.addWidget(combo)

            # 描述
            desc_label = QLabel(description)
            desc_label.setStyleSheet("font-size: 12px; color: #666;")
            row.addWidget(desc_label, 1)

            group_layout.addLayout(row)
            self.combo_boxes[category] = combo

        layout.addWidget(group_box)

        # 通知类型说明
        info_box = QGroupBox("通知类型说明")
        info_layout = QVBoxLayout(info_box)

        for type_value, type_name, type_desc in NOTIFICATION_TYPE_OPTIONS:
            info_label = QLabel(f"• {type_name}：{type_desc}")
            info_label.setStyleSheet("font-size: 12px; color: #444;")
            info_layout.addWidget(info_label)

        layout.addWidget(info_box)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_settings(self) -> None:
        """加载设置"""
        config = self.settings.get_notification_config()
        for category, combo in self.combo_boxes.items():
            type_value = config.get(category, "toast")
            # 查找对应的索引
            for i in range(combo.count()):
                if combo.itemData(i) == type_value:
                    combo.setCurrentIndex(i)
                    break

    def _on_combo_changed(self, category: str, index: int) -> None:
        """下拉框变化回调"""
        pass  # 保存时统一处理

    def get_settings(self) -> dict:
        """获取当前设置"""
        config = {}
        for category, combo in self.combo_boxes.items():
            config[category] = combo.currentData()
        return config

    def accept(self) -> None:
        """确认保存"""
        config = self.get_settings()
        self.settings.set_notification_config(config)
        super().accept()
