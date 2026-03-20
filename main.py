"""串口读取上位机 - 主程序入口。"""
import re
import shutil
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QThread, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
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


class MainWindow(QMainWindow):
    """主窗口：串口选择、记录控制、状态显示。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("串口数据读取")
        self.resize(500, 200)

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
        self._waiting_trigger = False  # 等待设备就绪信号后开始写入
        self._delay_baseline: float | None = None  # 首个 delay 作为标定基准
        self._auto_save_root_dir: str | None = None

        self._setup_ui()
        self._refresh_ports()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # 串口与波特率
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("串口:"))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(120)
        row1.addWidget(self.port_combo)
        row1.addWidget(QLabel("波特率:"))
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"])
        self.baud_combo.setCurrentText("115200")
        row1.addWidget(self.baud_combo)
        layout.addLayout(row1)

        # 定时输入
        row_timer = QHBoxLayout()
        row_timer.addWidget(QLabel("定时(秒):"))
        self.timer_spin = QSpinBox()
        self.timer_spin.setMinimum(0)
        self.timer_spin.setMaximum(24*60*60)  # 最多24小时
        self.timer_spin.setValue(0)
        self.timer_spin.setToolTip("0为不限时")
        row_timer.addWidget(self.timer_spin)
        row_timer.addWidget(QLabel("剔除前(%):"))
        self.trim_percent_spin = QDoubleSpinBox()
        self.trim_percent_spin.setMinimum(0.0)
        self.trim_percent_spin.setMaximum(20.0)
        self.trim_percent_spin.setDecimals(2)
        self.trim_percent_spin.setSingleStep(0.1)
        self.trim_percent_spin.setValue(1.0)
        self.trim_percent_spin.setToolTip("数据处理时剔除头部毛刺比例")
        row_timer.addWidget(self.trim_percent_spin)
        row_timer.addStretch()
        layout.addLayout(row_timer)

        self.check_simulate = QCheckBox("模拟串口模式")
        self.check_simulate.setChecked(False)
        layout.addWidget(self.check_simulate)

        # 调试环境备注（停止时写入文件顶部注释区）
        layout.addWidget(QLabel("调试环境备注(停止时自动写入文件顶部):"))
        self.debug_note_edit = QTextEdit()
        self.debug_note_edit.setPlaceholderText("例如: 板卡版本/固件版本/天线配置/现场环境/备注...")
        self.debug_note_edit.setFixedHeight(70)
        layout.addWidget(self.debug_note_edit)

        # 按钮（合并打开串口+开始记录：点击开始后等待 client start 等就绪信号，再写入 offset/delay）
        row2 = QHBoxLayout()
        self.btn_start = QPushButton("开始")
        self.btn_start.clicked.connect(self._on_start_stop)
        row2.addWidget(self.btn_start)

        self.btn_process_data = QPushButton("数据处理")
        self.btn_process_data.clicked.connect(self._on_process_data)
        row2.addWidget(self.btn_process_data)

        self.btn_open_folder = QPushButton("打开文件夹")
        self.btn_open_folder.clicked.connect(self._on_open_folder)
        row2.addWidget(self.btn_open_folder)

        row2.addStretch()
        layout.addLayout(row2)

        # 状态
        self.lbl_status = QLabel("状态: 未连接")
        layout.addWidget(self.lbl_status)
        self.lbl_bytes = QLabel("已接收: 0 字节")
        layout.addWidget(self.lbl_bytes)
        self.lbl_offset = QLabel("offset: --")
        layout.addWidget(self.lbl_offset)
        self.lbl_delay = QLabel("delay: --")
        layout.addWidget(self.lbl_delay)

        layout.addStretch()

        # 右下角保存策略设置
        row_save = QHBoxLayout()
        row_save.addStretch()
        self.check_auto_save = QCheckBox("自动保存")
        self.check_auto_save.setChecked(True)
        row_save.addWidget(self.check_auto_save)
        self.btn_save_setting = QPushButton("保存设置")
        self.btn_save_setting.setFixedWidth(86)
        self.btn_save_setting.clicked.connect(self._on_save_setting)
        row_save.addWidget(self.btn_save_setting)
        layout.addLayout(row_save)

        self.lbl_save_mode = QLabel("保存模式: 自动保存到项目目录 historydata")
        self.lbl_save_mode.setStyleSheet("color: #666;")
        layout.addWidget(self.lbl_save_mode)

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

        self.lbl_status.setText("状态: 模拟串口已连接，等待设备就绪...")
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

        self.lbl_status.setText("状态: 连接中...")
        self.btn_start.setText("停止")
        self.btn_start.setEnabled(True)
        self.port_combo.setEnabled(False)
        self.baud_combo.setEnabled(False)
        self.check_simulate.setEnabled(False)
        self._waiting_trigger = True

    def _on_connected(self):
        if self._simulate_mode:
            self.lbl_status.setText("状态: 模拟串口已连接，等待设备就绪...")
        else:
            self.lbl_status.setText("状态: 已连接，等待设备就绪...")

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
        self.lbl_status.setText("状态: 未连接")
        self.lbl_offset.setText("offset: --")
        self.lbl_delay.setText("delay: --")
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
            self.lbl_status.setText("状态: 已就绪，正在记录 offset/delay")

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
            self.lbl_offset.setText(f"offset: {off_val}")
            self.lbl_delay.setText(f"delay: {delay_out}")
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
            if only_offset or only_delay:
                keep_tail.append(line + "\n")
            else:
                self._file_handle.write(f"[{ts}] {line}\n")
        self._text_buffer = "\n".join(keep_tail) if keep_tail else ""
        self._file_handle.flush()

    def _on_data_received(self, data: bytes):
        self._byte_count += len(data)
        self.lbl_bytes.setText(f"已接收: {self._byte_count} 字节")
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
            if self._recording and self._file_handle:
                self._file_handle.write(f"[{ts}] {data.hex()}\n")
                self._file_handle.flush()
            return
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
        self._delay_baseline = None

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
