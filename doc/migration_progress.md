# OFDM Host 迁移进度

## 目标架构
- 前端：Flutter Desktop（Windows 优先）
- 核心：Python Core Service
- 通信：JSON Lines over stdin/stdout

## 阶段状态
- [x] 阶段 0：基线梳理（已阅读现有代码与文档）
- [x] 阶段 1：协议与骨架（已完成）
- [x] 阶段 2：采集闭环 MVP（已完成）
- [ ] 阶段 3：数据可视化与统计
- [ ] 阶段 4：工程化与发布
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

## 下一步（阶段 3）
1. 在 Flutter 中补齐 offset 波形图与统计卡片
2. 将离线分析结果页面化并支持导出
3. 增加日志筛选/高亮，提升大流量可读性
