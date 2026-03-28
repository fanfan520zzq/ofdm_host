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

## 2. 已实现请求（Phase 1）

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

## 5. 下一阶段扩展（Phase 2）
计划新增请求：
- `serial.open`
- `serial.close`
- `record.start`
- `record.stop`

计划新增事件：
- `serial.connected`
- `serial.disconnected`
- `trigger.detected`
- `stream.text`
- `stream.hex`
- `metric.offset_delay`
- `metric.packet_loss`
- `record.started`
- `record.stopped`
