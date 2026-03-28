"""Create a migration checkpoint commit and tag.

Usage example:
python tools/migration_checkpoint.py \
  --stage phase-1 \
  --message "core service scaffold" \
  --bump minor \
  --include core_service.py doc/ipc_protocol_v1.md doc/migration_progress.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
from pathlib import Path

VERSION_FILE = Path("MIGRATION_VERSION")
CHANGELOG_FILE = Path("doc/migration_changelog.md")


def run_git(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        check=check,
        text=True,
        capture_output=True,
    )


def ensure_git_repo() -> None:
    run_git(["rev-parse", "--is-inside-work-tree"])


def parse_version(version: str) -> tuple[int, int, int]:
    parts = version.strip().split(".")
    if len(parts) != 3:
        raise ValueError(f"invalid semantic version: {version}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def bump_version(version: str, level: str) -> str:
    major, minor, patch = parse_version(version)
    if level == "major":
        major += 1
        minor = 0
        patch = 0
    elif level == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1
    return f"{major}.{minor}.{patch}"


def append_changelog(new_version: str, stage: str, message: str, include_files: list[str]) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"\n## v{new_version}",
        f"- 时间: {ts}",
        f"- 阶段: {stage}",
        f"- 说明: {message}",
        "- 文件:",
    ]
    for p in include_files:
        lines.append(f"  - {p}")
    with CHANGELOG_FILE.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def ensure_files_exist(paths: list[str]) -> None:
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        raise FileNotFoundError(f"include paths not found: {missing}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create migration checkpoint commit/tag")
    parser.add_argument("--stage", required=True, help="stage label, e.g. phase-1")
    parser.add_argument("--message", required=True, help="checkpoint summary")
    parser.add_argument(
        "--bump",
        choices=["major", "minor", "patch"],
        default="minor",
        help="semantic version bump level",
    )
    parser.add_argument(
        "--include",
        nargs="+",
        required=True,
        help="files to include in this checkpoint commit",
    )
    parser.add_argument("--dry-run", action="store_true", help="preview only")
    args = parser.parse_args()

    ensure_git_repo()

    if not VERSION_FILE.exists():
        raise FileNotFoundError("MIGRATION_VERSION not found")

    if not CHANGELOG_FILE.exists():
        raise FileNotFoundError("doc/migration_changelog.md not found")

    ensure_files_exist(args.include)

    current_version = VERSION_FILE.read_text(encoding="utf-8").strip()
    new_version = bump_version(current_version, args.bump)
    tag_name = f"migration-v{new_version}"

    print(f"current version: {current_version}")
    print(f"next version:    {new_version}")
    print(f"tag:             {tag_name}")

    if args.dry_run:
        print("dry-run enabled, no changes applied")
        return 0

    VERSION_FILE.write_text(new_version + "\n", encoding="utf-8")
    append_changelog(new_version, args.stage, args.message, args.include)

    stage_targets = [*args.include, str(VERSION_FILE), str(CHANGELOG_FILE)]
    run_git(["add", *stage_targets])

    commit_message = f"migration: {args.stage} v{new_version} - {args.message}"
    run_git(["commit", "-m", commit_message])
    run_git(["tag", "-a", tag_name, "-m", commit_message])

    print("checkpoint created")
    print(f"commit: {commit_message}")
    print(f"tag:    {tag_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
