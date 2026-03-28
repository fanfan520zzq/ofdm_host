# OFDM Host 迁移进度

## 目标架构
- 前端：Flutter Desktop（Windows 优先）
- 核心：Python Core Service
- 通信：JSON Lines over stdin/stdout

## 阶段状态
- [x] 阶段 0：基线梳理（已阅读现有代码与文档）
- [x] 阶段 1：协议与骨架（进行中，已落地 core_service 最小可用版本）
- [ ] 阶段 2：采集闭环 MVP
- [ ] 阶段 3：数据可视化与统计
- [ ] 阶段 4：工程化与发布
- [ ] 阶段 5：灰度替换

## 阶段 1 交付清单
- [x] 新增 `core_service.py`（JSON Lines 服务）
- [x] 新增 `doc/ipc_protocol_v1.md`
- [x] 支持 `app.init` / `app.ping` / `serial.list_ports` / `app.shutdown`
- [x] 支持 `app.heartbeat` 服务端主动心跳
- [ ] Flutter 端 PoC 接入（待下一步）

## 下一步（阶段 2）
1. 在 Python Core 中接入 `serial.open/close`
2. 复用现有解析逻辑，实现 `trigger.detected` 与 `metric.offset_delay`
3. 增加 `record.start/stop` 并保持与旧版文件格式一致
4. 用 `historydata` 样本做回归对比
