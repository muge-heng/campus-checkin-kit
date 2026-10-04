from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class PauseRangeDialog(QDialog):
    def __init__(self, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置暂停日期区间")
        self.setModal(True)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.start_edit = QDateEdit()
        self.start_edit.setCalendarPopup(True)
        self.start_edit.setDate(self.start_edit.date().currentDate())

        self.end_edit = QDateEdit()
        self.end_edit.setCalendarPopup(True)
        self.end_edit.setDate(self.end_edit.date().currentDate())

        form.addRow("开始日期", self.start_edit)
        form.addRow("结束日期", self.end_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_date_range(self) -> tuple[date, date]:
        start = self.start_edit.date().toPython()
        end = self.end_edit.date().toPython()
        return start, end


class ReminderDialog(QDialog):
    def __init__(
        self,
        on_ack,
        on_snooze,
        on_add_pause_range,
        on_force_retry,
        preview_mode: bool = False,
        logo_icon: QIcon | None = None,
        parent=None,
        message: str = "",
    ) -> None:
        super().__init__(parent)
        self.on_ack = on_ack
        self.on_snooze = on_snooze
        self.on_add_pause_range = on_add_pause_range
        self.on_force_retry = on_force_retry
        self.preview_mode = preview_mode
        self.logo_icon = logo_icon or QIcon()
        self._acknowledged = False

        self.setWindowTitle("今日校园查寝提醒")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.Tool, True)
        self.setWindowModality(Qt.ApplicationModal)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        overlay = QWidget(self)
        overlay.setObjectName("overlay")
        overlay.setStyleSheet("#overlay { background-color: rgba(0, 0, 0, 185); }")
        root.addWidget(overlay)

        overlay_layout = QVBoxLayout(overlay)
        overlay_layout.setContentsMargins(30, 30, 30, 30)
        overlay_layout.addStretch()

        row = QHBoxLayout()
        row.addStretch()

        panel = QFrame()
        panel.setObjectName("reminderCard")
        panel.setStyleSheet(
            """
            QFrame#reminderCard {
                background-color: #ffffff;
                border-radius: 12px;
            }
            """
        )
        panel.setMinimumWidth(600)

        card_layout = QVBoxLayout(panel)
        card_layout.setContentsMargins(24, 20, 24, 20)

        top = QHBoxLayout()

        logo = QLabel()
        pixmap = self.logo_icon.pixmap(56, 56)
        if not pixmap.isNull():
            logo.setPixmap(pixmap)
            logo.setFixedSize(56, 56)
        else:
            logo.setFixedWidth(0)

        text_col = QVBoxLayout()

        title = QLabel(message or "已到提醒时间，请使用手机在今日校园完成查寝签到。")
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #111;")

        hint = QLabel("可点击'已签到'结束今日提醒，或设置寒暑假暂停区间。")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 13px; color: #444;")

        text_col.addWidget(title)
        text_col.addWidget(hint)

        top.addWidget(logo)
        top.addSpacing(10)
        top.addLayout(text_col, 1)

        card_layout.addLayout(top)

        buttons = QHBoxLayout()

        ack_btn = QPushButton("已签到")
        ack_btn.clicked.connect(self._handle_ack)

        snooze_btn = QPushButton("稍后提醒")
        snooze_btn.clicked.connect(self._handle_snooze)

        pause_btn = QPushButton("暂停区间")
        pause_btn.clicked.connect(self._handle_pause_range)

        buttons.addWidget(ack_btn)
        buttons.addWidget(snooze_btn)
        buttons.addWidget(pause_btn)

        card_layout.addSpacing(12)
        card_layout.addLayout(buttons)

        row.addWidget(panel)
        row.addStretch()

        overlay_layout.addLayout(row)
        overlay_layout.addStretch()

    def showEvent(self, event) -> None:
        screen = self.screen()
        if screen is not None:
            self.setGeometry(screen.geometry())
        super().showEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)

    def _handle_ack(self) -> None:
        self._acknowledged = True
        self.on_ack()
        self.accept()

    def _handle_snooze(self) -> None:
        self.on_snooze()
        self.accept()

    def _handle_pause_range(self) -> None:
        if self.preview_mode:
            QMessageBox.information(self, "预览模式", "预览模式不保存暂停区间。")
            return

        dialog = PauseRangeDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        start, end = dialog.get_date_range()
        if end < start:
            QMessageBox.warning(self, "日期错误", "结束日期不能早于开始日期。")
            return
        self.on_add_pause_range(start, end)
        QMessageBox.information(self, "已保存", f"暂停区间已保存：{start.isoformat()} ~ {end.isoformat()}")

    def closeEvent(self, event) -> None:
        if not self.preview_mode and not self._acknowledged:
            self.on_force_retry()
        super().closeEvent(event)
