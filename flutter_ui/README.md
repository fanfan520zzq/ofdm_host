# Flutter UI Shell（Phase 3-Start）

这是 OFDM Host 的 Flutter 前端壳工程（迁移中的 UI 层）。

当前状态：
- 已有桌面界面（连接控制 + 记录控制 + 实时事件流）
- 已支持 offset/delay 双波形与统计卡片（mean/min/max）
- 已支持波形时间窗切换与 Y 轴缩放
- 已支持自动量程 / 固定量程切换
- 已支持固定量程下 offset / delay 独立坐标配置
- 已支持日志关键词过滤 + 高亮
- 已支持日志高亮缓存过滤与限量渲染（高流量性能优化）
- 已支持离线文件分析（file.process -> process.result）
- 已支持离线分析结果导出（TXT / JSON）
- 已支持离线分析导出目录配置
- 已支持导出命名模板与重名策略（自动重命名 / 覆盖 / 跳过）
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

- 当前已完成 Phase 3 的 UI 收尾能力，可覆盖实时可视化、离线分析和导出策略场景。
- 界面可直接触发 `record.start` / `record.stop`，并展示记录文件路径。
- 下一阶段进入 Phase 4（工程化发布与打包联调）。
