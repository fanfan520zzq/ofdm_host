"""串口读取上位机 - 主程序入口。"""
import re
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QThread, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
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
from process_data import parse_file


class MainWindow(QMainWindow):
    """主窗口：串口选择、记录控制、状态显示。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("串口数据读取")
        self.resize(500, 200)

        self._thread: QThread | None = None
        self._worker: SerialWorker | None = None
        self._file_handle = None
        self._record_path: str | None = None
        self._record_start_time: datetime | None = None
        self._current_port: str | None = None
        self._byte_count = 0
        self._recording = False
        self._simulate_mode = False
        self._timer: QTimer | None = None
        self._timer_seconds: int = 0
        self._text_buffer = ""  # 用于解析 offset/delay 对
        self._waiting_trigger = False  # 等待设备就绪信号后开始写入

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
        row_timer.addStretch()
        layout.addLayout(row_timer)

        self.check_simulate = QCheckBox("模拟串口模式")
        self.check_simulate.setChecked(False)
        layout.addWidget(self.check_simulate)

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
            self._close_serial()
        else:
            self._open_serial()

    def _on_open_folder(self):
        """打开 historydata 文件夹。"""
        history_dir = Path(__file__).parent / "historydata"
        history_dir.mkdir(exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(history_dir)))

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
            result_dialog = ResultDialog(offsets, delays, converge_time, file_path, self)
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

    def _close_serial(self):
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
        history_dir = Path(__file__).parent / "historydata"
        history_dir.mkdir(exist_ok=True)
        path = history_dir / filename
        try:
            self._file_handle = open(path, "w", encoding="utf-8")
            self._record_path = str(path)
            sep = "=" * 60
            header = f"{sep}\n设备就绪时间: {ts}  设备: {self._current_port}  波特率: {baud}\n{sep}\n"
            self._file_handle.write(header)
            self._file_handle.flush()
            self._recording = True
            self._waiting_trigger = False
            self.lbl_status.setText("状态: 已就绪，正在记录 offset/delay")

            # 启动定时器（支持模拟模式）
            if self.timer_spin.value() > 0:
                self._timer_seconds = self.timer_spin.value()
                self._timer = QTimer(self)
                self._timer.timeout.connect(self._on_timer_tick)
                self._timer.start(1000)
        except OSError as e:
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
            self._file_handle.write(f"[{ts}] offset:{off_val}  delay:{dly_val}\n")
            self.lbl_offset.setText(f"offset: {off_val}")
            self.lbl_delay.setText(f"delay: {dly_val}")
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
        self._close_serial()

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
            self._close_serial()

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
        self._recording = False
        self._record_path = None
        self._record_start_time = None
        self._current_port = None
        self._text_buffer = ""

    def closeEvent(self, event):
        self._close_serial()
        event.accept()


class ResultDialog(QDialog):
    """结果显示对话框。"""

    def __init__(self, offsets, delays, converge_time, file_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("数据处理结果")
        self.resize(600, 400)
        
        layout = QVBoxLayout(self)
        
        # 文件信息
        file_info = f"文件: {Path(file_path).name}"
        layout.addWidget(QLabel(file_info))
        
        # 结果文本
        results = []
        
        # 计算平均值
        avg_offset = sum(offsets) / len(offsets) if offsets else 0
        avg_delay = sum(delays) / len(delays) if delays else 0
        
        results.append("=" * 50)
        results.append("数据处理结果")
        results.append("=" * 50)
        results.append(f"offset 平均值:     {avg_offset:.6f}")
        results.append(f"Delay 平均值:      {avg_delay:.6f}")
        results.append(f"offset 采样数:     {len(offsets)}")
        results.append(f"Delay 采样数:      {len(delays)}")
        
        if converge_time is not None:
            results.append(f"收敛时间:         {converge_time:.3f} 秒")
        else:
            results.append("收敛时间:         未检测到 offset 收敛到 <0.02 的时刻")
        
        results.append("=" * 50)
        results.append("")
        
        # 额外统计信息
        if offsets:
            min_offset = min(offsets)
            max_offset = max(offsets)
            results.append("[ 额外统计 ]")
            results.append(f"offset 最小值:     {min_offset:.6f}")
            results.append(f"offset 最大值:     {max_offset:.6f}")
        
        if delays:
            min_delay = min(delays)
            max_delay = max(delays)
            results.append(f"Delay 最小值:      {min_delay:.6f}")
            results.append(f"Delay 最大值:      {max_delay:.6f}")
        
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
