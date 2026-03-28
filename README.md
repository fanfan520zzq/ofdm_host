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

我们正在把程序升级成“两层结构”：
- 前台界面：负责操作和显示
- 后台服务：负责串口采集、解析和数据保存

目标再次确认：
- 前端 UI：使用 Flutter，让上位机界面更现代、更清晰
- 后端能力：继续使用 Python 串口 + Python 算法（不改核心算法栈）

这次升级的目标是后续更容易扩展新界面，但不影响现在的采集流程。

当前进度：
- 新增后台服务入口：`core_service.py`
- 已能完成启动确认、串口列表查询、心跳保活、正常关闭
- Phase 2 已完成：支持 `serial.open/close`、实时事件流、`record.start/stop` 记录落盘
- Phase 3 已启动：支持实时 offset/delay 双波形、日志过滤、历史文件离线分析
- 已创建 Flutter 前端壳工程：`flutter_ui/`
- 现有主程序 `main.py` 仍可按原方式使用

迁移状态查看位置：
- 当前迁移版本：`MIGRATION_VERSION`
- 每次变更记录：`doc/migration_changelog.md`
- 阶段进度看板：`doc/migration_progress.md`
- 协议细节（给开发同学）：`doc/ipc_protocol_v1.md`

## 迁移目标完成度（截至 v0.6.3）

- 总目标：Flutter 前端 + Python Core Service + JSON Lines IPC
- 已完成阶段：阶段 0、阶段 1、阶段 2、阶段 3
- 待开始阶段：阶段 4（工程化与发布）、阶段 5（灰度替换）

当前已完成的关键能力：
- Python Core 支持服务启动/关闭、心跳、串口开关、记录控制、文件分析
- Flutter UI 支持连接控制、离线分析、实时双波形、日志过滤与高亮
- 离线分析支持 TXT/JSON 导出、导出目录与导出命名模板配置、重名覆盖策略
- 波形支持自动/固定量程切换，并支持固定量程下 offset/delay 独立坐标配置
- 日志高亮已支持缓存过滤与限量渲染，提升高流量场景性能

距离 README 目标仍待完成的步骤：
1. Phase 4：工程化发布（打包整合、启动与路径配置、发布流程）
2. Phase 5：灰度替换（并行运行、回滚预案、最终切换）

UI 现状基线文档：`ui.md`（后续 UI 修改将直接更新该文档）

## 如果你只关心日常使用

- 继续运行：`python main.py`
- 现有采集、保存、离线分析流程不变
- 历史文件仍在 `historydata/` 下

## 如果你参与联调测试

可单独启动后台服务（用于新界面对接验证）：

```bash
python core_service.py
```

Flutter 前端壳工程（Phase 3-Start）启动方式：

```bash
cd flutter_ui
flutter create .
flutter pub get
flutter run -d windows
```

说明：当前仓库已提供 Flutter 代码骨架；若本机未安装 Flutter SDK，请先安装 Flutter。

联调时可在 Flutter 界面直接操作：
- 启动/停止 Python Core Service
- 打开/关闭串口（真实或模拟）
- 开始/停止记录（支持“等待触发后再写文件”）
- 查看实时事件流和最新 offset/delay/丢包指标
- 查看实时 offset/delay 双波形与均值/最值统计
- 切换波形时间窗并调整 Y 轴缩放倍率
- 切换波形自动量程 / 固定量程策略
- 按关键词过滤日志（便于高流量调试）
- 对过滤日志中的关键词做高亮显示
- 对 `historydata/*.txt` 执行离线统计分析（trim + converge_time）
- 导出离线分析结果（TXT / JSON，默认输出到 `analysis_exports/`）
- 可在界面中自定义离线分析导出目录
- 可配置导出命名模板与重名策略（自动重命名 / 覆盖 / 跳过）
- 固定量程模式下可分别设置 offset 与 delay 的独立坐标范围
- 日志高亮使用缓存过滤与限量渲染，降低高流量场景卡顿

## 自动版本留痕（每次大改）

项目已配置自动留痕脚本：`tools/migration_checkpoint.py`。

每次阶段性大改后，它会自动做 4 件事：
- 升级迁移版本号（`MIGRATION_VERSION`）
- 追加变更记录（`doc/migration_changelog.md`）
- 创建一次 git 提交
- 打一个迁移标签（例如 `migration-v0.2.0`）

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
## 项目结构与文件职责

