"""串口读取工作线程，使用 pyserial 读取串口数据并通过信号传递。"""
import time
import serial
from PyQt6.QtCore import QObject, pyqtSignal


def _parse_line_to_bytes(line: str) -> bytes | None:
    """将一行文本解析为 bytes：hex 或 UTF-8 文本。"""
    s = line.strip()
    if not s:
        return None
    # 去掉 hex 中的空格
    hex_chars = "0123456789aAbBcCdDeEfF"
    s_no_space = s.replace(" ", "")
    if all(c in hex_chars for c in s_no_space) and len(s_no_space) % 2 == 0:
        try:
            return bytes.fromhex(s_no_space)
        except ValueError:
            pass
    return s.encode("utf-8")


def load_simulate_input(path: str) -> list[bytes]:
    """从 txt 文件加载模拟输入，每行一条数据。"""
    chunks: list[bytes] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("#"):
                    continue
                b = _parse_line_to_bytes(line)
                if b:
                    chunks.append(b)
    except OSError:
        pass
    return chunks


# 8N1 下每字节 10 bit
BITS_PER_BYTE = 10


def _transmit_time_sec(num_bytes: int, baudrate: int) -> float:
    """按波特率计算传输 N 字节所需时间（秒）。"""
    return num_bytes * BITS_PER_BYTE / baudrate


class SimulateWorker(QObject):
    """模拟串口工作类：从 txt 文件读取模拟数据，按 115200 波特率节奏发送。"""
    dataReceived = pyqtSignal(bytes)
    errorOccurred = pyqtSignal(str)
    connected = pyqtSignal()
    disconnected = pyqtSignal()

    def __init__(self, data_chunks: list[bytes], baudrate: int = 115200):
        super().__init__()
        self.data_chunks = data_chunks if data_chunks else [b"00"]
        self.baudrate = baudrate
        self._running = False

    def close(self):
        """停止模拟。"""
        self._running = False
        self.disconnected.emit()

    def run(self):
        """线程入口：按波特率模拟传输时间，循环发送 data_chunks。"""
        self._running = True
        self.connected.emit()
        idx = 0
        while self._running:
            try:
                data = self.data_chunks[idx % len(self.data_chunks)]
                idx += 1
                self.dataReceived.emit(data)
                if not self._running:
                    break
                delay = _transmit_time_sec(len(data), self.baudrate)
                delay = max(delay, 0.001)  # 最小 1ms，避免极小包时死循环
                time.sleep(delay)
            except Exception as e:
                self.errorOccurred.emit(str(e))
                break


class SerialWorker(QObject):
    """串口读取工作类，在 QThread 中运行。"""
    dataReceived = pyqtSignal(bytes)
    errorOccurred = pyqtSignal(str)
    connected = pyqtSignal()
    disconnected = pyqtSignal()

    def __init__(self, port: str, baudrate: int = 115200):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self._serial: serial.Serial | None = None
        self._running = False

    def open(self) -> bool:
        """打开串口。"""
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.1,
            )
            self._running = True
            self.connected.emit()
            return True
        except Exception as e:
            self.errorOccurred.emit(str(e))
            return False

    def close(self):
        """关闭串口。"""
        self._running = False
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
        self.disconnected.emit()

    def run(self):
        """线程入口：打开串口并执行读取循环。"""
        if not self.open():
            return
        self._read_loop()

    def _read_loop(self):
        """在 QThread 中执行的读取循环。"""
        if not self._serial or not self._serial.is_open:
            return
        while self._running and self._serial and self._serial.is_open:
            try:
                if self._serial.in_waiting > 0:
                    data = self._serial.read(self._serial.in_waiting)
                    if data:
                        self.dataReceived.emit(data)
                else:
                    time.sleep(0.005)
            except Exception as e:
                self.errorOccurred.emit(str(e))
                break
        self.close()
