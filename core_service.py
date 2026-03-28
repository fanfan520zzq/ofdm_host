"""OFDM Host Python core service.

Phase 1 migration target:
- Keep legacy acquisition/parsing logic in Python
- Expose a stable JSON Lines IPC protocol for Flutter desktop UI

Transport:
- Read requests from stdin (one JSON object per line)
- Write responses/events to stdout (one JSON object per line)
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from typing import Any

from serial.tools import list_ports

PROTOCOL_VERSION = "1.0.0"
SERVICE_NAME = "ofdm-host-core"
SERVICE_VERSION = "0.1.0"
DEFAULT_HEARTBEAT_SECONDS = 5.0


@dataclass(slots=True)
class Request:
    req_id: str | None
    req_type: str
    payload: dict[str, Any]


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

        if req.req_type == "app.shutdown":
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
