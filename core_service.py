"""OFDM Host Python core service.

Phase 1/2/3 migration target:
- Keep legacy acquisition/parsing logic in Python
- Expose a stable JSON Lines IPC protocol for Flutter desktop UI

Transport:
- Read requests from stdin (one JSON object per line)
- Write responses/events to stdout (one JSON object per line)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import serial
from serial.tools import list_ports

from process_data import calc_stats_with_trim, parse_file

PROTOCOL_VERSION = "1.0.0"
SERVICE_NAME = "ofdm-host-core"
SERVICE_VERSION = "0.4.0"
DEFAULT_HEARTBEAT_SECONDS = 5.0

TRIGGER_PATTERN = re.compile(
    r"client\s+start!?|join\s+NET\s+success|INF:.*HASCH.*Init\s+OK!?|Time\s+Slot\s+index",
    re.IGNORECASE,
)
PAIR_PATTERN = re.compile(
    r"offset\s*:\s*([-\d.]+)\s+delay\s*:\s*([-\d.]+)",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(slots=True)
class Request:
    req_id: str | None
    req_type: str
    payload: dict[str, Any]


@dataclass(slots=True)
class ConnectionState:
    mode: str
    port: str
    baudrate: int
    stop_event: threading.Event
    thread: threading.Thread
    serial_obj: serial.Serial | None = None
    simulate_chunks: list[bytes] | None = None


@dataclass(slots=True)
class RecordState:
    request_id: str | None
    wait_trigger: bool
    root_dir: Path
    note: str
    armed_at_ms: int
    active: bool = False
    parsed_path: Path | None = None
    raw_path: Path | None = None
    parsed_file: Any | None = None
    raw_file: Any | None = None
    started_ts: str | None = None
    records_written: int = 0


class JsonLineIO:
    """Thread-safe JSON Lines writer and parser helpers."""

    def __init__(self) -> None:
        self._write_lock = threading.Lock()

    def send(self, message: dict[str, Any]) -> None:
        with self._write_lock:
            sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
            sys.stdout.flush()

    @staticmethod
    def parse_request(raw_line: str) -> Request:
        data = json.loads(raw_line)
        if not isinstance(data, dict):
            raise ValueError("request must be a JSON object")

        req_type = data.get("type")
        if not isinstance(req_type, str) or not req_type.strip():
            raise ValueError("field 'type' is required and must be a non-empty string")

        payload = data.get("payload", {})
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            raise ValueError("field 'payload' must be an object")

        req_id = data.get("id")
        if req_id is not None and not isinstance(req_id, str):
            req_id = str(req_id)

        return Request(req_id=req_id, req_type=req_type, payload=payload)


class CoreService:
    def __init__(self, heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS) -> None:
        self._io = JsonLineIO()
        self._stop_event = threading.Event()
        self._heartbeat_seconds = heartbeat_seconds
        self._heartbeat_thread: threading.Thread | None = None
        self._state_lock = threading.Lock()
        self._connection: ConnectionState | None = None
        self._record_lock = threading.Lock()
        self._record_state: RecordState | None = None
        self._stream_text_buffer = ""
        self._trigger_detected = False
        self._delay_baseline: float | None = None
        self._packet_loss_count = 0

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    def _emit(
        self,
        msg_type: str,
        *,
        req_id: str | None = None,
        payload: dict[str, Any] | None = None,
        code: str | None = None,
        message: str | None = None,
    ) -> None:
        data: dict[str, Any] = {
            "id": req_id,
            "type": msg_type,
            "ts": self._now_ms(),
            "payload": payload or {},
        }
        if code is not None:
            data["code"] = code
        if message is not None:
            data["message"] = message
        self._io.send(data)

    def _emit_error(self, req_id: str | None, code: str, message: str) -> None:
        self._emit(
            "error",
            req_id=req_id,
            payload={},
            code=code,
            message=message,
        )

    def _build_app_meta(self) -> dict[str, Any]:
        return {
            "service": SERVICE_NAME,
            "service_version": SERVICE_VERSION,
            "protocol_version": PROTOCOL_VERSION,
        }

    def _list_ports_payload(self) -> dict[str, Any]:
        ports_data: list[dict[str, Any]] = []
        for p in list_ports.comports():
            ports_data.append(
                {
                    "device": p.device,
                    "name": p.name,
                    "description": p.description,
                    "hwid": p.hwid,
                    "manufacturer": p.manufacturer,
                    "product": p.product,
                    "serial_number": p.serial_number,
                    "vid": p.vid,
                    "pid": p.pid,
                }
            )
        return {"ports": ports_data}

    @staticmethod
    def _now_ts() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    @staticmethod
    def _parse_baudrate(value: Any) -> int:
        try:
            baudrate = int(value)
        except (TypeError, ValueError):
            raise ValueError("field 'baudrate' must be an integer")
        if baudrate <= 0:
            raise ValueError("field 'baudrate' must be > 0")
        return baudrate

    @staticmethod
    def _parse_bool(value: Any, *, field_name: str, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "y", "on"}:
                return True
            if lowered in {"0", "false", "no", "n", "off"}:
                return False
        raise ValueError(f"field '{field_name}' must be a bool value")

    @staticmethod
    def _parse_root_dir(value: Any) -> Path:
        if value is None:
            return Path(__file__).parent
        if not isinstance(value, str) or not value.strip():
            raise ValueError("field 'root_dir' must be a non-empty string when provided")
        root = Path(value)
        if not root.is_absolute():
            root = Path(__file__).parent / root
        return root

    @staticmethod
    def _parse_trim_ratio(value: Any) -> float:
        if value is None:
            return 0.01

        try:
            ratio = float(value)
        except (TypeError, ValueError):
            raise ValueError("field 'trim_ratio' must be a numeric value")

        if ratio > 1 and ratio <= 100:
            ratio = ratio / 100.0

        if ratio < 0 or ratio >= 1:
            raise ValueError("field 'trim_ratio' must be in range [0, 1)")

        return ratio

    @staticmethod
    def _parse_simulate_line(line: str) -> bytes | None:
        s = line.strip()
        if not s or s.startswith("#"):
            return None

        s_no_space = s.replace(" ", "")
        hex_chars = "0123456789aAbBcCdDeEfF"
        if all(ch in hex_chars for ch in s_no_space) and len(s_no_space) % 2 == 0:
            try:
                return bytes.fromhex(s_no_space)
            except ValueError:
                pass
        return s.encode("utf-8")

    def _load_simulate_chunks(self, file_path: Path) -> list[bytes]:
        chunks: list[bytes] = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                chunk = self._parse_simulate_line(line)
                if chunk:
                    chunks.append(chunk)
        return chunks

    @staticmethod
    def _transmit_time_sec(num_bytes: int, baudrate: int) -> float:
        # 8N1 transmission uses about 10 bits per byte.
        return num_bytes * 10 / baudrate

    @staticmethod
    def _resolve_record_dirs(root_dir: Path) -> tuple[Path, Path]:
        parsed_dir = root_dir / "historydata"
        raw_dir = parsed_dir / "srcdata"
        parsed_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
        return parsed_dir, raw_dir

    def _reset_stream_state(self) -> None:
        self._stream_text_buffer = ""
        self._trigger_detected = False
        self._delay_baseline = None
        self._packet_loss_count = 0

    def _activate_record_if_needed(self, ts: str) -> None:
        record_event: dict[str, Any] | None = None
        req_id: str | None = None

        with self._record_lock:
            state = self._record_state
            if state is None or state.active:
                return

            parsed_file = None
            raw_file = None
            try:
                parsed_dir, raw_dir = self._resolve_record_dirs(state.root_dir)
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")
                filename = dt.strftime("%Y-%m-%d_%H-%M-%S.txt")
                parsed_path = parsed_dir / filename
                raw_path = raw_dir / filename

                parsed_file = open(parsed_path, "w", encoding="utf-8")
                raw_file = open(raw_path, "wb")

                with self._state_lock:
                    conn = self._connection

                port = conn.port if conn else "unknown"
                baudrate = str(conn.baudrate) if conn else "unknown"

                sep = "=" * 60
                header = f"{sep}\nready_time: {ts}  port: {port}  baudrate: {baudrate}\n{sep}\n"
                parsed_file.write(header)
                if state.note:
                    parsed_file.write("# NOTE_BEGIN\n")
                    for line in state.note.splitlines():
                        parsed_file.write(f"# {line}\n")
                    parsed_file.write("# NOTE_END\n")
                parsed_file.flush()

                self._delay_baseline = None
                state.active = True
                state.parsed_path = parsed_path
                state.raw_path = raw_path
                state.parsed_file = parsed_file
                state.raw_file = raw_file
                state.started_ts = ts

                req_id = state.request_id
                state.request_id = None

                record_event = {
                    "state": "recording",
                    "wait_trigger": state.wait_trigger,
                    "started_ts": ts,
                    "parsed_path": str(parsed_path),
                    "raw_path": str(raw_path),
                }
            except OSError as exc:
                if parsed_file:
                    parsed_file.close()
                if raw_file:
                    raw_file.close()
                self._record_state = None
                self._emit_error(req_id, "RECORD_OPEN_FAILED", str(exc))
                return

        if record_event is not None:
            self._emit("record.started", req_id=req_id, payload=record_event)

    @staticmethod
    def _format_delay(delay_value: float) -> str:
        text = f"{delay_value:.10f}".rstrip("0").rstrip(".")
        if text in {"", "-0"}:
            return "0"
        return text

    def _record_write_raw(self, data: bytes) -> None:
        io_error: str | None = None
        with self._record_lock:
            state = self._record_state
            if state is None or not state.active or state.raw_file is None:
                return
            try:
                state.raw_file.write(data)
                state.raw_file.flush()
            except OSError as exc:
                io_error = str(exc)

        if io_error is not None:
            self._emit_error(None, "RECORD_WRITE_FAILED", f"raw write failed: {io_error}")
            self._stop_record(reason="raw write failed", emit_event=True)

    def _record_write_parsed_line(self, line: str) -> None:
        io_error: str | None = None
        with self._record_lock:
            state = self._record_state
            if state is None or not state.active or state.parsed_file is None:
                return
            try:
                state.parsed_file.write(line + "\n")
                state.parsed_file.flush()
                state.records_written += 1
            except OSError as exc:
                io_error = str(exc)

        if io_error is not None:
            self._emit_error(None, "RECORD_WRITE_FAILED", f"parsed write failed: {io_error}")
            self._stop_record(reason="parsed write failed", emit_event=True)

    def _stop_record(
        self,
        *,
        req_id: str | None = None,
        reason: str,
        emit_event: bool,
    ) -> bool:
        payload: dict[str, Any] | None = None

        with self._record_lock:
            state = self._record_state
            if state is None:
                return False

            active = state.active
            parsed_path = str(state.parsed_path) if state.parsed_path else None
            raw_path = str(state.raw_path) if state.raw_path else None

            if state.active and state.parsed_file is not None:
                sep = "=" * 60
                end_ts = self._now_ts()
                try:
                    state.parsed_file.write(f"\n{sep}\nend_time: {end_ts}\n{sep}\n")
                    state.parsed_file.flush()
                except OSError:
                    pass

            if state.parsed_file is not None:
                try:
                    state.parsed_file.close()
                except OSError:
                    pass

            if state.raw_file is not None:
                try:
                    state.raw_file.close()
                except OSError:
                    pass

            payload = {
                "reason": reason,
                "active": active,
                "parsed_path": parsed_path,
                "raw_path": raw_path,
                "records_written": state.records_written,
            }
            self._record_state = None

        if emit_event and payload is not None:
            self._emit("record.stopped", req_id=req_id, payload=payload)
        return True

    def _detach_connection(
        self,
        *,
        expected_thread: threading.Thread | None = None,
    ) -> ConnectionState | None:
        with self._state_lock:
            conn = self._connection
            if conn is None:
                return None
            if expected_thread is not None and conn.thread is not expected_thread:
                return None
            self._connection = None
            self._reset_stream_state()
            return conn

    def _release_connection_resources(self, conn: ConnectionState, *, allow_join: bool) -> None:
        conn.stop_event.set()

        if conn.serial_obj and conn.serial_obj.is_open:
            try:
                conn.serial_obj.close()
            except Exception:
                pass

        if (
            allow_join
            and conn.thread.is_alive()
            and conn.thread is not threading.current_thread()
        ):
            conn.thread.join(timeout=1.0)

    def _on_stream_bytes(self, data: bytes) -> None:
        if not data:
            return

        ts = self._now_ts()
        self._record_write_raw(data)

        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            hex_text = data.hex()
            self._emit("stream.hex", payload={"hex": hex_text, "size": len(data)})
            self._record_write_parsed_line(f"[{ts}] {hex_text}")
            return

        self._emit("stream.text", payload={"text": text})
        self._consume_metrics_text(text, ts)

    def _consume_metrics_text(self, text: str, ts: str) -> None:
        self._stream_text_buffer += text

        if not self._trigger_detected and TRIGGER_PATTERN.search(self._stream_text_buffer):
            self._trigger_detected = True
            self._emit("trigger.detected", payload={"reason": "keyword matched"})
            self._activate_record_if_needed(ts)

        if not self._trigger_detected:
            return

        normalized = re.sub(r"d\s+elay", "delay", self._stream_text_buffer, flags=re.IGNORECASE)
        normalized = re.sub(r"of\s+fset", "offset", normalized, flags=re.IGNORECASE)

        pos = 0
        for match in PAIR_PATTERN.finditer(normalized):
            offset_raw, delay_raw = match.group(1), match.group(2)
            pos = match.end()

            try:
                offset = float(offset_raw)
                delay_value = float(delay_raw)
            except ValueError:
                continue

            if self._delay_baseline is None:
                self._delay_baseline = delay_value
            delay = delay_value - self._delay_baseline
            delay_text = self._format_delay(delay)

            self._emit(
                "metric.offset_delay",
                payload={
                    "offset": offset,
                    "delay": delay,
                    "offset_raw": offset_raw,
                    "delay_raw": delay_raw,
                },
            )
            self._record_write_parsed_line(f"[{ts}] offset:{offset_raw}  delay:{delay_text}")

        remain = normalized[pos:] if pos < len(normalized) else ""
        lines = remain.split("\n")
        keep_tail: list[str] = []

        for i, line in enumerate(lines):
            line = line.strip("\r")
            is_last = i == len(lines) - 1
            if is_last:
                keep_tail.append(line)
                break

            if not line:
                continue

            has_offset = bool(re.search(r"offset\s*:\s*[-\d.]+", line, flags=re.IGNORECASE))
            has_delay = bool(re.search(r"delay\s*:\s*[-\d.]+", line, flags=re.IGNORECASE))

            if line.strip() == "10":
                self._packet_loss_count += 1
                self._emit(
                    "metric.packet_loss",
                    payload={"count": self._packet_loss_count, "token": "10"},
                )
                self._record_write_parsed_line(f"[{ts}] PACKET_LOSS: 10")
                continue

            if (has_offset and not has_delay) or (has_delay and not has_offset):
                keep_tail.append(line + "\n")
            else:
                self._record_write_parsed_line(f"[{ts}] {line}")

        self._stream_text_buffer = "\n".join(keep_tail) if keep_tail else ""

    def _real_stream_loop(self, conn: ConnectionState) -> None:
        assert conn.serial_obj is not None
        try:
            while not conn.stop_event.is_set():
                waiting = conn.serial_obj.in_waiting
                if waiting > 0:
                    data = conn.serial_obj.read(waiting)
                    self._on_stream_bytes(data)
                else:
                    time.sleep(0.005)
        except Exception as exc:
            self._emit_error(None, "SERIAL_READ_FAILED", str(exc))
        finally:
            self._stop_record(reason="serial disconnected", emit_event=True)
            detached = self._detach_connection(expected_thread=threading.current_thread())
            if detached:
                self._release_connection_resources(detached, allow_join=False)
                self._emit(
                    "serial.disconnected",
                    payload={
                        "mode": detached.mode,
                        "port": detached.port,
                        "reason": "stream stopped",
                    },
                )

    def _simulate_stream_loop(self, conn: ConnectionState) -> None:
        chunks = conn.simulate_chunks or []
        idx = 0

        try:
            while not conn.stop_event.is_set():
                data = chunks[idx % len(chunks)]
                idx += 1
                self._on_stream_bytes(data)

                delay = self._transmit_time_sec(len(data), conn.baudrate)
                delay = max(delay, 0.001)
                if conn.stop_event.wait(delay):
                    break
        finally:
            self._stop_record(reason="serial disconnected", emit_event=True)
            detached = self._detach_connection(expected_thread=threading.current_thread())
            if detached:
                self._release_connection_resources(detached, allow_join=False)
                self._emit(
                    "serial.disconnected",
                    payload={
                        "mode": detached.mode,
                        "port": detached.port,
                        "reason": "simulate stopped",
                    },
                )

    def _handle_serial_open(self, req: Request) -> None:
        with self._state_lock:
            if self._connection is not None:
                self._emit_error(req.req_id, "SERIAL_ALREADY_OPEN", "a serial session is already active")
                return

        mode = str(req.payload.get("mode", "real")).strip().lower()
        baudrate = self._parse_baudrate(req.payload.get("baudrate", 115200))
        stop_event = threading.Event()

        if mode == "real":
            port = req.payload.get("port")
            if not isinstance(port, str) or not port.strip():
                raise ValueError("field 'port' is required for mode=real")

            try:
                serial_obj = serial.Serial(port=port, baudrate=baudrate, timeout=0.1)
            except Exception as exc:
                self._emit_error(req.req_id, "SERIAL_OPEN_FAILED", str(exc))
                return

            conn = ConnectionState(
                mode="real",
                port=port,
                baudrate=baudrate,
                stop_event=stop_event,
                thread=threading.Thread(target=lambda: self._real_stream_loop(conn), name="stream-real", daemon=True),
                serial_obj=serial_obj,
            )
        elif mode == "simulate":
            file_value = req.payload.get("file", "simulate_input.txt")
            if not isinstance(file_value, str) or not file_value.strip():
                raise ValueError("field 'file' must be a non-empty string for mode=simulate")

            file_path = Path(file_value)
            if not file_path.is_absolute():
                file_path = Path(__file__).parent / file_path

            if not file_path.exists():
                self._emit_error(req.req_id, "SIMULATE_FILE_NOT_FOUND", str(file_path))
                return

            chunks = self._load_simulate_chunks(file_path)
            if not chunks:
                self._emit_error(req.req_id, "SIMULATE_EMPTY", "simulate input has no valid chunks")
                return

            conn = ConnectionState(
                mode="simulate",
                port=str(file_path),
                baudrate=baudrate,
                stop_event=stop_event,
                thread=threading.Thread(target=lambda: self._simulate_stream_loop(conn), name="stream-simulate", daemon=True),
                simulate_chunks=chunks,
            )
        else:
            raise ValueError("field 'mode' must be either 'real' or 'simulate'")

        with self._state_lock:
            if self._connection is not None:
                self._release_connection_resources(conn, allow_join=False)
                self._emit_error(req.req_id, "SERIAL_ALREADY_OPEN", "a serial session is already active")
                return
            self._connection = conn
            self._reset_stream_state()

        conn.thread.start()
        self._emit(
            "serial.connected",
            req_id=req.req_id,
            payload={"mode": conn.mode, "port": conn.port, "baudrate": conn.baudrate},
        )

    def _handle_serial_close(self, req: Request) -> None:
        self._stop_record(req_id=req.req_id, reason="serial closed", emit_event=True)
        conn = self._detach_connection()
        if conn is None:
            self._emit_error(req.req_id, "SERIAL_NOT_OPEN", "no active serial session")
            return

        self._release_connection_resources(conn, allow_join=True)
        self._emit(
            "serial.disconnected",
            req_id=req.req_id,
            payload={"mode": conn.mode, "port": conn.port, "reason": "closed by request"},
        )

    def _handle_record_start(self, req: Request) -> None:
        with self._state_lock:
            has_connection = self._connection is not None

        if not has_connection:
            self._emit_error(req.req_id, "RECORD_NO_SERIAL", "serial must be connected before record.start")
            return

        wait_trigger = self._parse_bool(req.payload.get("wait_trigger"), field_name="wait_trigger", default=True)
        root_dir = self._parse_root_dir(req.payload.get("root_dir"))
        note_value = req.payload.get("note", "")
        note = str(note_value).strip() if note_value is not None else ""

        with self._record_lock:
            if self._record_state is not None:
                self._emit_error(req.req_id, "RECORD_ALREADY_ACTIVE", "record session already armed or active")
                return

            self._record_state = RecordState(
                request_id=req.req_id,
                wait_trigger=wait_trigger,
                root_dir=root_dir,
                note=note,
                armed_at_ms=self._now_ms(),
            )

        if wait_trigger and not self._trigger_detected:
            self._emit(
                "record.armed",
                req_id=req.req_id,
                payload={
                    "wait_trigger": True,
                    "root_dir": str(root_dir),
                    "armed_at_ms": self._now_ms(),
                },
            )
            return

        if not wait_trigger:
            self._trigger_detected = True
        self._activate_record_if_needed(self._now_ts())

    def _handle_record_stop(self, req: Request) -> None:
        stopped = self._stop_record(req_id=req.req_id, reason="stopped by request", emit_event=True)
        if not stopped:
            self._emit_error(req.req_id, "RECORD_NOT_ACTIVE", "no active record session")

    def _handle_file_process(self, req: Request) -> None:
        file_path_raw = req.payload.get("file_path")
        if not isinstance(file_path_raw, str) or not file_path_raw.strip():
            raise ValueError("field 'file_path' is required and must be a non-empty string")

        file_path = Path(file_path_raw)
        if not file_path.is_absolute():
            file_path = Path(__file__).parent / file_path

        if not file_path.exists():
            self._emit_error(req.req_id, "FILE_NOT_FOUND", str(file_path))
            return

        trim_ratio = self._parse_trim_ratio(req.payload.get("trim_ratio"))

        try:
            offsets, delays, converge_time = parse_file(str(file_path))
        except Exception as exc:
            self._emit_error(req.req_id, "PROCESS_FAILED", str(exc))
            return

        if not offsets or not delays:
            self._emit(
                "process.result",
                req_id=req.req_id,
                payload={
                    "file_path": str(file_path),
                    "trim_ratio": trim_ratio,
                    "has_data": False,
                    "message": "未找到有效 offset/delay 数据",
                },
            )
            return

        offset_stats = calc_stats_with_trim(offsets, ratio=trim_ratio)
        delay_stats = calc_stats_with_trim(delays, ratio=trim_ratio)
        self._emit(
            "process.result",
            req_id=req.req_id,
            payload={
                "file_path": str(file_path),
                "trim_ratio": trim_ratio,
                "has_data": True,
                "converge_time": converge_time,
                "offset_stats": offset_stats,
                "delay_stats": delay_stats,
            },
        )

    def _handle_request(self, req: Request) -> None:
        if req.req_type == "app.init":
            self._emit("app.ready", req_id=req.req_id, payload=self._build_app_meta())
            return

        if req.req_type == "app.ping":
            self._emit("app.pong", req_id=req.req_id, payload=self._build_app_meta())
            return

        if req.req_type == "serial.list_ports":
            self._emit("serial.ports", req_id=req.req_id, payload=self._list_ports_payload())
            return

        if req.req_type == "serial.open":
            self._handle_serial_open(req)
            return

        if req.req_type == "serial.close":
            self._handle_serial_close(req)
            return

        if req.req_type == "record.start":
            self._handle_record_start(req)
            return

        if req.req_type == "record.stop":
            self._handle_record_stop(req)
            return

        if req.req_type == "file.process":
            self._handle_file_process(req)
            return

        if req.req_type == "app.shutdown":
            self._stop_record(reason="shutdown", emit_event=True)
            conn = self._detach_connection()
            if conn is not None:
                self._release_connection_resources(conn, allow_join=True)
                self._emit(
                    "serial.disconnected",
                    payload={"mode": conn.mode, "port": conn.port, "reason": "shutdown"},
                )
            self._emit("app.stopped", req_id=req.req_id, payload={"reason": "shutdown requested"})
            self._stop_event.set()
            return

        self._emit_error(req.req_id, "UNKNOWN_TYPE", f"unsupported request type: {req.req_type}")

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.wait(self._heartbeat_seconds):
            self._emit("app.heartbeat", payload={"service": SERVICE_NAME})

    def _start_heartbeat(self) -> None:
        if self._heartbeat_seconds <= 0:
            return
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name="heartbeat", daemon=True)
        self._heartbeat_thread.start()

    def run(self) -> int:
        self._start_heartbeat()
        self._emit("app.ready", payload=self._build_app_meta())

        while not self._stop_event.is_set():
            line = sys.stdin.readline()
            if not line:
                # EOF: parent process exited or pipe closed
                break

            raw = line.strip()
            if not raw:
                continue

            req_id: str | None = None
            try:
                req = self._io.parse_request(raw)
                req_id = req.req_id
                self._handle_request(req)
            except json.JSONDecodeError as exc:
                self._emit_error(req_id, "INVALID_JSON", f"invalid JSON line: {exc.msg}")
            except ValueError as exc:
                self._emit_error(req_id, "INVALID_REQUEST", str(exc))
            except Exception:
                detail = traceback.format_exc(limit=1).strip().replace("\n", " | ")
                self._emit_error(req_id, "INTERNAL_ERROR", detail)

        self._stop_event.set()
        return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OFDM host core service (JSON Lines over stdio)")
    parser.add_argument(
        "--heartbeat-seconds",
        type=float,
        default=DEFAULT_HEARTBEAT_SECONDS,
        help="heartbeat interval in seconds, set <=0 to disable",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    service = CoreService(heartbeat_seconds=args.heartbeat_seconds)
    return service.run()


if __name__ == "__main__":
    raise SystemExit(main())
