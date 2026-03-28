# FlClash 项目 UI 设计风格与技术栈总结

## 1. UI 设计风格总结

### 1.1 整体设计语言
- 核心设计语言是 Material You / Material 3，应用层直接启用 `useMaterial3: true`，并对导航栏、按钮、滑块等组件做了 M3 风格定制。
- 视觉目标偏向「工具型产品」：信息密度较高、状态反馈明确、操作层级清晰，强调可读性和效率，而非装饰性。
- README 明确标注为类 Surfboard 的界面风格，实际代码也体现为偏卡片化、分区明确、功能入口清楚的结构。

### 1.2 色彩与主题策略
- 支持亮色/暗色主题，并提供 pure black（纯黑）模式，暗色模式在 OLED 场景下更省电。
- 主题色方案由 ColorScheme 驱动，同时结合动态配色能力（dynamic_color / material_color_utilities）进行拓展。
- 颜色工具层提供 opacity、明暗混合、色值转换等扩展，说明项目对跨主题可读性和层级对比有系统化处理。

### 1.3 布局与响应式风格
- 采用多端自适应：移动端与桌面端导航形态不同。
- 移动端以底部 NavigationBar 为主，桌面端以左侧 NavigationRail + 内容区分栏为主。
- 通过 ViewMode（mobile/laptop/desktop）和宽度阈值控制页面组织，说明布局不是简单拉伸，而是模式切换。

### 1.4 交互与信息架构
- 首页是多页面容器（PageView + Provider 状态），页面切换可选动画/跳转，保证性能与体验平衡。
- 弹层采用自适应策略：移动端优先 bottom sheet，桌面端优先 side sheet；同一业务在不同设备保持接近的操作语义。
- 桌面端集成托盘、快捷键、窗口管理等能力，交互更偏「常驻工具应用」而非一次性移动 App。

### 1.5 文案、字体与国际化
- 使用 Flutter 本地化体系与 ARB 资源，覆盖中/英/日/俄等多语言。
- 字体资源包含 JetBrainsMono、Twemoji 和自定义图标字体，兼顾代码/网络工具场景下的数字可读性与图标表达。

## 2. 技术栈总结

### 2.1 客户端主栈（UI 层）
- 语言与框架：Dart + Flutter（Material 3）。
- 状态管理：Riverpod 3 + riverpod_annotation（大量 provider + 代码生成）。
- 序列化与不可变模型：freezed + json_serializable。
- 网络与系统能力：dio、connectivity_plus、device_info_plus、url_launcher、app_links。
- 桌面增强：window_manager、tray_manager、hotkey_manager、screen_retriever、launch_at_startup。

### 2.2 数据与本地持久化
- 本地数据库：drift + drift_flutter（SQLite 抽象层），包含 profiles/scripts/rules/link 等结构化数据。
- 偏轻量设置：shared_preferences。
- 文件与缓存：file_picker、archive、flutter_cache_manager。

### 2.3 核心代理引擎与跨语言桥接
- 核心代理能力由 Go 实现（core 目录），依赖 mihomo（Clash.Meta）并通过本地 replace 指向子模块。
- Go 侧存在 cgo 构建分支，导出如 startTUN、invokeAction、getTraffic、getTotalTraffic 等接口。
- Flutter 侧通过 core 控制层与插件层对接核心能力，形成「Flutter UI + Go 网络核心」的双层架构。

### 2.4 平台与工程化
- 目标平台：Android / Windows / macOS / Linux。
- 构建体系：Flutter + Dart 构建脚本（setup.dart）+ 各平台原生工程（android、windows、linux、macos）。
- 插件组织：仓库内含自定义插件（proxy、tray_manager、window_ext、flutter_distributor），说明项目对平台细节有较深定制。

### 2.5 国际化与多语言
- 国际化方案：flutter_localizations + intl + ARB 资源编排。
- 资源组织明确：arb 目录存放多语言词条，lib/l10n 存放生成代码。

## 3. 架构特征（一句话）
- FlClash 是一个以 Flutter 为 UI 外壳、以 Go/mihomo 为网络核心、以 Riverpod + Drift 组织状态和数据、并深度适配桌面与移动交互差异的多平台代理客户端。

## 4. 关键参考文件
- README 与定位说明：README.md、README_zh_CN.md
- 应用入口与主题注入：lib/main.dart、lib/application.dart
- 首页与导航布局：lib/pages/home.dart、lib/manager/app_manager.dart
- 自适应弹层：lib/widgets/sheet.dart
- 状态与配置：lib/providers/app.dart、lib/providers/config.dart、lib/providers/state.dart
- 主题与色彩扩展：lib/common/theme.dart、lib/common/color.dart
- 核心 Go 模块：core/go.mod、core/lib.go、core/main_cgo.go
- 数据层：lib/database/database.dart
- 工程依赖清单：pubspec.yaml
