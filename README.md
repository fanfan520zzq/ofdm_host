# 串口数据读取上位机

基于 PyQt6 的串口数据采集程序，支持真实串口与模拟串口，自动保存数据并提供分析工具。

## 项目结构

```
ofdm_host/
├── main.py              # 主程序（GUI）
├── serial_reader.py     # 串口/模拟串口工作线程
├── process_data.py      # 数据分析
├── fix_data_format.py   # 数据格式修复（无 RX 前缀）
├── fix_rx_format.py     # 数据格式修复（有 RX 前缀）
├── simulate_input.txt   # 模拟串口数据源
├── requirements.txt
└── historydata/         # 记录保存目录
```

## 安装

```bash
pip install -r requirements.txt
```

## 使用

### 1. 启动主程序

```bash
python main.py
```

选择串口和波特率，点击**开始**。程序检测到设备就绪信号（`client start` / `join NET success`）后自动开始记录，数据保存至 `historydata/YYYY-MM-DD_HH-mm-ss.txt`。

勾选**模拟串口模式**可不连接硬件，从 `simulate_input.txt` 按波特率节奏回放数据。**定时(秒)** 设置 >0 可在指定时间后自动停止。

### 2. 格式修复（如有数据截断）

串口缓冲区溢出会导致 offset/delay 数值跨行截断，修复后再分析：

```bash
# 标准格式（[时间戳] offset:X delay:Y）
python fix_data_format.py historydata/xxx.txt

# 含 RX 前缀格式（[时间戳] RX：offset:X delay:Y）
python fix_rx_format.py historydata/xxx.txt output.txt
```

### 3. 数据分析

```bash
python process_data.py historydata/2026-03-14_16-05-21.txt
```

输出 offset/delay 均值及收敛时间（从设备就绪到 `|offset| < 0.02` 的耗时）。也可在主程序界面点击**数据处理**按钮交互式查看结果。

## 模拟数据格式

`simulate_input.txt` 每行一条，`#` 开头为注释，支持 hex（`01 02 03`）或 UTF-8 文本：

```
[2026-03-14 15:00:00.000] join NET success
[2026-03-14 15:00:01.000] client start!
[2026-03-14 15:00:02.000] offset:0.0001  delay:82004.1234
```