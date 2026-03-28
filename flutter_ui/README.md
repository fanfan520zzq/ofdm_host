# Flutter UI Shell（Phase 2）

这是 OFDM Host 的 Flutter 前端壳工程（迁移中的 UI 层）。

当前状态：
- 已有桌面界面骨架（连接控制 + 实时事件流）
- 已可对接 Python `core_service.py`
- 后端串口和算法仍由 Python 负责

## 本地启动（需要先安装 Flutter SDK）

1. 进入目录

```bash
cd flutter_ui
```

2. 如果你本机还没有 platform 目录（windows/android 等），先补齐

```bash
flutter create .
```

3. 获取依赖

```bash
flutter pub get
```

4. 运行

```bash
flutter run -d windows
```

## 默认联调参数

- Python 命令：`python`
- Core 服务脚本：`../core_service.py`
- 模拟输入文件：`../simulate_input.txt`

可以在界面里直接改这 3 项。

## 说明

- 这是 Phase 2 的 UI 起步版本，重点是通信链路和状态展示。
- 后续会继续补齐波形、统计结果页、日志筛选等能力。
