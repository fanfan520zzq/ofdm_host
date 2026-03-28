# Phase 4 工程化与发布指南

本文档描述 Flutter + Python 双栈在 Phase 4 的标准联调和发布流程。

## 1. 目标

- 统一本地启动流程，减少环境差异导致的启动失败。
- 在发布前执行基础自检（路径、命令、关键文件）。
- 生成可交付的 Windows 发布目录（Flutter Runner + Python Core）。

## 2. 脚本清单

- `tools/phase4_preflight.py`
  - 作用：执行发布前检查。
  - 检查项：关键文件存在、Python 可用、Flutter 可用、PyInstaller 可用性提示。
- `tools/run_phase4_dev.ps1`
  - 作用：开发联调入口（先 preflight，再 flutter run）。
- `tools/build_phase4_release.ps1`
  - 作用：发布构建入口（先 preflight，再 analyze/test/build，并打包发布目录）。

## 3. 开发联调

在仓库根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\run_phase4_dev.ps1
```

常用参数：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\run_phase4_dev.ps1 -Device windows -PythonCmd python
powershell -ExecutionPolicy Bypass -File .\tools\run_phase4_dev.ps1 -SkipPubGet
```

## 4. 发布构建

在仓库根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_phase4_release.ps1
```

默认流程：

1. 执行 preflight。
2. 执行 `flutter pub get`。
3. 执行 `flutter analyze`。
4. 执行 `flutter test`。
5. 执行 `flutter build windows --release`。
6. 生成发布目录 `dist/phase4_bundle/`。

可选参数：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_phase4_release.ps1 -SkipAnalyze -SkipTests
powershell -ExecutionPolicy Bypass -File .\tools\build_phase4_release.ps1 -PythonCmd python
```

## 5. 发布目录说明

构建后产物位于 `dist/phase4_bundle/`，包含：

- Flutter Windows Runner 产物（exe + data + dll）。
- `python_core/`（`core_service.py` 及依赖脚本）。
- `start_ofdm_flutter.bat`（简化启动入口）。
- `phase4_bundle_manifest.txt`（发布清单）。
- `PHASE4_RELEASE_GUIDE.md`（当前文档副本）。

## 6. 首次运行建议

1. 先确认系统已安装 Python，并可通过 `python` 命令启动。
2. 运行 `start_ofdm_flutter.bat`。
3. 在 Flutter UI 中确认启动参数：
   - Python 命令：`python`
   - Core 脚本：`.\python_core\core_service.py`
   - 模拟文件：`.\python_core\simulate_input.txt`
4. 点击“启动服务”，观察日志是否通过启动前自检。

## 7. 回滚建议（进入 Phase 5 前）

- 如果新链路异常，仍可直接使用 `python main.py` 回到旧版 PyQt 主流程。
- 发布前建议保留最近一次稳定 tag（例如 `migration-v0.6.3`）。
