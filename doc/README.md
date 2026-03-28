 # 串口数据读取上位机（ofdm_host）
 基于 PyQt6 的串口采集工具，支持真实串口与模拟串口两种模式。程序可自动识别设备就绪信号、提取 offset/delay 数据并保存到历史文件，同时提供离线统计分析。
 ## 主要功能
 - 图形化选择串口与波特率
 - 支持真实串口采集（pyserial）
 - 支持模拟串口回放（从文本文件循环发送）
 - 识别触发信号后自动开始记录
 - 仅提取并规范化保存 offset/delay 记录
 - 支持定时自动停止
 - 支持历史数据文件一键分析（均值、收敛时间、最值）
 ## 运行环境
 - Python 3.10+
 - Windows（当前项目在 Windows 环境下使用）
 安装依赖：
 ```bash
 pip install -r requirements.txt
 ```
 `requirements.txt` 当前依赖：
 - PyQt6>=6.4.0
 - pyserial>=3.5

## 迁移进展（通俗版）

项目正在进行升级：把程序拆成“前台界面 + 后台服务”两部分。

这样做的好处是：后续界面迭代更快，但底层采集能力继续复用，不需要推翻重写。

目标再次确认：
- 前端：使用 Flutter 做更好看的上位机界面
- 后端：保留 Python 串口采集和 Python 算法

当前进度：
- 已新增后台服务入口：`core_service.py`
- 已打通启动确认、串口列表、心跳、正常关闭
- Phase 2 已完成：串口开关、实时事件流、record.start/stop 记录落盘
- Phase 3 已启动：实时双波形、日志过滤、离线分析面板已接入
- 已创建 Flutter 前端壳工程：`flutter_ui/`
- 现在仍可继续使用原有主程序 `main.py` 进行采集

迁移状态查看：
- 当前迁移版本：`MIGRATION_VERSION`
- 每次变更记录：`doc/migration_changelog.md`
- 阶段进度看板：`doc/migration_progress.md`

## 如果你只是使用者

- 继续运行：`python main.py`
- 当前采集与分析流程保持不变

## 如果你参与迁移联调

```bash
cd flutter_ui
flutter create .
flutter pub get
flutter run -d windows
```

如果提示没有 `flutter` 命令，说明本机还未安装 Flutter SDK。

Flutter 壳界面当前已支持：
- 启动/停止 Python 后端
- 打开/关闭串口（真实/模拟）
- 开始/停止记录（可选等待触发词）
- 实时查看事件流与关键指标
- 实时查看 offset/delay 双波形与均值/最值
- 波形时间窗切换、Y 轴缩放与自动/固定量程切换
- 日志关键词过滤与高亮（提升高流量可读性）
- 对历史文件执行离线统计分析（`file.process`）
- 导出离线分析结果（TXT / JSON）
- 自定义离线分析导出目录

## 自动版本留痕（每次大改）

项目已提供自动留痕脚本：`tools/migration_checkpoint.py`，每次阶段性改动后可自动记录版本、变更、提交和标签。

## 打包 EXE（Windows）

安装打包工具：

```bash
pip install pyinstaller
```

在项目根目录执行：

```bash
python -m PyInstaller --noconfirm --clean --name ofdm_host --windowed main.py
```

打包完成后可执行文件位置：

```text
dist/ofdm_host/ofdm_host.exe
```
 ## 项目结构
 ```text
 ofdm_host/
 ├── main.py              # GUI 主程序（采集控制 + 分析结果弹窗）
 ├── serial_reader.py     # 串口线程与模拟串口线程
 ├── process_data.py      # 离线分析脚本（解析 offset/delay）
 ├── fix_data_format.py   # RX 格式数据修复脚本
 ├── simulate_input.txt   # 模拟串口输入源
 ├── requirements.txt
 ├── historydata/         # 采集历史文件输出目录
 ├── test_regex.py        # 正则逻辑调试脚本
 └── test.txt             # 示例原始日志
 ```
 ## 快速开始
 ### 1) 启动图形界面
 ```bash
 python main.py
 ```
 ### 2) 选择模式并开始
 - 真实串口模式：选择串口与波特率，点击“开始”
 - 模拟串口模式：勾选“模拟串口模式”，点击“开始”
 - 可选定时：设置“定时(秒)”>0，超时后自动停止
