# OFDM Host IPC 协议 v1（JSON Lines）

## 1. 通信约定
- 传输层：`stdin/stdout`
- 编码：`UTF-8`
- 报文格式：每行一条 JSON（JSON Lines）
- 时间戳：`ts` 为毫秒时间戳（Unix ms）

统一字段：
- `id`: 请求 ID（可选，建议前端生成）
- `type`: 消息类型
- `ts`: 服务端生成时间戳
- `payload`: 业务数据对象
- `code`: 错误码（仅 error）
- `message`: 错误描述（仅 error）

## 2. 已实现请求（Phase 1 + Phase 2 + Phase 3-Start）

### 2.1 app.init
请求：
```json
{"id":"1","type":"app.init","payload":{}}
```
响应：
```json
{"id":"1","type":"app.ready","ts":1710000000000,"payload":{"service":"ofdm-host-core","service_version":"0.4.0","protocol_version":"1.0.0"}}
```

### 2.2 app.ping
请求：
```json
{"id":"2","type":"app.ping","payload":{}}
```
响应：
```json
{"id":"2","type":"app.pong","ts":1710000000001,"payload":{"service":"ofdm-host-core","service_version":"0.4.0","protocol_version":"1.0.0"}}
```

### 2.3 serial.list_ports
请求：
```json
{"id":"3","type":"serial.list_ports","payload":{}}
```
响应：
```json
{"id":"3","type":"serial.ports","ts":1710000000002,"payload":{"ports":[{"device":"COM3","name":"COM3","description":"USB Serial Device"}]}}
```

### 2.4 app.shutdown
请求：
```json
{"id":"4","type":"app.shutdown","payload":{}}
```
响应：
```json
{"id":"4","type":"app.stopped","ts":1710000000003,"payload":{"reason":"shutdown requested"}}
```

### 2.5 serial.open
请求（真实串口）：
```json
{"id":"5","type":"serial.open","payload":{"mode":"real","port":"COM3","baudrate":115200}}
```
请求（模拟串口）：
```json
{"id":"6","type":"serial.open","payload":{"mode":"simulate","file":"simulate_input.txt","baudrate":115200}}
```
响应：
```json
{"id":"5","type":"serial.connected","ts":1710000000004,"payload":{"mode":"real","port":"COM3","baudrate":115200}}
```

### 2.6 serial.close
请求：
```json
{"id":"7","type":"serial.close","payload":{}}
```
响应：
```json
{"id":"7","type":"serial.disconnected","ts":1710000000005,"payload":{"mode":"real","port":"COM3","reason":"closed by request"}}
```

### 2.7 record.start
请求（等待触发后开始记录）：
```json
{"id":"8","type":"record.start","payload":{"wait_trigger":true,"root_dir":".","note":"phase2 run"}}
```
响应（触发后真正进入记录状态）：
```json
{"id":"8","type":"record.started","ts":1710000000006,"payload":{"state":"recording","wait_trigger":true,"started_ts":"2026-03-28 11:41:20.901","parsed_path":"C:/repo/historydata/2026-03-28_11-41-20.txt","raw_path":"C:/repo/historydata/srcdata/2026-03-28_11-41-20.txt"}}
```

### 2.8 record.stop
请求：
```json
{"id":"9","type":"record.stop","payload":{}}
```
响应：
```json
{"id":"9","type":"record.stopped","ts":1710000000007,"payload":{"reason":"stopped by request","active":true,"parsed_path":"C:/repo/historydata/2026-03-28_11-41-20.txt","raw_path":"C:/repo/historydata/srcdata/2026-03-28_11-41-20.txt","records_written":120}}
```

### 2.9 file.process
请求（对历史文件做离线统计）：
```json
{"id":"10","type":"file.process","payload":{"file_path":"historydata/2026-03-14_16-05-21.txt","trim_ratio":0.01}}
```
响应（有数据）：
```json
{"id":"10","type":"process.result","ts":1710000000008,"payload":{"file_path":"C:/repo/historydata/2026-03-14_16-05-21.txt","trim_ratio":0.01,"has_data":true,"converge_time":3.245,"offset_stats":{"mean":0.000123,"min":-0.000321,"max":0.000456},"delay_stats":{"mean":0.001001,"min":0.0,"max":0.0019}}}
```
响应（无有效数据）：
```json
{"id":"10","type":"process.result","ts":1710000000008,"payload":{"file_path":"C:/repo/historydata/2026-03-14_16-05-21.txt","trim_ratio":0.01,"has_data":false,"message":"未找到有效 offset/delay 数据"}}
```

## 3. 服务端主动事件

### 3.1 app.ready
服务启动后主动发送一次：
```json
{"id":null,"type":"app.ready","ts":1710000000000,"payload":{"service":"ofdm-host-core","service_version":"0.4.0","protocol_version":"1.0.0"}}
```

### 3.2 app.heartbeat
默认每 5 秒发送一次（可通过启动参数关闭）：
```json
{"id":null,"type":"app.heartbeat","ts":1710000005000,"payload":{"service":"ofdm-host-core"}}
```

