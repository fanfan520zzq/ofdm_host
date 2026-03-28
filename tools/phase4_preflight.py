#!/usr/bin/env python3
"""Phase 4 preflight checks for OFDM Host engineering/release workflow."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Tuple


@dataclass
class CheckResult:
    name: str
    required: bool
    ok: bool
    detail: str
    suggestion: str = ""


def _run_command(command: str, args: List[str], cwd: Path) -> Tuple[bool, str]:
    try:
        if " " in command.strip():
            cmdline = " ".join([command, *args])
            completed = subprocess.run(
                cmdline,
                cwd=str(cwd),
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )
        else:
            completed = subprocess.run(
                [command, *args],
                cwd=str(cwd),
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )
    except FileNotFoundError:
        return False, f"command not found: {command}"
    except subprocess.TimeoutExpired:
        return False, f"timeout: {command} {' '.join(args)}"
    except Exception as exc:  # pylint: disable=broad-except
        return False, f"run error: {exc}"

    first_line = (completed.stdout or completed.stderr or "").strip().splitlines()
    message = first_line[0] if first_line else "(no output)"
    if completed.returncode == 0:
        return True, message
    return False, f"exit={completed.returncode}, {message}"


def _check_file(repo_root: Path, rel_path: str, required: bool = True) -> CheckResult:
    path = repo_root / rel_path
    if path.exists():
        return CheckResult(
            name=f"file:{rel_path}",
            required=required,
            ok=True,
            detail="found",
        )

    return CheckResult(
        name=f"file:{rel_path}",
        required=required,
        ok=False,
        detail="missing",
        suggestion=f"ensure {rel_path} exists under {repo_root}",
    )


def _default_flutter_cmd(repo_root: Path) -> str:
    local_flutter = repo_root / ".flutter-sdk" / "bin" / "flutter.bat"
    if local_flutter.exists():
        return str(local_flutter)
    return "flutter"


def run_preflight(repo_root: Path, python_cmd: str, flutter_cmd: str) -> List[CheckResult]:
    results: List[CheckResult] = []

    required_files = [
        "core_service.py",
        "process_data.py",
        "serial_reader.py",
        "flutter_ui/pubspec.yaml",
        "flutter_ui/lib/src/app.dart",
        "tools/migration_checkpoint.py",
    ]
    optional_files = [
        "simulate_input.txt",
        "flutter_ui/windows/CMakeLists.txt",
        "ofdm_host.spec",
    ]

    for rel_path in required_files:
        results.append(_check_file(repo_root, rel_path, required=True))
    for rel_path in optional_files:
        results.append(_check_file(repo_root, rel_path, required=False))

    ok, detail = _run_command(python_cmd, ["--version"], cwd=repo_root)
    results.append(
        CheckResult(
            name="command:python --version",
            required=True,
            ok=ok,
            detail=detail,
            suggestion="install Python or pass --python-cmd with a valid interpreter",
        )
    )

    ok, detail = _run_command(flutter_cmd, ["--version"], cwd=repo_root)
    results.append(
        CheckResult(
            name="command:flutter --version",
            required=True,
            ok=ok,
            detail=detail,
            suggestion="install Flutter SDK or pass --flutter-cmd with a valid flutter executable",
        )
    )

    ok, detail = _run_command(python_cmd, ["-m", "PyInstaller", "--version"], cwd=repo_root)
    results.append(
        CheckResult(
            name="command:python -m PyInstaller --version",
            required=False,
            ok=ok,
            detail=detail,
            suggestion="install with: pip install pyinstaller",
        )
    )

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run phase4 engineering preflight checks.")
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Repository root path",
    )
    parser.add_argument(
        "--python-cmd",
        default="python",
        help="Python command used to run scripts",
    )
    parser.add_argument(
        "--flutter-cmd",
        default="",
        help="Flutter executable path or command",
    )
    parser.add_argument(
        "--strict-warnings",
        action="store_true",
        help="Fail if optional checks fail",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    flutter_cmd = args.flutter_cmd.strip() or _default_flutter_cmd(repo_root)
    results = run_preflight(repo_root, args.python_cmd.strip(), flutter_cmd)

    required_failed = [item for item in results if item.required and not item.ok]
    optional_failed = [item for item in results if (not item.required) and (not item.ok)]

    if args.json:
        payload = {
            "repo_root": str(repo_root),
            "python_cmd": args.python_cmd,
            "flutter_cmd": flutter_cmd,
            "required_failed": len(required_failed),
            "optional_failed": len(optional_failed),
            "checks": [asdict(item) for item in results],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("== OFDM Host Phase4 Preflight ==")
        print(f"repo_root: {repo_root}")
        print(f"python_cmd: {args.python_cmd}")
        print(f"flutter_cmd: {flutter_cmd}")
        for item in results:
            if item.ok:
                level = "PASS"
            else:
                level = "FAIL" if item.required else "WARN"
            print(f"[{level}] {item.name}: {item.detail}")
            if (not item.ok) and item.suggestion:
                print(f"  -> {item.suggestion}")

        print(
            f"summary: required_failed={len(required_failed)}, "
            f"optional_failed={len(optional_failed)}"
        )

    if required_failed:
        return 2
    if args.strict_warnings and optional_failed:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