- 可选剔除比例：设置“剔除前(%)”用于分析时过滤头部毛刺（默认 1%）
- 主界面提供“调试环境备注”输入框，停止采样时会自动将其内容写入文件最上方

右下角提供保存策略：

- 勾选“自动保存”：点击“保存设置”后选择保存根目录，程序会在该目录下创建 `historydata/`，并自动生成 `historydata/srcdata/`
- 不勾选“自动保存”：手动点击“停止”后会弹出“另存为”窗口，分别保存解析文本 txt 和原始二进制文本 txt
 ### 3) 触发后自动记录
 程序连接成功后不会立即写文件，而是先等待设备就绪触发关键词。检测到下列关键词之一后开始记录：
 - client start
 - join NET success
 - INF: ... HASCH ... Init OK
 - Time Slot index
自动保存模式下，触发后会在 `historydata` 目录生成文件：
 ```text
 historydata/YYYY-MM-DD_HH-mm-ss.txt
 ```

同时会在 `historydata/srcdata/` 生成同名原始数据文件：

```text
historydata/srcdata/YYYY-MM-DD_HH-mm-ss.txt
```

该文件为串口原始字节流直写，不加时间戳、不加备注、不做任何修正，便于追溯原始输入。
 ### 4) 分析历史文件
 两种方式：
 - GUI 中点击“数据处理”按钮并选择文件
 - 命令行运行：
 ```bash
 python process_data.py historydata/2026-03-14_16-05-21.txt
 ```
 ## 数据处理逻辑说明
 ### 采集阶段（main.py）
 - 实时接收串口字节流
 - UTF-8 可解码时，使用缓冲区跨行拼接并匹配 offset/delay 对
 - 自动修正常见断裂词（如 `of fset`、`d elay`）
 - 统一输出格式为：
 ```text
 [时间戳] offset:<数值>  delay:<数值>
 ```
- delay 写入前会执行标定：当前 delay 减去本次记录首条 delay（首条标定后为 0）
- 文件顶部的调试信息以 `#` 开头，不参与数据解析，不影响后续统计
 - 若遇到不可解码数据，会写入十六进制字符串
 ### 分析阶段（process_data.py）
 - 从文件中提取 offset 与 delay
 - 计算 offset 平均值、delay 平均值
 - 计算收敛时间：首次满足 `|offset| < 0.02` 的时刻，与起始时刻之差
 - 起始时刻优先使用 `client start`，若无则使用 `join NET success`，再无则使用第一条有效数据时间
 ## 模拟输入文件格式
 `simulate_input.txt` 每行作为一帧发送：
 - 以 `#` 开头的行为注释
 - 可写普通文本（按 UTF-8 发送）
 - 也可写十六进制字节（如 `01 02 03 04` 或 `01020304`）
 示例：
 ```text
 join NET success
 Time Slot index: 1 client start!
 offset:0.0001000  Delay:0.01000001
 ```
 ## 格式修复脚本
 当原始日志是 RX 前缀格式且存在跨行截断时，可使用：
 ```bash
 python fix_data_format.py 输入文件 [输出文件]
 ```
 说明：
 - 未指定输出文件时，默认覆盖输入文件
 - 该脚本当前针对形如 `RX：...` 的日志片段进行重组并提取
 - 输出仍为统一格式：`[时间戳] offset:x  delay:y`
 ## 常见问题
 ### 1. 点击开始后没有生成文件
 通常是尚未收到触发关键词。请确认设备日志中出现了 `client start` / `join NET success` 等关键字。
 ### 2. 串口已连接但无数据增长
 检查波特率是否匹配，或设备是否持续输出。也可先启用模拟模式验证软件链路。
 ### 3. 分析提示未找到有效数据
 目标文件中可能没有同时包含 `offset:` 和 `delay:` 的行，可先做格式修复后再分析。
 ## 备注
 当前仓库中只有 `fix_data_format.py`，并没有独立的 `fix_rx_format.py` 文件。历史文档如有该文件名，请以当前仓库实际文件为准。