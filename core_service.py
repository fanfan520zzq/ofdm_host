"""OFDM Host Python core service.

Phase 1/2 migration target:
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
from pathlib import Path
from typing import Any

import serial
from serial.tools import list_ports

PROTOCOL_VERSION = "1.0.0"
SERVICE_NAME = "ofdm-host-core"
SERVICE_VERSION = "0.2.0"
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
    def _parse_baudrate(value: Any) -> int:
        try:
            baudrate = int(value)
        except (TypeError, ValueError):
            raise ValueError("field 'baudrate' must be an integer")
        if baudrate <= 0:
            raise ValueError("field 'baudrate' must be > 0")
        return baudrate

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

    def _reset_stream_state(self) -> None:
        self._stream_text_buffer = ""
        self._trigger_detected = False
        self._delay_baseline = None
        self._packet_loss_count = 0

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

        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            self._emit("stream.hex", payload={"hex": data.hex(), "size": len(data)})
            return

        self._emit("stream.text", payload={"text": text})
        self._consume_metrics_text(text)

    def _consume_metrics_text(self, text: str) -> None:
        self._stream_text_buffer += text

        if not self._trigger_detected and TRIGGER_PATTERN.search(self._stream_text_buffer):
            self._trigger_detected = True
            self._emit("trigger.detected", payload={"reason": "keyword matched"})

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

            self._emit(
                "metric.offset_delay",
                payload={
                    "offset": offset,
                    "delay": delay,
                    "offset_raw": offset_raw,
                    "delay_raw": delay_raw,
                },
            )

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
                continue

            if (has_offset and not has_delay) or (has_delay and not has_offset):
                keep_tail.append(line + "\n")

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

        if req.req_type in {"record.start", "record.stop"}:
            self._emit_error(req.req_id, "NOT_IMPLEMENTED", f"{req.req_type} is planned in next phase-2 step")
            return

        if req.req_type == "app.shutdown":
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
