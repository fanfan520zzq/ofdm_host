# OFDM Host 迁移进度

## 目标架构
- 前端：Flutter Desktop（Windows 优先）
- 核心：Python Core Service
- 通信：JSON Lines over stdin/stdout

## 阶段状态
- [x] 阶段 0：基线梳理（已阅读现有代码与文档）
- [x] 阶段 1：协议与骨架（已完成）
- [x] 阶段 2：采集闭环 MVP（已完成）
- [x] 阶段 3：数据可视化与统计（已完成）
- [ ] 阶段 4：工程化与发布（进行中，step1 + 调试收敛已完成）
- [ ] 阶段 5：灰度替换

## 阶段 1 交付清单
- [x] 新增 `core_service.py`（JSON Lines 服务）
- [x] 新增 `doc/ipc_protocol_v1.md`
- [x] 支持 `app.init` / `app.ping` / `serial.list_ports` / `app.shutdown`
- [x] 支持 `app.heartbeat` 服务端主动心跳
- [x] Flutter 端 PoC 接入（已创建 `flutter_ui/` 壳工程）

## 阶段 2 完成项
1. 在 Python Core 中接入 `serial.open/close`（已完成）
2. 复用现有解析逻辑，实现 `trigger.detected` 与 `metric.offset_delay`（已完成）
3. 接入 `record.start/stop` 并完成文件落盘（已完成）
4. 模拟链路冒烟验证（已完成）

## Phase 2 当前已落地能力
- 新增 `serial.open`，支持 `real` 和 `simulate` 两种模式
- 新增 `serial.close`
- 新增实时流事件：`stream.text`、`stream.hex`
- 新增触发事件：`trigger.detected`
- 新增指标事件：`metric.offset_delay`、`metric.packet_loss`
- 新增记录会话：`record.start`、`record.stop`、`record.armed`、`record.started`、`record.stopped`
- 记录输出保持双文件结构：`historydata/*.txt` + `historydata/srcdata/*.txt`
- 新增 Flutter 前端壳工程（`flutter_ui/`）：连接控制 + 实时事件流 + 指标卡片

## 下一步（阶段 4）
1. 完成发布包实机验收（目标机器环境验证 + 启动参数固化）
2. 完成工程化打包联调（PyInstaller 旧链路与 Flutter 新链路并行验证）
3. 建立灰度切换与回滚验证清单（为阶段 5 做准备）

## Phase 3（启动）已落地能力
1. Python Core 新增 `file.process` 请求，返回 `process.result`
2. Flutter 已新增离线分析面板（文件路径 + trim 比例 + 结果卡片）
3. Flutter 已新增实时双波形（offset / delay）和统计卡片（mean/min/max）
4. Flutter 已支持日志关键词过滤，提升高流量可读性

## Phase 3（第二批）已落地能力
1. Flutter 已支持离线分析结果导出（TXT / JSON）
2. 导出目录已支持手动配置（默认 `analysis_exports/`）
3. 波形已支持时间窗切换（120/240/420/800/1200 点）
4. 波形已支持 Y 轴缩放倍率调节
5. 波形已支持自动量程 / 固定量程切换
6. 日志已支持关键词高亮（在过滤结果中突出命中片段）
7. 导出已支持命名模板与重名策略（自动重命名 / 覆盖 / 跳过）
8. 固定量程下已支持 offset / delay 独立坐标配置
9. 日志渲染已支持缓存过滤与限量展示（高流量性能优化）

## Phase 4（step1）已落地能力
1. 新增 `tools/phase4_preflight.py`，统一发布前自检（关键文件 + Python/Flutter/PyInstaller）
2. 新增 `tools/run_phase4_dev.ps1`，统一开发联调启动入口（preflight + flutter run）
3. 新增 `tools/build_phase4_release.ps1`，统一发布构建入口（preflight + analyze/test/build + bundle）
4. 新增 `doc/phase4_release_guide.md`，沉淀工程化流程和发布目录说明
5. Flutter UI 增加启动前路径自检与自动回退（core_service/simulate_input）

## Phase 4（调试与验收收敛）已落地能力
1. 修复 preflight 在 Windows 下的编码问题（UTF-8 + errors='replace'）。
2. 修复发布脚本中 bat 引号解析与 exe 自动选择逻辑。
3. 完成完整 release 构建并验证 `dist/phase4_bundle/` 产物完整性。
4. 完成窗口一体化 UI 调整：隐藏原生标题栏、顶部拖动 + 关闭按钮、串口大圆角。
5. 完成窗口外边界圆角裁剪（radius=20）与透明背景配合。
