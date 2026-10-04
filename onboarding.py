"""首次启动引导：介绍强提醒机制与校园网登录用法，并让用户选择启用哪些模块。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWizard, QWizardPage

from settings_store import SettingsStore


def _rich_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextFormat(Qt.RichText)
    return label


class FeaturePage(QWizardPage):
    def __init__(self, settings: SettingsStore) -> None:
        super().__init__()
        self.setTitle("欢迎使用校园提醒与校园网助手")
        self.setSubTitle("这是一个开源的聚合小工具，包含两个可以独立开关的功能模块，请选择你需要启用的功能。")
        layout = QVBoxLayout(self)
        layout.addWidget(_rich_label(
            "<b>1. 今日校园查寝强提醒</b>：到点弹出全屏强提醒卡片，督促完成签到。适用于任何学校，时间可自定义。<br>"
            "<b>2. CUMT 校园网自动登录与保活</b>：自动登录校园网 ePortal，断网自动重连，假期智能暂停。"
        ))
        self.reminder_box = QCheckBox("启用 今日校园提醒 模块")
        self.reminder_box.setChecked(settings.is_reminder_enabled())
        self.network_box = QCheckBox("启用 CUMT 校园网自动登录与保活 模块")
        self.network_box.setChecked(settings.is_network_enabled())
        layout.addWidget(self.reminder_box)
        layout.addWidget(self.network_box)
        layout.addStretch()
        self.registerField("use_reminder", self.reminder_box)
        self.registerField("use_network", self.network_box)


class ForceReminderPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("强提醒机制说明")
        self.setSubTitle("请了解提醒的行为方式，避免被“吓到”。")
        layout = QVBoxLayout(self)
        layout.addWidget(_rich_label(
            "· 到达提醒时间（默认 21:00，可在主菜单改成贵校的时间）后，屏幕会被半透明黑色遮罩覆盖，"
            "中央弹出提醒卡片，并伴随提示音。<br>"
            "· 按 <b>Esc 无法关闭</b>弹窗，这是刻意设计，防止下意识回避。<br>"
            "· 直接关闭弹窗但没有确认签到？<b>5 分钟后会重新强制弹出</b>。<br>"
            "· 点“<b>已签到</b>”：今天不再提醒。<br>"
            "· 点“<b>稍后提醒</b>”：默认 10 分钟后再弹（可在主菜单调整）。<br>"
            "· 点“<b>暂停区间</b>”：设置寒暑假等日期区间，区间内完全不提醒。<br>"
            "· 在主菜单可开启“节假日自动跳过”，法定节假日当天不打扰。<br>"
            "· 想先看看效果？主菜单和托盘里都有“预览提醒”，预览不会改动任何真实状态。"
        ))
        layout.addStretch()


class NetworkPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("校园网登录功能使用方法")
        self.setSubTitle("仅限 CUMT（中国矿业大学）校园网 ePortal；其他学校可只使用提醒模块。")
        layout = QVBoxLayout(self)
        layout.addWidget(_rich_label(
            "· 打开主菜单的“<b>校园网</b>”页，填写你的<b>校园网账号（学号）和密码</b>，选择运营商，"
            "保存后点“立即登录”验证一次。<br>"
            "· 勾选“<b>程序启动后自动尝试登录</b>”：开机/启动程序即自动上网。<br>"
            "· 勾选“<b>断网后自动检测并重连</b>”（保活）：默认每 15 秒巡检一次网络，"
            "断网后自动重连 Wi-Fi 并重新登录。<br>"
            "· <b>夜间断网智能判断</b>：学校只在<b>上课日的前一夜</b>断网（默认 23:30 至次日 07:00）。"
            "程序自动拉取节假日与调休安排推算明日是否上课，只在真会断网的时段暂停保活——"
            "周五、周六夜间和假期前夜网络不断，保活照常工作；断网时段结束自动恢复巡检。<br>"
            "· Windows <b>解锁或回到桌面</b>后也会立即尝试登录一次（断网时段除外）。<br>"
            "· 账号密码仅保存在你本机 %APPDATA% 的配置文件中，不会上传任何地方。"
        ))
        layout.addStretch()


class FinishPage(QWizardPage):
    def __init__(self, settings: SettingsStore) -> None:
        super().__init__()
        self.setTitle("启动选项")
        self.setSubTitle("设置完成后随时可在主菜单修改。")
        layout = QVBoxLayout(self)
        self.autostart_box = QCheckBox("设置开机自启（推荐，保证到点提醒和保活不断档）")
        self.autostart_box.setChecked(True)
        self.main_window_box = QCheckBox("完成后打开主菜单窗口（取消则静默启动到系统托盘）")
        self.main_window_box.setChecked(not settings.get_bool("start_with_main_window", False))
        self.tray_tip = _rich_label(
            "提示：程序平时驻留在<b>系统托盘</b>（屏幕右下角）。"
            "双击或右键托盘图标即可打开主菜单、查看状态或退出程序。"
        )
        layout.addWidget(self.autostart_box)
        layout.addWidget(self.main_window_box)
        layout.addWidget(self.tray_tip)
        layout.addStretch()
        self.registerField("want_autostart", self.autostart_box)
        self.registerField("open_main_now", self.main_window_box)


class OnboardingWizard(QWizard):
    def __init__(self, settings: SettingsStore, logo_icon=None) -> None:
        super().__init__()
        self.settings = settings
        self.setWindowTitle("首次启动引导")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        if logo_icon is not None:
            self.setWindowIcon(logo_icon)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.addPage(FeaturePage(settings))
        self.addPage(ForceReminderPage())
        self.addPage(NetworkPage())
        self.addPage(FinishPage(settings))
        self.setFixedSize(640, 520)

    def apply_result(self, ctx) -> bool:
        """把引导页的选择写入配置，返回是否需要立即打开主菜单。"""
        self.settings.set_bool("enable_reminder", bool(self.field("use_reminder")))
        self.settings.set_bool("enable_network", bool(self.field("use_network")))
        self.settings.set_bool("onboarding_completed", True)
        if self.field("want_autostart"):
            ctx.set_startup(True)
            self.settings.set_bool("autostart_user_enabled", True)
        return bool(self.field("open_main_now"))
