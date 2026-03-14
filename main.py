"""串口读取上位机 - 主程序入口。"""
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QThread, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QSpinBox,  # 新增
)
from serial.tools import list_ports

from serial_reader import SerialWorker, SimulateWorker, load_simulate_input


class MainWindow(QMainWindow):
    """主窗口：串口选择、记录控制、状态显示。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("串口数据读取")
        self.resize(400, 180)

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

        # 按钮
        row2 = QHBoxLayout()
        self.btn_open = QPushButton("打开串口")
        self.btn_open.clicked.connect(self._on_open_serial)
        row2.addWidget(self.btn_open)

        self.btn_record = QPushButton("开始记录")
        self.btn_record.clicked.connect(self._on_toggle_record)
        self.btn_record.setEnabled(False)
        row2.addWidget(self.btn_record)

        row2.addStretch()
        layout.addLayout(row2)

        # 状态
        self.lbl_status = QLabel("状态: 未连接")
        layout.addWidget(self.lbl_status)
        self.lbl_bytes = QLabel("已接收: 0 字节")
        layout.addWidget(self.lbl_bytes)
        layout.addStretch()

    def _refresh_ports(self):
        self.port_combo.clear()
        ports = list_ports.comports()
        for p in ports:
            self.port_combo.addItem(f"{p.device} - {p.description}", p.device)
        if not ports:
            self.port_combo.addItem("无可用串口", None)

    def _on_open_serial(self):
        if self._worker and self._thread and self._thread.isRunning():
            self._close_serial()
        else:
            self._open_serial()

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

        self.lbl_status.setText("状态: 模拟串口已连接（连接中...）")
        self.btn_open.setText("关闭串口")
        self.btn_open.setEnabled(True)
        self.port_combo.setEnabled(False)
        self.baud_combo.setEnabled(False)
        self.check_simulate.setEnabled(False)

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
        self.btn_open.setText("关闭串口")
        self.btn_open.setEnabled(True)
        self.port_combo.setEnabled(False)
        self.baud_combo.setEnabled(False)
        self.check_simulate.setEnabled(False)

    def _on_connected(self):
        if self._simulate_mode:
            self.lbl_status.setText("状态: 模拟串口已连接")
        else:
            self.lbl_status.setText("状态: 已连接")
        self.btn_record.setEnabled(True)

    def _close_serial(self):
        if self._recording:
            self._stop_record(write_footer=True)
        if self._worker:
            self._worker.close()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(1000)
        self._thread = None
        self._worker = None
        self.lbl_status.setText("状态: 未连接")
        self.btn_open.setText("打开串口")
        self.btn_record.setEnabled(False)
        self.port_combo.setEnabled(True)
        self.baud_combo.setEnabled(True)
        self.check_simulate.setEnabled(True)

    def _on_disconnected(self):
        self.btn_open.setEnabled(True)

    def _on_data_received(self, data: bytes):
        self._byte_count += len(data)
        self.lbl_bytes.setText(f"已接收: {self._byte_count} 字节")

        if self._recording and self._file_handle:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            try:
                text = data.decode("utf-8").rstrip("\r\n")
                out = text if text else data.hex()
            except UnicodeDecodeError:
                out = data.hex()
            self._file_handle.write(f"[{ts}] {out}\n")
            self._file_handle.flush()

    def _on_error(self, msg: str):
        QMessageBox.critical(self, "串口错误", msg)
        self._close_serial()

    def _on_toggle_record(self):
        if self._recording:
            self._stop_record(write_footer=True)
        else:
            seconds = self.timer_spin.value()
            self._start_record(seconds)

    def _start_record(self, seconds: int = 0):
        self._record_start_time = datetime.now()
        if self._simulate_mode:
            self._current_port = "模拟串口"
        else:
            self._current_port = self.port_combo.currentData() or self.port_combo.currentText()
        baud = self.baud_combo.currentText()

        # 文件名: 日期_开始时间，如 2025-03-09_10-00-00.txt
        date_str = self._record_start_time.strftime("%Y-%m-%d")
        time_str = self._record_start_time.strftime("%H-%M-%S")
        filename = f"{date_str}_{time_str}.txt"

        history_dir = Path(__file__).parent / "historydata"
        history_dir.mkdir(exist_ok=True)
        path = history_dir / filename

        try:
            self._file_handle = open(path, "w", encoding="utf-8")
            self._record_path = str(path)
            # 写入头部：分割线表达时间、设备
            sep = "=" * 60
            start_ts = self._record_start_time.strftime("%Y-%m-%d %H:%M:%S")
            header = f"{sep}\n开始时间: {start_ts}  设备: {self._current_port}  波特率: {baud}\n{sep}\n"
            self._file_handle.write(header)
            self._file_handle.flush()
            self._recording = True
            self.btn_record.setText("停止记录")
            # 定时器逻辑
            if seconds and seconds > 0:
                self._timer_seconds = seconds
                self._timer = QTimer(self)
                self._timer.timeout.connect(self._on_timer_tick)
                self._timer.start(1000)  # 每秒触发
                self.btn_record.setText(f"停止记录 ({self._timer_seconds}s)")
            else:
                self._timer = None
                self._timer_seconds = 0
        except OSError as e:
            QMessageBox.critical(self, "错误", f"无法创建文件: {e}")

    def _on_timer_tick(self):
        if not self._recording:
            if self._timer:
                self._timer.stop()
            return
        self._timer_seconds -= 1
        if self._timer_seconds > 0:
            self.btn_record.setText(f"停止记录 ({self._timer_seconds}s)")
        else:
            if self._timer:
                self._timer.stop()
            self._stop_record(write_footer=True)

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
        self.btn_record.setText("开始记录")

    def closeEvent(self, event):
        self._close_serial()
        event.accept()


def main():
    app = QApplication([])
    win = MainWindow()
    win.show()
    app.exec()


if __name__ == "__main__":
    main()
