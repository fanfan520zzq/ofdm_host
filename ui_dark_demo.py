import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPalette, QPen
from PyQt5.QtWidgets import (
    QApplication,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (  # type: ignore
    ComboBox,
    FluentTitleBar,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    Theme,
    setTheme,
    setThemeColor,
)
from qfluentwidgets.components.widgets.frameless_window import FramelessWindow  # type: ignore


class PlotPlaceholder(QWidget):
    """波形占位控件：预留绘图区域并开启抗锯齿。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("plotArea")
        self.setMinimumHeight(300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        rect = self.rect().adjusted(8, 8, -8, -8)
        grid_pen = QPen(QColor("#3A3A3A"), 1)
        mid_pen = QPen(QColor("#2D9CFF"), 1)

        painter.setPen(grid_pen)
        steps = 10
        dx = rect.width() / steps
        dy = rect.height() / steps
        for i in range(1, steps):
            x = int(rect.left() + i * dx)
            y = int(rect.top() + i * dy)
            painter.drawLine(x, rect.top(), x, rect.bottom())
            painter.drawLine(rect.left(), y, rect.right(), y)

        painter.setPen(mid_pen)
        painter.drawLine(rect.left(), rect.center().y(), rect.right(), rect.center().y())

        painter.setPen(QColor("#8EC9FF"))
        painter.drawText(rect.adjusted(10, 10, -10, -10), Qt.AlignTop | Qt.AlignLeft, "Waveform Area (AA On)")


class NeonPrimaryButton(PrimaryPushButton):
    """带霓虹光感的主按钮。"""

    def __init__(self, text: str, parent=None):
        super().__init__(parent=parent)
        self.setText(text)
        self.setObjectName("openPortButton")
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setOffset(0, 0)
        self.shadow.setBlurRadius(18)
        self.shadow.setColor(QColor(34, 169, 255, 70))
        self.setGraphicsEffect(self.shadow)

    def enterEvent(self, event):
        self.shadow.setBlurRadius(28)
        self.shadow.setColor(QColor(34, 169, 255, 140))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.shadow.setBlurRadius(18)
        self.shadow.setColor(QColor(34, 169, 255, 70))
        super().leaveEvent(event)


class IndustrialTitleBar(FluentTitleBar):
    """工业风标题栏：导航与窗口控制按钮融合。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("customTitleBar")
        self.setFixedHeight(38)

        self.minBtn.setObjectName("titleMinBtn")
        self.maxBtn.setObjectName("titleMaxBtn")
        self.closeBtn.setObjectName("titleCloseBtn")

        self.menu_host = QFrame(self)
        self.menu_host.setObjectName("titleMenuHost")
        menu_layout = QHBoxLayout(self.menu_host)
        menu_layout.setContentsMargins(6, 0, 6, 0)
        menu_layout.setSpacing(6)

        self.menu_buttons = []
        for text in ["仪表盘", "串口", "波形", "日志"]:
            btn = PushButton(text)
            btn.setObjectName("titleMenuButton")
            btn.setFixedHeight(28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, b=btn: self._set_active(b))
            self.menu_buttons.append(btn)
            menu_layout.addWidget(btn)

        self._set_active(self.menu_buttons[1])

        self.hBoxLayout.insertSpacing(2, 10)
        self.hBoxLayout.insertWidget(3, self.menu_host, 0, Qt.AlignLeft | Qt.AlignVCenter)

    def _set_active(self, active_btn: PushButton):
        for btn in self.menu_buttons:
            btn.setProperty("active", btn is active_btn)
            btn.style().unpolish(btn)
            btn.style().polish(btn)


class MainWindow(FramelessWindow):
    def __init__(self):
        super().__init__()
        self.setObjectName("mainWindow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowTitle("OFDM Industrial Host")
        self.resize(1320, 800)
        self.setMinimumSize(1120, 680)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)

        try:
            self.windowEffect.setMicaEffect(int(self.winId()), False)
        except Exception:
            try:
                self.windowEffect.removeBackgroundEffect(int(self.winId()))
            except Exception:
                pass

        self.setTitleBar(IndustrialTitleBar(self))

        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("#F5F6F8"))
        palette.setColor(QPalette.WindowText, QColor("#111111"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self._build_ui()
        self._apply_qss()
        self._load_demo_logs()

    def _build_ui(self):
        self.content_root = QWidget(self)
        self.content_root.setObjectName("contentRoot")
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, self.titleBar.height() + 8, 18, 18)
        root_layout.setSpacing(0)
        root_layout.addWidget(self.content_root)

        content_layout = QHBoxLayout(self.content_root)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        left_card = self._build_left_control_card()
        right_panel = self._build_right_panel()
        content_layout.addWidget(left_card, 1)
        content_layout.addWidget(right_panel, 3)

    def _build_left_control_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("controlCard")

        effect = QGraphicsDropShadowEffect(card)
        effect.setOffset(0, 2)
        effect.setBlurRadius(24)
        effect.setColor(QColor(0, 0, 0, 120))
        card.setGraphicsEffect(effect)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        title = QLabel("连接控制")
        title.setObjectName("cardMainTitle")
        subtitle = QLabel("Serial Controller")
        subtitle.setObjectName("cardSubTitle")

        setting_wrap = QFrame()
        setting_wrap.setObjectName("innerCard")
        setting_layout = QFormLayout(setting_wrap)
        setting_layout.setContentsMargins(12, 12, 12, 12)
        setting_layout.setHorizontalSpacing(10)
        setting_layout.setVerticalSpacing(12)
        setting_layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        setting_layout.setFormAlignment(Qt.AlignTop)

        self.combo_port = ComboBox()
        self.combo_port.setObjectName("modernCombo")
        self.combo_port.addItems(["COM1", "COM2", "COM3", "COM4", "COM5"])

        self.combo_baud = ComboBox()
        self.combo_baud.setObjectName("modernCombo")
        self.combo_baud.addItems(["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"])
        self.combo_baud.setCurrentText("115200")

        label_port = QLabel("串口")
        label_baud = QLabel("波特率")
        label_port.setObjectName("fieldKey")
        label_baud.setObjectName("fieldKey")

        setting_layout.addRow(label_port, self.combo_port)
        setting_layout.addRow(label_baud, self.combo_baud)

        self.btn_open = NeonPrimaryButton("打开串口")
        self.btn_open.setCheckable(True)
        self.btn_open.setMinimumHeight(42)
        self.btn_open.clicked.connect(self._mock_toggle)

        status_wrap = QFrame()
        status_wrap.setObjectName("innerCard")
        status_layout = QFormLayout(status_wrap)
        status_layout.setContentsMargins(12, 12, 12, 12)
        status_layout.setHorizontalSpacing(16)
        status_layout.setVerticalSpacing(10)

        self.status_value = QLabel("未连接")
        self.status_value.setObjectName("statusValueOffline")

        kv_items = [
            ("状态", self.status_value),
            ("协议", QLabel("UART")),
            ("数据位", QLabel("8N1")),
            ("模式", QLabel("实时采集")),
        ]
        for key, value in kv_items:
            key_label = QLabel(key)
            key_label.setObjectName("kvKey")
            value.setObjectName(value.objectName() or "kvValue")
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            status_layout.addRow(key_label, value)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(setting_wrap)
        layout.addWidget(self.btn_open)
        layout.addWidget(status_wrap)
        layout.addStretch(1)
        return card

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        right_layout = QVBoxLayout(panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        plot_card = QFrame()
        plot_card.setObjectName("plotCard")
        plot_layout = QVBoxLayout(plot_card)
        plot_layout.setContentsMargins(12, 12, 12, 12)
        plot_layout.setSpacing(10)

        plot_title = QLabel("实时波形")
        plot_title.setObjectName("sectionTitle")
        plot_hint = QLabel("预留 pyqtgraph 绘图区，已启用抗锯齿")
        plot_hint.setObjectName("sectionHint")
        self.plot_widget = PlotPlaceholder()

        plot_layout.addWidget(plot_title)
        plot_layout.addWidget(plot_hint)
        plot_layout.addWidget(self.plot_widget)

        log_card = QFrame()
        log_card.setObjectName("logCard")
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(12, 12, 12, 12)
        log_layout.setSpacing(8)

        log_title = QLabel("数据日志")
        log_title.setObjectName("sectionTitle")

        self.log_edit = PlainTextEdit()
        self.log_edit.setObjectName("logEdit")
        self.log_edit.setReadOnly(True)
        self.log_edit.setMinimumHeight(190)
        self.log_edit.setMaximumHeight(220)
        self.log_edit.document().setMaximumBlockCount(10)

        log_layout.addWidget(log_title)
        log_layout.addWidget(self.log_edit)

        right_layout.addWidget(plot_card, 3)
        right_layout.addWidget(log_card, 1)
        return panel

    def _mock_toggle(self):
        connected = self.btn_open.isChecked()
        if connected:
            self.btn_open.setText("关闭串口")
            self.status_value.setText("已连接")
            self.status_value.setObjectName("statusValueOnline")
        else:
            self.btn_open.setText("打开串口")
            self.status_value.setText("未连接")
            self.status_value.setObjectName("statusValueOffline")

        self.status_value.style().unpolish(self.status_value)
        self.status_value.style().polish(self.status_value)

    def _load_demo_logs(self):
        logs = [
            "[20:15:22.118] RX: offset:0.0021 delay:10.01",
            "[20:15:22.168] RX: offset:0.0014 delay:10.08",
            "[20:15:22.218] RX: PACKET_OK",
            "[20:15:22.268] RX: PACKET_OK",
            "[20:15:22.318] RX: PACKET_LOSS",
            "[20:15:22.368] RX: PACKET_OK",
            "[20:15:22.418] RX: PACKET_OK",
            "[20:15:22.468] RX: delay update: 0.0029",
            "[20:15:22.518] RX: jitter: 0.0004",
            "[20:15:22.568] RX: stream stable",
        ]
        self.log_edit.setPlainText("\n".join(logs))

    def _apply_qss(self):
        self.setStyleSheet(
            """
            #mainWindow, #contentRoot {
                background: #F5F6F8;
                color: #111111;
            }

            #customTitleBar {
                background: #FFFFFF;
                border: 1px solid #D9DFEA;
                border-bottom: 0;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }

            #titleLabel {
                color: #14171C;
                font-size: 13px;
                font-weight: 600;
            }

            #titleMenuHost {
                background: transparent;
            }

            #titleMenuButton {
                color: #2A3442;
                background: #F4F7FC;
                border: 1px solid #D1D9E7;
                border-radius: 7px;
                padding: 0 10px;
            }

            #titleMenuButton:hover {
                background: #EAF2FF;
                border: 1px solid #2D9CFF;
                color: #0F2238;
            }

            #titleMenuButton[active="true"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #238BFF, stop:1 #2DBBFF);
                border: none;
                color: #071522;
                font-weight: 600;
            }

            #titleMinBtn, #titleMaxBtn {
                border-radius: 6px;
                background: transparent;
            }

            #titleMinBtn:hover, #titleMaxBtn:hover {
                background: #E9EEF7;
            }

            #titleCloseBtn {
                border-radius: 6px;
                background: transparent;
            }

            #titleCloseBtn:hover {
                background: #E81123;
            }

            #controlCard, #plotCard, #logCard {
                background: #FFFFFF;
                border: 1px solid #DCE3EF;
                border-radius: 14px;
            }

            #innerCard {
                background: #F7F9FC;
                border: 1px solid #E2E8F2;
                border-radius: 10px;
            }

            #cardMainTitle {
                color: #121821;
                font-size: 21px;
                font-weight: 600;
                letter-spacing: 0.8px;
            }

            #cardSubTitle {
                color: #5F7288;
                font-size: 12px;
            }

            #fieldKey {
                color: #5D6C80;
                font-size: 12px;
                min-width: 52px;
            }

            #modernCombo {
                border: 1px solid #CED7E6;
                background: #FFFFFF;
                border-radius: 8px;
                min-height: 34px;
                padding: 0 10px;
                color: #111111;
            }

            #modernCombo:hover {
                border: 1px solid #2D9CFF;
                background: #F2F8FF;
            }

            #openPortButton {
                border: 1px solid #44B7FF;
                border-radius: 10px;
                min-height: 42px;
                color: #081726;
                font-size: 14px;
                font-weight: 700;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1EA5FF, stop:1 #52D4FF);
            }

            #openPortButton:hover {
                border: 1px solid #7FD0FF;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #31B0FF, stop:1 #6EDFFF);
            }

            #openPortButton:pressed, #openPortButton:checked {
                color: #07121F;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1A8CE0, stop:1 #3BB4E3);
            }

            #kvKey {
                color: #5D6F86;
                font-size: 12px;
            }

            #kvValue {
                color: #141A22;
                font-size: 12px;
                font-weight: 500;
            }

            #statusValueOffline {
                color: #FFC28E;
                font-size: 12px;
                font-weight: 600;
            }

            #statusValueOnline {
                color: #70FFB5;
                font-size: 12px;
                font-weight: 600;
            }

            #sectionTitle {
                color: #111111;
                font-size: 14px;
                font-weight: 600;
            }

            #sectionHint {
                color: #607286;
                font-size: 12px;
            }

            #plotArea {
                border-radius: 10px;
                border: 1px solid #D7DFEC;
                background: #F9FBFE;
            }

            #logEdit {
                border-radius: 10px;
                border: 1px solid #D7DFEC;
                background: #FCFDFF;
                color: #111111;
                padding: 8px;
                selection-background-color: #2D9CFF;
                selection-color: #FFFFFF;
            }

            #logEdit QScrollBar:vertical {
                width: 4px;
                margin: 4px 2px 4px 2px;
                background: transparent;
            }

            #logEdit QScrollBar::handle:vertical {
                min-height: 20px;
                border-radius: 2px;
                background: transparent;
            }

            #logEdit:hover QScrollBar::handle:vertical {
                background: rgba(45, 156, 255, 145);
            }

            #logEdit QScrollBar::add-line:vertical,
            #logEdit QScrollBar::sub-line:vertical,
            #logEdit QScrollBar::add-page:vertical,
            #logEdit QScrollBar::sub-page:vertical {
                height: 0px;
                background: transparent;
            }
            """
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    setTheme(Theme.LIGHT)
    setThemeColor("#2D9CFF")

    win = MainWindow()
    win.show()

    sys.exit(app.exec_())