```text
ofdm_host/
├── .gitignore
├── README.md
├── ui.md
├── MIGRATION_VERSION
├── main.py
├── core_service.py
├── serial_reader.py
├── process_data.py
├── fix_data_format.py
├── ui_dark_demo.py
├── requirements.txt
├── ofdm_host.spec
├── simulate_input.txt
├── test_regex.py
├── test.txt
├── flutter_version.txt
├── flutter_exit.txt
├── ofdm_host - 快捷方式.lnk
├── tools/
│   └── migration_checkpoint.py
├── doc/
│   ├── README.md
│   ├── FLCLASH_UI_技术栈总结.md
│   ├── ipc_protocol_v1.md
│   ├── migration_progress.md
│   ├── migration_changelog.md
│   └── migration_plan_vibecoding.md
├── flutter_ui/
│   ├── pubspec.yaml
│   ├── lib/main.dart
│   ├── lib/src/app.dart
│   ├── lib/src/core_service_client.dart
│   ├── lib/src/models.dart
│   └── test/widget_test.dart
├── historydata/
│   ├── *.txt
│   └── srcdata/
├── build/
├── dist/
├── .venv/
├── .flutter-sdk/
├── __pycache__/
└── myapp/
```

### 根目录文件说明

- `README.md`：项目总览、运行方式、迁移进展与操作说明。
- `ui.md`：UI 设计与功能基线文档，后续 UI 修改统一在这里维护。
- `.gitignore`：Git 忽略规则，避免临时文件进入版本库。
- `MIGRATION_VERSION`：当前迁移版本号。
- `main.py`：旧版 PyQt6 主程序（当前稳定可用入口）。
- `core_service.py`：Python 后台核心服务，提供 JSON Lines IPC 给 Flutter。
- `serial_reader.py`：串口读取线程和模拟串口线程实现（旧版主流程依赖）。
- `process_data.py`：离线数据解析与统计计算（旧版与 Core `file.process` 复用）。
- `fix_data_format.py`：日志格式修复工具（处理 RX 截断/错位数据）。
- `ui_dark_demo.py`：PyQt 界面样式实验文件（不在主运行链路）。
- `requirements.txt`：Python 依赖列表。
- `ofdm_host.spec`：PyInstaller 打包配置。
- `simulate_input.txt`：模拟串口输入样例。
- `test_regex.py`：正则匹配调试脚本。
- `test.txt`：原始日志示例文件。
- `flutter_version.txt`：本地 Flutter 版本记录文件（环境辅助）。
- `flutter_exit.txt`：本地 Flutter 运行/退出辅助记录文件。
- `ofdm_host - 快捷方式.lnk`：Windows 快捷方式文件（本地使用）。

### 关键目录说明

- `tools/`：迁移流程工具脚本。
	- `migration_checkpoint.py`：自动做版本号升级、changelog 追加、git 提交与 tag。
- `doc/`：迁移和技术文档目录。
	- `README.md`：文档总览入口。
	- `FLCLASH_UI_技术栈总结.md`：UI 技术栈调研笔记（历史参考）。
	- `ipc_protocol_v1.md`：前后端 IPC 协议定义。
	- `migration_progress.md`：阶段进度与下一步计划。
	- `migration_changelog.md`：每次迁移 checkpoint 的变更记录。
	- `migration_plan_vibecoding.md`：完整迁移方案与风险评估。
- `flutter_ui/`：Flutter 桌面前端工程。
	- `lib/main.dart`：Flutter 入口。
	- `lib/src/app.dart`：主页面 UI、交互逻辑、波形/日志/分析面板。
	- `lib/src/core_service_client.dart`：与 Python Core 通信的 IPC 客户端。
	- `lib/src/models.dart`：核心事件模型与 JSON 解析。
	- `test/widget_test.dart`：Flutter 基础冒烟测试。
- `historydata/`：采集输出目录（解析后文本）。
- `historydata/srcdata/`：串口原始字节流文本。
- `build/`、`dist/`：构建与打包产物目录。
- `.venv/`、`.flutter-sdk/`：本地开发环境目录。
- `__pycache__/`：Python 字节码缓存目录。
- `myapp/`：本地试验目录（与当前主迁移链路无直接依赖）。

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