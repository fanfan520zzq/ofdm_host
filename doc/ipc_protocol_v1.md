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

## 2. 已实现请求（Phase 1 + Phase 2 起步）

### 2.1 app.init
请求：
```json
{"id":"1","type":"app.init","payload":{}}
```
响应：
```json
{"id":"1","type":"app.ready","ts":1710000000000,"payload":{"service":"ofdm-host-core","service_version":"0.1.0","protocol_version":"1.0.0"}}
```

### 2.2 app.ping
请求：
```json
{"id":"2","type":"app.ping","payload":{}}
```
响应：
```json
{"id":"2","type":"app.pong","ts":1710000000001,"payload":{"service":"ofdm-host-core","service_version":"0.1.0","protocol_version":"1.0.0"}}
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

## 3. 服务端主动事件

### 3.1 app.ready
服务启动后主动发送一次：
```json
{"id":null,"type":"app.ready","ts":1710000000000,"payload":{"service":"ofdm-host-core","service_version":"0.1.0","protocol_version":"1.0.0"}}
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
- `NOT_IMPLEMENTED`: 预留接口尚未实现

## 5. 下一阶段扩展（Phase 2）
已实现：
- `serial.open`
- `serial.close`
- `serial.connected`
- `serial.disconnected`
- `trigger.detected`
- `stream.text`
- `stream.hex`
- `metric.offset_delay`
- `metric.packet_loss`

待实现：
- `record.start`
- `record.stop`
- `record.started`
- `record.stopped`
- 记录文件落盘与旧版格式对齐
