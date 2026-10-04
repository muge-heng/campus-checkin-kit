"""
通知管理器 - 统一管理所有通知的发送逻辑
支持三种通知模式：系统推送、简洁通知、关闭通知
"""

from enum import Enum
from typing import Optional

from PySide6.QtWidgets import QSystemTrayIcon

from toast_notification import show_toast_notification, ToastLevel


class NotificationType(Enum):
    """通知类型枚举"""
    SYSTEM = "system"      # 系统推送
    TOAST = "toast"        # 简洁通知
    NONE = "none"          # 关闭通知


class NotificationCategory(Enum):
    """通知分类枚举"""
    STARTUP = "startup"        # 启动相关（程序启动、配置保存等）
    CHECKIN = "checkin"        # 签到相关（确认签到、稍后提醒、暂停区间等）
    NETWORK = "network"        # 校园网相关（登录、检测、保活等）
    DEBUG = "debug"            # 调试相关（预览模式等）


# 默认通知配置
DEFAULT_NOTIFICATION_CONFIG = {
    "startup": "toast",    # 启动通知使用简洁通知
    "checkin": "toast",    # 签到通知使用简洁通知
    "network": "toast",    # 校园网通知使用简洁通知
    "debug": "system",     # 调试通知使用系统推送
}


class NotificationManager:
    """通知管理器"""

    def __init__(self, tray_icon: QSystemTrayIcon, settings_store=None):
        self.tray_icon = tray_icon
        self.settings_store = settings_store

    def _get_notification_type(self, category: NotificationCategory) -> NotificationType:
        """获取指定分类的通知类型"""
        if self.settings_store:
            config = self.settings_store.get_notification_config()
            type_str = config.get(category.value, DEFAULT_NOTIFICATION_CONFIG.get(category.value, "toast"))
        else:
            type_str = DEFAULT_NOTIFICATION_CONFIG.get(category.value, "toast")

        try:
            return NotificationType(type_str)
        except ValueError:
            return NotificationType.TOAST

    def notify(
        self,
        category: NotificationCategory,
        title: str,
        message: str,
        level: ToastLevel = ToastLevel.INFO
    ) -> None:
        """
        发送通知

        Args:
            category: 通知分类
            title: 通知标题
            message: 通知内容
            level: 通知级别（用于简洁通知的指示灯颜色）
        """
        notification_type = self._get_notification_type(category)

        if notification_type == NotificationType.SYSTEM:
            self._show_system_notification(title, message)
        elif notification_type == NotificationType.TOAST:
            self._show_toast_notification(title, message, level)
        # NONE 类型不做任何操作

    def _show_system_notification(self, title: str, message: str) -> None:
        """显示系统推送通知"""
        self.tray_icon.showMessage(title, message)

    def _show_toast_notification(self, title: str, message: str, level: ToastLevel) -> None:
        """显示简洁通知"""
        show_toast_notification(message, title, level)

    def notify_startup(self, message: str) -> None:
        """发送启动相关通知"""
        self.notify(NotificationCategory.STARTUP, "今日校园查寝提醒", message, ToastLevel.INFO)

    def notify_checkin(self, message: str) -> None:
        """发送签到相关通知"""
        self.notify(NotificationCategory.CHECKIN, "今日校园查寝提醒", message, ToastLevel.SUCCESS)

    def notify_network(self, title: str, message: str, success: bool = True) -> None:
        """发送校园网相关通知"""
        level = ToastLevel.SUCCESS if success else ToastLevel.ERROR
        self.notify(NotificationCategory.NETWORK, title, message, level)

    def notify_debug(self, message: str) -> None:
        """发送调试相关通知"""
        self.notify(NotificationCategory.DEBUG, "调试", message, ToastLevel.INFO)
