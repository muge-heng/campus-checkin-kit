"""
简洁通知组件 - Toast 风格通知
在系统右下角时间区域上方弹出小字体通知，自动出现与消失，无音效
支持堆叠效果、滑入动画、状态指示灯
"""

from enum import Enum
from typing import List
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QRect
from PySide6.QtGui import QFont, QScreen, QColor
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGraphicsOpacityEffect, QApplication


class ToastLevel(Enum):
    """通知级别"""
    SUCCESS = "success"  # 绿色 - 成功
    ERROR = "error"      # 红色 - 失败
    WARNING = "warning"  # 黄色 - 警告
    INFO = "info"        # 蓝色 - 信息


# 级别对应颜色
LEVEL_COLORS = {
    ToastLevel.SUCCESS: "#4CAF50",
    ToastLevel.ERROR: "#f44336",
    ToastLevel.WARNING: "#FF9800",
    ToastLevel.INFO: "#2196F3",
}


class ToastNotification(QWidget):
    """简洁通知组件 - 支持堆叠、滑入动画、状态指示灯"""

    # 保持对活跃 Toast 的引用，防止被垃圾回收
    _active_toasts: List["ToastNotification"] = []
    _max_active_toasts = 4

    def __init__(
        self,
        message: str,
        title: str = "",
        level: ToastLevel = ToastLevel.INFO,
        duration: int = 3000,
        parent=None
    ):
        super().__init__(parent)
        self.duration = duration
        self.level = level
        self._setup_ui(title, message)
        self._setup_animation()

    def _setup_ui(self, title: str, message: str) -> None:
        """设置 UI 界面"""
        # 窗口属性设置
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(320)

        # 主容器 - Windows 11 风格
        container = QWidget(self)
        container.setObjectName("toastContainer")
        container.setStyleSheet("""
            QWidget#toastContainer {
                background-color: #1e1e1e;
                border-radius: 8px;
                border: 1px solid #333333;
            }
        """)

        # 主布局
        main_layout = QHBoxLayout(container)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(12)

        # 状态指示灯
        indicator = QLabel()
        indicator.setFixedSize(10, 10)
        color = LEVEL_COLORS.get(self.level, "#2196F3")
        indicator.setStyleSheet(f"""
            background-color: {color};
            border-radius: 5px;
            border: none;
        """)
        main_layout.addWidget(indicator, alignment=Qt.AlignTop)

        # 文字区域
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)

        # 标题（可选）
        if title:
            title_label = QLabel(title)
            title_label.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
            title_label.setStyleSheet("color: #ffffff; background: transparent;")
            title_label.setWordWrap(True)
            text_layout.addWidget(title_label)

        # 消息内容
        msg_label = QLabel(message)
        msg_label.setFont(QFont("Microsoft YaHei", 9))
        msg_label.setStyleSheet("color: #cccccc; background: transparent;")
        msg_label.setWordWrap(True)
        text_layout.addWidget(msg_label)

        main_layout.addLayout(text_layout, 1)

        # 调整容器大小
        container.adjustSize()
        self.setFixedSize(container.sizeHint())

        # 透明度效果
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self.opacity_effect)

    def _setup_animation(self) -> None:
        """设置动画效果"""
        # 淡入动画
        self.fade_in = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_in.setDuration(250)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(1.0)
        self.fade_in.setEasingCurve(QEasingCurve.OutCubic)

        # 淡出动画
        self.fade_out = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_out.setDuration(300)
        self.fade_out.setStartValue(1.0)
        self.fade_out.setEndValue(0.0)
        self.fade_out.setEasingCurve(QEasingCurve.InCubic)
        self.fade_out.finished.connect(self._on_close_finished)

        # 位置动画（用于堆叠效果）
        self.pos_animation = QPropertyAnimation(self, b"pos")
        self.pos_animation.setDuration(200)
        self.pos_animation.setEasingCurve(QEasingCurve.OutCubic)

        # 自动关闭定时器
        self.close_timer = QTimer(self)
        self.close_timer.setSingleShot(True)
        self.close_timer.timeout.connect(self._start_fade_out)

    def _get_target_position(self, index: int) -> QPoint:
        """根据索引计算目标位置（从右下角向上堆叠，确保在任务栏上方）"""
        screen = QApplication.primaryScreen()
        if not screen:
            return QPoint(100, 100)

        # availableGeometry 已排除任务栏区域
        available = screen.availableGeometry()
        margin = 16
        gap = 8

        x = available.x() + available.width() - self.width() - margin
        # 从可用区域底部向上计算，确保在任务栏上方
        y = available.y() + available.height() - self.height() - margin - (self.height() + gap) * index

        return QPoint(x, y)

    def show_toast(self) -> None:
        """显示通知"""
        # 保持引用，防止被垃圾回收
        ToastNotification._active_toasts.append(self)

        # 计算位置（最新的在最下面）
        index = 0
        self.move(self._get_target_position(index))

        # 限制并发数量，避免堆积导致资源占用上升
        if len(ToastNotification._active_toasts) > ToastNotification._max_active_toasts:
            oldest = ToastNotification._active_toasts[0]
            oldest._start_fade_out()

        # 先显示窗口
        self.show()
        self.raise_()

        # 滑入动画：从右侧滑入
        start_pos = self._get_target_position(index)
        start_pos.setX(start_pos.x() + 100)  # 从右侧偏移
        self.move(start_pos)

        # 同时播放淡入和滑入动画
        self.fade_in.start()

        self.pos_animation.stop()
        self.pos_animation.setDuration(250)
        self.pos_animation.setStartValue(start_pos)
        self.pos_animation.setEndValue(self._get_target_position(index))
        self.pos_animation.start()

        # 启动自动关闭定时器
        self.close_timer.start(self.duration)

        # 移动其他 Toast 向上
        self._restack_toasts()

    def _restack_toasts(self) -> None:
        """重新排列所有活跃的 Toast"""
        for i, toast in enumerate(ToastNotification._active_toasts):
            target_pos = toast._get_target_position(i)
            if toast.pos() != target_pos and toast.isVisible():
                toast.pos_animation.stop()
                toast.pos_animation.setStartValue(toast.pos())
                toast.pos_animation.setEndValue(target_pos)
                toast.pos_animation.start()

    def _start_fade_out(self) -> None:
        """开始淡出动画"""
        self.fade_out.start()

    def _on_close_finished(self) -> None:
        """关闭动画完成"""
        self.close()
        # 移除引用
        if self in ToastNotification._active_toasts:
            ToastNotification._active_toasts.remove(self)
        # 重新排列剩余的 Toast
        self._restack_toasts()

    def mousePressEvent(self, event) -> None:
        """点击关闭"""
        self._start_fade_out()
        super().mousePressEvent(event)


def show_toast_notification(
    message: str,
    title: str = "",
    level: ToastLevel = ToastLevel.INFO,
    duration: int = 3000
) -> None:
    """便捷函数：显示简洁通知"""
    toast = ToastNotification(message, title, level, duration)
    toast.show_toast()
