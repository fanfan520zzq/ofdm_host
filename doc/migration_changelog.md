# Migration Changelog

## v0.1.0
- 初始化迁移版本基线
- 建立 JSON Lines IPC 协议文档
- 建立 Python `core_service.py` 最小可用骨架

## v0.2.0
- 时间: 2026-03-28 11:13:38
- 阶段: phase-1
- 说明: core service scaffold and protocol v1
- 文件:
  - core_service.py
  - doc/ipc_protocol_v1.md
  - doc/migration_progress.md
  - tools/migration_checkpoint.py
  - README.md

## v0.3.0
- 时间: 2026-03-28 11:23:43
- 阶段: phase-2-start
- 说明: phase2 serial streaming and non-technical summary
- 文件:
  - core_service.py
  - doc/ipc_protocol_v1.md
  - doc/migration_progress.md
  - doc/migration_plan_vibecoding.md

## v0.4.0
- 时间: 2026-03-28 11:33:08
- 阶段: phase-2-ui-shell
- 说明: flutter ui shell scaffold and README sync
- 文件:
  - flutter_ui
  - README.md
  - doc/README.md
  - doc/migration_progress.md

## v0.5.0
- 时间: 2026-03-28 11:44:15
- 阶段: phase-2-complete
- 说明: record start-stop persistence and env audit
- 文件:
  - core_service.py
  - flutter_ui/lib/src/core_service_client.dart
  - flutter_ui/lib/src/app.dart
  - flutter_ui/README.md
  - README.md
  - doc/README.md
  - doc/ipc_protocol_v1.md
  - doc/migration_progress.md
  - doc/migration_plan_vibecoding.md

## v0.6.0
- 时间: 2026-03-28 22:01:51
- 阶段: phase-3-start
- 说明: phase3 visualization and file processing bridge
- 文件:
  - core_service.py
  - flutter_ui/lib/src/core_service_client.dart
  - flutter_ui/lib/src/app.dart
  - flutter_ui/README.md
  - README.md
  - doc/README.md
  - doc/ipc_protocol_v1.md
  - doc/migration_progress.md
  - doc/migration_plan_vibecoding.md

## v0.6.1
- 时间: 2026-03-28 22:09:25
- 阶段: phase-3-step2
- 说明: phase3 export zoom and highlight
- 文件:
  - flutter_ui/lib/src/app.dart
  - flutter_ui/README.md
  - README.md
  - doc/README.md
  - doc/migration_progress.md
  - doc/migration_plan_vibecoding.md

## v0.6.2
- 时间: 2026-03-28 22:19:07
- 阶段: phase-3-step3
- 说明: phase3 configurable export path and scale mode
- 文件:
  - flutter_ui/lib/src/app.dart
  - flutter_ui/test/widget_test.dart
  - flutter_ui/README.md
  - README.md
  - doc/README.md
  - doc/migration_progress.md
  - doc/migration_plan_vibecoding.md

## v0.6.3
- 时间: 2026-03-28 22:37:12
- 阶段: phase-3-step4
- 说明: phase3 export naming policy, independent fixed ranges, and log perf optimization
- 文件:
  - flutter_ui/lib/src/app.dart
  - README.md
  - doc/README.md
  - doc/migration_progress.md
  - doc/migration_plan_vibecoding.md
  - flutter_ui/README.md
  - ui.md

## v0.7.0
- 时间: 2026-03-28 23:08:00
- 阶段: phase-4-step1
- 说明: phase4 preflight and release scripts, startup path self-check, and release guide
- 文件:
  - flutter_ui/lib/src/app.dart
  - tools/phase4_preflight.py
  - tools/run_phase4_dev.ps1
  - tools/build_phase4_release.ps1
  - doc/phase4_release_guide.md
  - README.md
  - doc/README.md
  - doc/migration_progress.md
  - doc/migration_plan_vibecoding.md
  - flutter_ui/README.md
  - ui.md
  - MIGRATION_VERSION

## v0.7.1
- 时间: 2026-03-28 23:20:00
- 阶段: phase-4-debug-fix
- 说明: fix Windows preflight encoding and release script quote handling
- 文件:
  - tools/phase4_preflight.py
  - tools/build_phase4_release.ps1
  - doc/phase4_release_guide.md
  - README.md
  - ui.md

## v0.7.2
- 时间: 2026-03-28 23:35:00
- 阶段: phase-4-ui-refine
- 说明: remove standalone window bar, make header draggable, and apply rounded serial selector
- 文件:
  - flutter_ui/lib/src/app.dart
  - flutter_ui/lib/main.dart
  - ui.md
  - README.md

## v0.7.3
- 时间: 2026-03-28 23:50:00
- 阶段: phase-4-ui-polish
- 说明: apply rounded outer window boundary (radius=20) with clipping and transparent window background
- 文件:
  - flutter_ui/lib/main.dart
  - flutter_ui/lib/src/app.dart
  - ui.md
  - README.md
  - MIGRATION_VERSION
