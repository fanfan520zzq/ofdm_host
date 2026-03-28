"""串口读取上位机 - 主程序入口。"""
import re
import shutil
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QPointF, QThread, QTimer, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from serial.tools import list_ports

from serial_reader import SerialWorker, SimulateWorker, load_simulate_input
from process_data import parse_file, calc_stats_with_trim


class OffsetWaveformWidget(QWidget):
    """offset 波形显示控件（轻量自绘）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.samples: list[float] = []
        self.setMinimumHeight(220)

    def append_sample(self, value: float) -> None:
        self.samples.append(value)
        self.update()

    def clear_samples(self) -> None:
        self.samples.clear()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.fillRect(rect, QColor("#ffffff"))
        painter.setPen(QPen(QColor("#d7deeb"), 1))
        painter.drawRoundedRect(rect, 8, 8)

        plot = rect.adjusted(12, 12, -12, -12)
        if plot.width() <= 0 or plot.height() <= 0:
            return

        painter.setPen(QPen(QColor("#edf1f7"), 1))
        grid_count = 8
        for i in range(1, grid_count):
            x = int(plot.left() + i * plot.width() / grid_count)
            y = int(plot.top() + i * plot.height() / grid_count)
            painter.drawLine(x, plot.top(), x, plot.bottom())
            painter.drawLine(plot.left(), y, plot.right(), y)

        painter.setPen(QPen(QColor("#9fb7d9"), 1))
        painter.drawLine(plot.left(), plot.center().y(), plot.right(), plot.center().y())

        if len(self.samples) < 2:
            painter.setPen(QPen(QColor("#97a6ba"), 1))
            painter.drawText(plot, 0x84, "等待 offset 数据...")
            return

        max_abs = max(max(abs(v) for v in self.samples), 0.001)
        values = self.samples
        max_points = max(plot.width(), 2)
        if len(values) > max_points:
            step = len(values) / max_points
            sampled = []
            idx = 0.0
            while int(idx) < len(values):
                sampled.append(values[int(idx)])
                idx += step
            if sampled[-1] != values[-1]:
                sampled.append(values[-1])
            values = sampled

        n = len(values)
        polygon = QPolygonF()
        for i, val in enumerate(values):
            x = plot.left() + i * plot.width() / (n - 1)
            y_ratio = (val + max_abs) / (2 * max_abs)
            y = plot.bottom() - y_ratio * plot.height()
            polygon.append(QPointF(float(x), float(y)))

        painter.setPen(QPen(QColor("#2f86ff"), 1.8))
        painter.drawPolyline(polygon)

        painter.setPen(QPen(QColor("#6b7d96"), 1))
        painter.drawText(
            plot.adjusted(0, 0, -6, -6),
            0x82,
            f"offset min={min(self.samples):.6f} max={max(self.samples):.6f}",
        )


class MainWindow(QMainWindow):
    """主窗口：串口选择、记录控制、状态显示。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("串口上位机")
        self.resize(1120, 760)

        self._thread: QThread | None = None
        self._worker: SerialWorker | None = None
        self._file_handle = None
        self._raw_file_handle = None
        self._record_path: str | None = None
        self._raw_record_path: str | None = None
        self._record_start_time: datetime | None = None
        self._current_port: str | None = None
        self._byte_count = 0
        self._recording = False
        self._simulate_mode = False
        self._timer: QTimer | None = None
        self._timer_seconds: int = 0
        self._text_buffer = ""  # 用于解析 offset/delay 对
        self._live_text_buffer = ""  # 用于实时显示完整文本行
        self._waiting_trigger = False  # 等待设备就绪信号后开始写入
        self._delay_baseline: float | None = None  # 首个 delay 作为标定基准
        self._auto_save_root_dir: str | None = None
        self._packet_loss_count: int = 0

        self._setup_ui()
        self._apply_styles()
        self._refresh_ports()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(14)

        # 左侧控制面板
        left_card = QFrame()
        left_card.setObjectName("leftCard")
        left_card.setMinimumWidth(320)
        left_card.setMaximumWidth(380)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(12)

        title = QLabel("连接控制")
        title.setObjectName("panelTitle")
        left_layout.addWidget(title)

        serial_card = QFrame()
        serial_card.setObjectName("groupCard")
        serial_form = QFormLayout(serial_card)
        serial_form.setContentsMargins(10, 10, 10, 10)
        serial_form.setHorizontalSpacing(10)
        serial_form.setVerticalSpacing(10)

        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(120)
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"])
        self.baud_combo.setCurrentText("115200")
        self.timer_spin = QSpinBox()
        self.timer_spin.setMinimum(0)
        self.timer_spin.setMaximum(24 * 60 * 60)
        self.timer_spin.setValue(0)
        self.timer_spin.setToolTip("0为不限时")
        self.trim_percent_spin = QDoubleSpinBox()
        self.trim_percent_spin.setMinimum(0.0)
        self.trim_percent_spin.setMaximum(20.0)
        self.trim_percent_spin.setDecimals(2)
        self.trim_percent_spin.setSingleStep(0.1)
        self.trim_percent_spin.setValue(1.0)
        self.trim_percent_spin.setToolTip("数据处理时剔除头部毛刺比例")

        serial_form.addRow("串口", self.port_combo)
        serial_form.addRow("波特率", self.baud_combo)
        serial_form.addRow("定时(秒)", self.timer_spin)
        serial_form.addRow("剔除前(%)", self.trim_percent_spin)
        left_layout.addWidget(serial_card)

        self.check_simulate = QCheckBox("模拟串口模式")
        self.check_simulate.setChecked(False)
        left_layout.addWidget(self.check_simulate)

        row_btn = QHBoxLayout()
        self.btn_start = QPushButton("开始")
        self.btn_start.clicked.connect(self._on_start_stop)
        row_btn.addWidget(self.btn_start)
        self.btn_process_data = QPushButton("数据处理")
        self.btn_process_data.clicked.connect(self._on_process_data)
        row_btn.addWidget(self.btn_process_data)
        self.btn_open_folder = QPushButton("打开文件夹")
        self.btn_open_folder.clicked.connect(self._on_open_folder)
        row_btn.addWidget(self.btn_open_folder)
        left_layout.addLayout(row_btn)

        status_card = QFrame()
        status_card.setObjectName("groupCard")
        status_form = QFormLayout(status_card)
        status_form.setContentsMargins(10, 10, 10, 10)
        status_form.setHorizontalSpacing(12)
        status_form.setVerticalSpacing(8)

        self.lbl_status = QLabel("未连接")
        self.lbl_bytes = QLabel("0 字节")
        self.lbl_offset = QLabel("--")
        self.lbl_delay = QLabel("--")
        self.lbl_packet_loss = QLabel("0")
        status_form.addRow("状态", self.lbl_status)
        status_form.addRow("已接收", self.lbl_bytes)
        status_form.addRow("offset", self.lbl_offset)
        status_form.addRow("delay", self.lbl_delay)
        status_form.addRow("丢包", self.lbl_packet_loss)
        left_layout.addWidget(status_card)

        note_label = QLabel("调试环境备注")
        left_layout.addWidget(note_label)
        self.debug_note_edit = QTextEdit()
        self.debug_note_edit.setPlaceholderText("例如: 板卡版本/固件版本/天线配置/现场环境/备注...")
        self.debug_note_edit.setFixedHeight(72)
        left_layout.addWidget(self.debug_note_edit)

        save_row = QHBoxLayout()
        self.check_auto_save = QCheckBox("自动保存")
        self.check_auto_save.setChecked(True)
        save_row.addWidget(self.check_auto_save)
        self.btn_save_setting = QPushButton("保存设置")
        self.btn_save_setting.setFixedWidth(86)
        self.btn_save_setting.clicked.connect(self._on_save_setting)
        save_row.addWidget(self.btn_save_setting)
        save_row.addStretch()
        left_layout.addLayout(save_row)

        self.lbl_save_mode = QLabel("保存模式: 自动保存到项目目录 historydata")
        self.lbl_save_mode.setObjectName("saveModeLabel")
        left_layout.addWidget(self.lbl_save_mode)
        left_layout.addStretch()

        # 右侧实时数据区
        right_card = QFrame()
        right_card.setObjectName("rightCard")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(14, 14, 14, 14)
        right_layout.setSpacing(10)

        wave_title_row = QHBoxLayout()
        wave_title = QLabel("offset波形")
        wave_title.setObjectName("panelTitle")
        wave_title_row.addWidget(wave_title)
        wave_title_row.addStretch()
        btn_clear_wave = QPushButton("清空波形")
        btn_clear_wave.clicked.connect(self._clear_waveform)
        wave_title_row.addWidget(btn_clear_wave)
        right_layout.addLayout(wave_title_row)

        self.waveform_view = OffsetWaveformWidget()
        right_layout.addWidget(self.waveform_view, 2)

        data_title_row = QHBoxLayout()
        data_title = QLabel("实时数据")
        data_title.setObjectName("panelTitle")
        data_title_row.addWidget(data_title)
        data_title_row.addStretch()
        self.live_data_view = QTextEdit()
        self.live_data_view.setReadOnly(True)
        self.live_data_view.setPlaceholderText("串口接收数据将实时显示在这里")
        self.live_data_view.document().setMaximumBlockCount(1200)
        btn_clear_live = QPushButton("清空")
        btn_clear_live.clicked.connect(self.live_data_view.clear)
        data_title_row.addWidget(btn_clear_live)
        right_layout.addLayout(data_title_row)

        right_layout.addWidget(self.live_data_view, 3)

        root_layout.addWidget(left_card, 1)
        root_layout.addWidget(right_card, 2)

    def _apply_styles(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #f5f7fb;
                color: #1f2937;
                font-size: 13px;
            }

            #leftCard, #rightCard {
                background: #ffffff;
                border: 1px solid #d9e1ee;
                border-radius: 12px;
            }

            #groupCard {
                background: #f8fafc;
                border: 1px solid #e3e8f2;
                border-radius: 10px;
            }

            #panelTitle {
                font-size: 18px;
                font-weight: 600;
                color: #1a2433;
            }

            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {
                background: #ffffff;
                border: 1px solid #cfd8e6;
                border-radius: 8px;
                padding: 6px 8px;
            }

            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {
                border: 1px solid #3b82f6;
            }

            QPushButton {
                background: #3b82f6;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 8px 10px;
            }

            QPushButton:hover {
                background: #2563eb;
            }

            QPushButton:pressed {
                background: #1d4ed8;
            }

            #saveModeLabel {
                color: #6b7280;
            }
            """
        )

    def _refresh_ports(self):
        self.port_combo.clear()
        ports = list_ports.comports()
        for p in ports:
            self.port_combo.addItem(f"{p.device} - {p.description}", p.device)
        if not ports:
            self.port_combo.addItem("无可用串口", None)

    # 设备就绪信号：收到后创建文件并开始写入 offset/delay
    _TRIGGER_PATTERN = re.compile(
        r"client\s+start!?|join\s+NET\s+success|INF:.*HASCH.*Init\s+OK!?|Time\s+Slot\s+index",
        re.IGNORECASE,
    )
    _OFFSET_PATTERN = re.compile(r"offset\s*:\s*([\-\d.]+)", re.IGNORECASE)

    def _on_start_stop(self):
        if self._worker and self._thread and self._thread.isRunning():
            self._close_serial(manual_stop=True)
        else:
            self._open_serial()

    def _resolve_storage_dirs(self) -> tuple[Path, Path]:
        """根据保存策略返回解析文件目录和原始文件目录。"""
        if self.check_auto_save.isChecked():
            base_dir = Path(self._auto_save_root_dir) if self._auto_save_root_dir else Path(__file__).parent
            parsed_dir = base_dir / "historydata"
        else:
            parsed_dir = Path(__file__).parent / "historydata" / "_manual_tmp"
        raw_dir = parsed_dir / "srcdata"
        parsed_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
        return parsed_dir, raw_dir

    def _on_save_setting(self):
        """设置自动保存目标目录。"""
        if not self.check_auto_save.isChecked():
            self.lbl_save_mode.setText("保存模式: 手动停止后另存为")
            QMessageBox.information(self, "提示", "当前未勾选自动保存。手动停止后会弹出另存为对话框。")
            return

        start_dir = self._auto_save_root_dir or str(Path(__file__).parent)
        selected_dir = QFileDialog.getExistingDirectory(self, "选择自动保存根目录", start_dir)
        if not selected_dir:
            return
        self._auto_save_root_dir = selected_dir
        parsed_dir, _ = self._resolve_storage_dirs()
        self.lbl_save_mode.setText(f"保存模式: 自动保存到 {parsed_dir}")

    def _on_open_folder(self):
        """打开 historydata 文件夹。"""
        parsed_dir, _ = self._resolve_storage_dirs()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(parsed_dir)))

    def _on_process_data(self):
        """打开文件选择对话框，处理选中的数据文件。"""
        history_dir = Path(__file__).parent / "historydata"
        history_dir.mkdir(exist_ok=True)
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择数据文件",
            str(history_dir),
            "文本文件 (*.txt);;所有文件 (*)"
        )
        
        if not file_path:
            return
        
        try:
            offsets, delays, converge_time = parse_file(file_path)
            if not offsets or not delays:
                QMessageBox.warning(self, "提示", "未找到有效的 offset/Delay 数据！")
                return
            
            # 显示结果窗口
            trim_ratio = self.trim_percent_spin.value() / 100.0
            result_dialog = ResultDialog(offsets, delays, converge_time, file_path, trim_ratio, self)
            result_dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"处理文件出错: {e}")

    def _open_serial(self):
        self._simulate_mode = self.check_simulate.isChecked()

        if self._simulate_mode:
            self._open_simulate()
        else:
            self._open_real_serial()

    def _open_simulate(self):
        """打开模拟串口：从 simulate_input.txt 读取数据。"""
        input_path = Path(__file__).parent / "simulate_input.txt"
        chunks = load_simulate_input(str(input_path))
        if not chunks:
            QMessageBox.warning(self, "提示", "simulate_input.txt 无有效数据，请添加内容后重试")
            return
        try:
            baud = int(self.baud_combo.currentText())
        except ValueError:
            baud = 115200
        self._thread = QThread()
        self._worker = SimulateWorker(data_chunks=chunks, baudrate=baud)
        self._worker.moveToThread(self._thread)

        self._worker.dataReceived.connect(self._on_data_received)
        self._worker.errorOccurred.connect(self._on_error)
        self._worker.disconnected.connect(self._on_disconnected)
        self._worker.connected.connect(self._on_connected)

        self._thread.started.connect(self._worker.run)
        self._thread.start()

        self.lbl_status.setText("模拟串口已连接，等待设备就绪...")
        self.btn_start.setText("停止")
        self.btn_start.setEnabled(True)
        self.port_combo.setEnabled(False)
        self.baud_combo.setEnabled(False)
        self.check_simulate.setEnabled(False)
        self._waiting_trigger = True

    def _open_real_serial(self):
        """打开真实串口。"""
        port = self.port_combo.currentData() if self.port_combo.currentData() else self.port_combo.currentText()
        if not port or port == "无可用串口":
            QMessageBox.warning(self, "提示", "请选择有效串口")
            return
        try:
            baud = int(self.baud_combo.currentText())
        except ValueError:
            baud = 115200

        self._thread = QThread()
        self._worker = SerialWorker(port=port, baudrate=baud)
        self._worker.moveToThread(self._thread)

        self._worker.dataReceived.connect(self._on_data_received)
        self._worker.errorOccurred.connect(self._on_error)
        self._worker.disconnected.connect(self._on_disconnected)
        self._worker.connected.connect(self._on_connected)

        self._thread.started.connect(self._worker.run)
        self._thread.start()

        self.lbl_status.setText("连接中...")
        self.btn_start.setText("停止")
        self.btn_start.setEnabled(True)
        self.port_combo.setEnabled(False)
        self.baud_combo.setEnabled(False)
        self.check_simulate.setEnabled(False)
        self._waiting_trigger = True

    def _on_connected(self):
        if self._simulate_mode:
            self.lbl_status.setText("模拟串口已连接，等待设备就绪...")
            self._append_live_line("系统", "模拟串口已连接，等待设备就绪")
        else:
            self.lbl_status.setText("已连接，等待设备就绪...")
            self._append_live_line("系统", "串口已连接，等待设备就绪")

    def _append_live_line(self, tag: str, content: str, ts: str | None = None) -> None:
        if not content:
            return
        if ts is None:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self.live_data_view.append(f"[{ts}] {tag}: {content}")

    def _feed_live_text(self, text: str, ts: str) -> None:
        """将接收到的文本按完整行实时写入显示框。"""
        self._live_text_buffer += text
        lines = self._live_text_buffer.split("\n")
        self._live_text_buffer = lines.pop() if lines else ""
        for line in lines:
            line = line.strip("\r")
            if line:
                self._append_live_line("RX", line, ts=ts)
                # 未进入记录流程时，也尝试从实时文本中抽取 offset 画图
                if not self._recording:
                    self._try_append_offset_from_text(line)

    def _clear_waveform(self) -> None:
        self.waveform_view.clear_samples()

    def _try_append_offset_from_text(self, text: str) -> None:
        m = self._OFFSET_PATTERN.search(text)
        if not m:
            return
        try:
            value = float(m.group(1))
        except ValueError:
            return
        self.waveform_view.append_sample(value)

    def _close_serial(self, manual_stop: bool = False):
        closed_record_path = self._record_path if self._recording else None
        closed_raw_record_path = self._raw_record_path if self._recording else None
        if self._recording:
            self._stop_record(write_footer=True)
        self._waiting_trigger = False
        if self._worker:
            self._worker.close()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(1000)
        self._thread = None
        self._worker = None
        self.lbl_status.setText("未连接")
        self.lbl_offset.setText("--")
        self.lbl_delay.setText("--")
        self.btn_start.setText("开始")
        self.port_combo.setEnabled(True)
        self.baud_combo.setEnabled(True)
        self.check_simulate.setEnabled(True)
        if closed_record_path:
            self._prepend_debug_info(closed_record_path)
            if manual_stop and not self.check_auto_save.isChecked() and closed_raw_record_path:
                self._save_records_as(closed_record_path, closed_raw_record_path)

    def _save_records_as(self, parsed_src: str, raw_src: str) -> None:
        """未开启自动保存时，手动停止后另存为解析文本和原始数据。"""
        parsed_default = Path(parsed_src).name
        parsed_target, _ = QFileDialog.getSaveFileName(
            self,
            "另存为解析文本",
            str(Path(__file__).parent / parsed_default),
            "文本文件 (*.txt);;所有文件 (*)",
        )
        if not parsed_target:
            return

        raw_default = f"{Path(parsed_target).stem}_raw.txt"
        raw_target, _ = QFileDialog.getSaveFileName(
            self,
            "另存为原始二进制文本",
            str(Path(parsed_target).with_name(raw_default)),
            "文本文件 (*.txt);;所有文件 (*)",
        )
        if not raw_target:
            return

        try:
            shutil.copyfile(parsed_src, parsed_target)
            shutil.copyfile(raw_src, raw_target)
        except OSError as e:
            QMessageBox.warning(self, "提示", f"另存为失败: {e}")

    def _prepend_debug_info(self, record_path: str) -> None:
        """停止采样后将主界面备注内容写入文件顶部注释区。"""
        note = self.debug_note_edit.toPlainText().strip()
        if not note:
            return

        try:
            with open(record_path, "r", encoding="utf-8") as f:
                original_content = f.read()
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            header_lines = [
                "# DEBUG_INFO_BEGIN",
                f"# created_at: {ts}",
                "# note: these lines are metadata and ignored by parser",
            ]
            header_lines.extend(f"# {line}" for line in note.splitlines())
            header_lines.extend(["# DEBUG_INFO_END", ""])
            new_content = "\n".join(header_lines) + original_content
            with open(record_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except OSError as e:
            QMessageBox.warning(self, "提示", f"写入调试信息失败: {e}")

    def _on_disconnected(self):
        self.btn_start.setEnabled(True)

    def _on_trigger(self, ts: str):
        """收到设备就绪信号，创建文件并开始写入 offset/delay。"""
        if self._recording or self._file_handle:
            return
        if self._simulate_mode:
            self._current_port = "模拟串口"
        else:
            self._current_port = self.port_combo.currentData() or self.port_combo.currentText()
        baud = self.baud_combo.currentText()
        self._record_start_time = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")
        date_str = self._record_start_time.strftime("%Y-%m-%d")
        time_str = self._record_start_time.strftime("%H-%M-%S")
        filename = f"{date_str}_{time_str}.txt"
        history_dir, src_history_dir = self._resolve_storage_dirs()
        path = history_dir / filename
        raw_path = src_history_dir / filename
        try:
            self._file_handle = open(path, "w", encoding="utf-8")
            # 原始串口字节流直写文件：不加时间戳，不加备注，不做修正。
            self._raw_file_handle = open(raw_path, "wb")
            self._record_path = str(path)
            self._raw_record_path = str(raw_path)
            sep = "=" * 60
            header = f"{sep}\n设备就绪时间: {ts}  设备: {self._current_port}  波特率: {baud}\n{sep}\n"
            self._file_handle.write(header)
            self._file_handle.flush()
            self._recording = True
            self._waiting_trigger = False
            self._delay_baseline = None
            self._packet_loss_count = 0
            self.lbl_packet_loss.setText("0")
            self.lbl_status.setText("已就绪，正在记录 offset/delay")
            self._append_live_line("系统", f"设备就绪，开始记录。设备={self._current_port} 波特率={baud}", ts=ts)

            # 启动定时器（支持模拟模式）
            if self.timer_spin.value() > 0:
                self._timer_seconds = self.timer_spin.value()
                self._timer = QTimer(self)
                self._timer.timeout.connect(self._on_timer_tick)
                self._timer.start(1000)
        except OSError as e:
            if self._file_handle:
                self._file_handle.close()
                self._file_handle = None
            if self._raw_file_handle:
                self._raw_file_handle.close()
                self._raw_file_handle = None
            self._record_path = None
            self._raw_record_path = None
            QMessageBox.critical(self, "错误", f"无法创建文件: {e}")

    def _process_text_buffer(self, ts: str) -> None:
        """解析缓冲区：提取 offset/delay 对（每对一个时间戳），输出其他完整行。"""
        if not self._recording or not self._file_handle:
            return
        buf = re.sub(r"d\s+elay", "delay", self._text_buffer, flags=re.IGNORECASE)
        buf = re.sub(r"of\s+fset", "offset", buf, flags=re.IGNORECASE)
        pair_pat = re.compile(
            r"offset\s*:\s*([-\d.]+)\s+delay\s*:\s*([-\d.]+)",
            re.IGNORECASE | re.DOTALL,
        )
        pos = 0
        other_parts = []
        while True:
            m = pair_pat.search(buf, pos)
            if not m:
                break
            if m.start() > pos:
                other_parts.append(buf[pos : m.start()])
            off_val, dly_val = m.group(1), m.group(2)
            delay_out = dly_val
            try:
                delay_raw = float(dly_val)
                if self._delay_baseline is None:
                    self._delay_baseline = delay_raw
                delay_calibrated = delay_raw - self._delay_baseline
                delay_out = f"{delay_calibrated:.10f}".rstrip("0").rstrip(".")
                if delay_out in {"", "-0"}:
                    delay_out = "0"
            except ValueError:
                pass
            self._file_handle.write(f"[{ts}] offset:{off_val}  delay:{delay_out}\n")
            self.lbl_offset.setText(off_val)
            self.lbl_delay.setText(delay_out)
            self._append_live_line("解析", f"offset:{off_val}  delay:{delay_out}", ts=ts)
            try:
                self.waveform_view.append_sample(float(off_val))
            except ValueError:
                pass
            pos = m.end()
        remain = buf[pos:] if pos < len(buf) else ""
        lines = remain.split("\n")
        keep_tail = []
        for i, line in enumerate(lines):
            line = line.strip("\r")
            is_last = i == len(lines) - 1
            if is_last:
                keep_tail.append(line)
                break
            if not line:
                continue
            has_offset = bool(re.search(r"offset\s*:\s*[-\d.]+", line, re.IGNORECASE))
            has_delay = bool(re.search(r"delay\s*:\s*[-\d.]+", line, re.IGNORECASE))
            only_offset = has_offset and not has_delay
            only_delay = has_delay and not has_offset
            if line.strip() == "10":
                self._packet_loss_count += 1
                self.lbl_packet_loss.setText(str(self._packet_loss_count))
                self._file_handle.write(f"[{ts}] PACKET_LOSS: 10\n")
                self._append_live_line("告警", "PACKET_LOSS: 10", ts=ts)
                continue
            if only_offset or only_delay:
                keep_tail.append(line + "\n")
            else:
                self._file_handle.write(f"[{ts}] {line}\n")
                self._append_live_line("RX", line, ts=ts)
        self._text_buffer = "\n".join(keep_tail) if keep_tail else ""
        self._file_handle.flush()

    def _on_data_received(self, data: bytes):
        self._byte_count += len(data)
        self.lbl_bytes.setText(f"{self._byte_count} 字节")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        if self._recording and self._raw_file_handle:
            try:
                self._raw_file_handle.write(data)
                self._raw_file_handle.flush()
            except OSError as e:
                self._on_error(f"原始数据写入失败: {e}")
                return
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            self._append_live_line("HEX", data.hex(), ts=ts)
            if self._recording and self._file_handle:
                self._file_handle.write(f"[{ts}] {data.hex()}\n")
                self._file_handle.flush()
            return
        self._feed_live_text(text, ts)
        self._text_buffer += text
        if self._waiting_trigger:
            if self._TRIGGER_PATTERN.search(self._text_buffer):
                self._on_trigger(ts)
        if self._recording and self._file_handle:
            self._process_text_buffer(ts)

    def _on_error(self, msg: str):
        QMessageBox.critical(self, "串口错误", msg)
        self._close_serial(manual_stop=False)

    def _on_timer_tick(self):
        if not self._recording:
            if self._timer:
                self._timer.stop()
            return
        self._timer_seconds -= 1
        if self._timer_seconds > 0:
            self.btn_start.setText(f"停止 ({self._timer_seconds}s)")
        else:
            if self._timer:
                self._timer.stop()
            self._close_serial(manual_stop=False)

    def _stop_record(self, write_footer: bool = False):
        # 停止定时器
        if self._timer:
            self._timer.stop()
            self._timer = None
            self._timer_seconds = 0
        if self._file_handle:
            if write_footer:
                end_time = datetime.now()
                sep = "=" * 60
                end_ts = end_time.strftime("%Y-%m-%d %H:%M:%S")
                self._file_handle.write(f"\n{sep}\n结束时间: {end_ts}\n{sep}\n")
            self._file_handle.close()
            self._file_handle = None
        if self._raw_file_handle:
            self._raw_file_handle.close()
            self._raw_file_handle = None
        self._recording = False
        self._record_path = None
        self._raw_record_path = None
        self._record_start_time = None
        self._current_port = None
        self._text_buffer = ""
        self._live_text_buffer = ""
        self._delay_baseline = None
        self._packet_loss_count = 0
        self.lbl_packet_loss.setText("0")

    def closeEvent(self, event):
        self._close_serial(manual_stop=False)
        event.accept()


class ResultDialog(QDialog):
    """结果显示对话框。"""

    def __init__(self, offsets, delays, converge_time, file_path, trim_ratio=0.01, parent=None):
        super().__init__(parent)
        self.setWindowTitle("数据处理结果")
        self.resize(600, 400)
        
        layout = QVBoxLayout(self)
        
        # 文件信息
        file_info = f"文件: {Path(file_path).name}"
        layout.addWidget(QLabel(file_info))
        
        # 结果文本
        results = []
        trim_percent = trim_ratio * 100
        
        # 计算统计值（剔除前 N% 头部样本）
        offset_stats = calc_stats_with_trim(offsets, ratio=trim_ratio)
        delay_stats = calc_stats_with_trim(delays, ratio=trim_ratio)
        
        results.append("=" * 50)
        results.append("数据处理结果")
        results.append("=" * 50)
        results.append(f"统计口径: 剔除前 {trim_percent:.2f}% 头部样本后计算均值和最值")
        results.append(f"offset 平均值:     {offset_stats['mean']:.6f}")
        results.append(f"Delay 平均值:      {delay_stats['mean']:.6f}")
        results.append(
            f"offset 采样数:     原始 {offset_stats['raw_count']} / 使用 {offset_stats['used_count']}"
        )
        results.append(
            f"Delay 采样数:      原始 {delay_stats['raw_count']} / 使用 {delay_stats['used_count']}"
        )
        
        if converge_time is not None:
            results.append(f"收敛时间:         {converge_time:.3f} 秒")
        else:
            results.append("收敛时间:         未检测到 offset 收敛到 <0.02 的时刻")
        
        results.append("=" * 50)
        results.append("")
        
        # 额外统计信息
        if offset_stats["used_count"] > 0 or delay_stats["used_count"] > 0:
            results.append("[ 额外统计 ]")
        if offset_stats["used_count"] > 0:
            results.append(f"offset 最小值:     {offset_stats['min']:.6f}")
            results.append(f"offset 最大值:     {offset_stats['max']:.6f}")
        if delay_stats["used_count"] > 0:
            results.append(f"Delay 最小值:      {delay_stats['min']:.6f}")
            results.append(f"Delay 最大值:      {delay_stats['max']:.6f}")
        
        # 显示文本
        text_display = QTextEdit()
        text_display.setReadOnly(True)
        text_display.setText("\n".join(results))
        layout.addWidget(text_display)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.close)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)


def main():
    app = QApplication([])
    win = MainWindow()
    win.show()
    app.exec()


if __name__ == "__main__":
    main()