### 3.3 stream.text
可解码文本流事件（串口原文）：
```json
{"id":null,"type":"stream.text","ts":1710000005100,"payload":{"text":"offset:0.01 delay:0.1\n"}}
```

### 3.4 stream.hex
不可解码字节事件：
```json
{"id":null,"type":"stream.hex","ts":1710000005200,"payload":{"hex":"0a01ff","size":3}}
```

### 3.5 trigger.detected
命中触发关键词后发出：
```json
{"id":null,"type":"trigger.detected","ts":1710000005300,"payload":{"reason":"keyword matched"}}
```

### 3.6 metric.offset_delay
触发后解析到 offset/delay 时发出：
```json
{"id":null,"type":"metric.offset_delay","ts":1710000005400,"payload":{"offset":0.001,"delay":0.0,"offset_raw":"0.001","delay_raw":"0.01"}}
```

### 3.7 metric.packet_loss
检测到丢包标记（行内容为 10）时发出：
```json
{"id":null,"type":"metric.packet_loss","ts":1710000005500,"payload":{"count":1,"token":"10"}}
```

### 3.8 record.armed
调用 `record.start` 且配置为等待触发时，服务会先进入 armed 状态：
```json
{"id":"8","type":"record.armed","ts":1710000005600,"payload":{"wait_trigger":true,"root_dir":"C:/repo","armed_at_ms":1710000005600}}
```

### 3.9 record.started
满足触发条件并成功创建记录文件后发出：
```json
{"id":"8","type":"record.started","ts":1710000005700,"payload":{"state":"recording","wait_trigger":true,"started_ts":"2026-03-28 11:41:20.901","parsed_path":"C:/repo/historydata/2026-03-28_11-41-20.txt","raw_path":"C:/repo/historydata/srcdata/2026-03-28_11-41-20.txt"}}
```

### 3.10 record.stopped
记录停止后发出：
```json
{"id":"9","type":"record.stopped","ts":1710000005800,"payload":{"reason":"stopped by request","active":true,"parsed_path":"C:/repo/historydata/2026-03-28_11-41-20.txt","raw_path":"C:/repo/historydata/srcdata/2026-03-28_11-41-20.txt","records_written":120}}
```

### 3.11 process.result
收到 `file.process` 后发出（同请求响应体结构）：
```json
{"id":"10","type":"process.result","ts":1710000005900,"payload":{"file_path":"C:/repo/historydata/2026-03-14_16-05-21.txt","trim_ratio":0.01,"has_data":true,"converge_time":3.245,"offset_stats":{"mean":0.000123,"min":-0.000321,"max":0.000456},"delay_stats":{"mean":0.001001,"min":0.0,"max":0.0019}}}
```

## 4. 错误响应
统一错误类型：`type = "error"`

示例：
```json
{"id":"x1","type":"error","ts":1710000000004,"payload":{},"code":"UNKNOWN_TYPE","message":"unsupported request type: serial.open"}
```

当前错误码：
- `INVALID_JSON`: JSON 语法错误
- `INVALID_REQUEST`: 字段缺失或类型不合法
- `UNKNOWN_TYPE`: 未实现的消息类型
- `INTERNAL_ERROR`: 服务内部异常
- `SERIAL_ALREADY_OPEN`: 串口会话已存在
- `SERIAL_NOT_OPEN`: 当前没有活动串口会话
- `SERIAL_OPEN_FAILED`: 打开真实串口失败
- `SERIAL_READ_FAILED`: 串口读取异常
- `SIMULATE_FILE_NOT_FOUND`: 模拟输入文件不存在
- `SIMULATE_EMPTY`: 模拟输入文件没有有效数据
- `RECORD_NO_SERIAL`: 未连接串口时调用记录
- `RECORD_ALREADY_ACTIVE`: 已存在 armed 或 active 的记录会话
- `RECORD_NOT_ACTIVE`: 停止记录时没有活动会话
- `RECORD_OPEN_FAILED`: 创建记录文件失败
- `RECORD_WRITE_FAILED`: 记录文件写入失败
- `FILE_NOT_FOUND`: `file.process` 的目标文件不存在
- `PROCESS_FAILED`: 离线处理阶段异常

## 5. 当前扩展状态（截至 Phase 3-Start）
已实现能力：
- `serial.open`
- `serial.close`
- `serial.connected`
- `serial.disconnected`
- `trigger.detected`
- `stream.text`
- `stream.hex`
- `metric.offset_delay`
- `metric.packet_loss`
- `record.start`
- `record.stop`
- `record.armed`
- `record.started`
- `record.stopped`
- `file.process`
- `process.result`

完成说明：
- 已具备触发后记录 + stop 落盘的完整闭环
- 输出 parsed 与 raw 双文件结构（`historydata/` + `historydata/srcdata/`）
- 已支持历史文件离线统计（trim + mean/min/max + converge_time）
