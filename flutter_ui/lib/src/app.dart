import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'core_service_client.dart';
import 'models.dart';

class OfdmHostApp extends StatelessWidget {
  const OfdmHostApp({super.key});

  @override
  Widget build(BuildContext context) {
    final base = ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: const Color(0xFFE36F2D),
        brightness: Brightness.light,
      ),
    );

    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'OFDM Host Flutter UI',
      theme: base.copyWith(
        textTheme: GoogleFonts.spaceGroteskTextTheme(base.textTheme),
        scaffoldBackgroundColor: const Color(0xFFF2EFE9),
      ),
      home: const _HomePage(),
    );
  }
}

class _HomePage extends StatefulWidget {
  const _HomePage();

  @override
  State<_HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<_HomePage> {
  static const int _maxWavePoints = 420;

  final CoreServiceClient _client = CoreServiceClient();

  final TextEditingController _pythonPathController =
      TextEditingController(text: 'python');
  final TextEditingController _coreScriptController =
      TextEditingController(text: '../core_service.py');
  final TextEditingController _simulatePathController =
      TextEditingController(text: '../simulate_input.txt');
  final TextEditingController _recordRootController =
      TextEditingController(text: '.');
  final TextEditingController _recordNoteController =
      TextEditingController(text: 'phase3 flutter ui run');
  final TextEditingController _analysisFileController = TextEditingController();
  final TextEditingController _logFilterController = TextEditingController();

  final List<String> _logLines = <String>[];
  final List<String> _ports = <String>[];
  final List<double> _offsetSeries = <double>[];
  final List<double> _delaySeries = <double>[];

  StreamSubscription<CoreEvent>? _eventSub;
  StreamSubscription<String>? _stderrSub;

  bool _serviceRunning = false;
  bool _serialConnected = false;
  bool _simulateMode = true;
  bool _recordWaitTrigger = true;
  bool _recordArmed = false;
  bool _recording = false;
  bool _analysisLoading = false;

  String? _selectedPort;
  String? _recordParsedPath;
  String? _recordRawPath;
  Map<String, dynamic>? _analysisResult;

  int _packetLoss = 0;
  double _analysisTrimRatio = 0.01;
  double? _lastOffset;
  double? _lastDelay;

  String _statusText = '未连接';
  String _analysisHint = '尚未分析历史文件';

  @override
  void dispose() {
    _eventSub?.cancel();
    _stderrSub?.cancel();
    _client.dispose();

    _pythonPathController.dispose();
    _coreScriptController.dispose();
    _simulatePathController.dispose();
    _recordRootController.dispose();
    _recordNoteController.dispose();
    _analysisFileController.dispose();
    _logFilterController.dispose();
    super.dispose();
  }

  Future<void> _startService() async {
    try {
      await _client.start(
        pythonExecutable: _pythonPathController.text.trim(),
        coreScriptPath: _coreScriptController.text.trim(),
      );

      _eventSub ??= _client.events.listen(_onEvent);
      _stderrSub ??= _client.stderrLines.listen((line) {
        _appendLog('STDERR: $line');
      });

      setState(() {
        _serviceRunning = true;
        _statusText = '服务已启动';
      });

      _client.init();
      _client.listPorts();
    } catch (e) {
      _appendLog('启动失败: $e');
    }
  }

  Future<void> _stopService() async {
    await _client.stop();
    setState(() {
      _serviceRunning = false;
      _serialConnected = false;
      _recordArmed = false;
      _recording = false;
      _analysisLoading = false;
      _statusText = '服务已停止';
    });
  }

  Future<void> _toggleSerial() async {
    if (!_serviceRunning) {
      _appendLog('请先启动服务');
      return;
    }

    if (_serialConnected) {
      _client.closeSerial();
      return;
    }

    if (_simulateMode) {
      _client.openSimulateSerial(
        simulateFile: _simulatePathController.text.trim(),
        baudrate: 115200,
      );
      return;
    }

    if (_ports.isEmpty) {
      _appendLog('无可用串口，请先刷新');
      return;
    }

    final port = _selectedPort ?? _ports.first;
    _client.openRealSerial(port: port, baudrate: 115200);
  }

  void _refreshPorts() {
    if (!_serviceRunning) {
      _appendLog('请先启动服务');
      return;
    }
    _client.listPorts();
  }

  void _toggleRecord() {
    if (!_serviceRunning) {
      _appendLog('请先启动服务');
      return;
    }
    if (!_serialConnected) {
      _appendLog('请先打开串口');
      return;
    }

    if (_recordArmed || _recording) {
      _client.stopRecord();
      return;
    }

    _client.startRecord(
      waitTrigger: _recordWaitTrigger,
      rootDir: _recordRootController.text.trim(),
      note: _recordNoteController.text.trim(),
    );
  }

  void _runFileAnalysis() {
    if (!_serviceRunning) {
      _appendLog('请先启动服务，再执行文件分析');
      return;
    }

    final path = _analysisFileController.text.trim();
    if (path.isEmpty) {
      _appendLog('请输入待分析文件路径');
      return;
    }

    setState(() {
      _analysisLoading = true;
      _analysisHint = '分析中...';
    });

    _client.processFile(
      filePath: path,
      trimRatio: _analysisTrimRatio,
    );
  }

  void _onEvent(CoreEvent event) {
    _appendLog(event.rawLine);

    switch (event.type) {
      case 'serial.ports':
        final portsPayload = event.payload['ports'];
        final nextPorts = <String>[];
        if (portsPayload is List) {
          for (final item in portsPayload) {
            if (item is Map<String, dynamic>) {
              final device = item['device']?.toString();
              if (device != null && device.isNotEmpty) {
                nextPorts.add(device);
              }
            }
          }
        }
        setState(() {
          _ports
            ..clear()
            ..addAll(nextPorts);
          if (_ports.isEmpty) {
            _selectedPort = null;
          } else if (_selectedPort == null || !_ports.contains(_selectedPort)) {
            _selectedPort = _ports.first;
          }
        });
        break;

      case 'serial.connected':
        setState(() {
          _serialConnected = true;
          _statusText = '串口已连接';
        });
        break;

      case 'serial.disconnected':
        setState(() {
          _serialConnected = false;
          _recordArmed = false;
          _recording = false;
          _statusText = '串口已断开';
        });
        break;

      case 'record.armed':
        setState(() {
          _recordArmed = true;
          _recording = false;
          _statusText = '记录已就绪，等待触发';
        });
        break;

      case 'record.started':
        setState(() {
          _recordArmed = false;
          _recording = true;
          _recordParsedPath = event.payload['parsed_path']?.toString();
          _recordRawPath = event.payload['raw_path']?.toString();
          _statusText = '记录中';
        });
        break;

      case 'record.stopped':
        setState(() {
          _recordArmed = false;
          _recording = false;
          _recordParsedPath = event.payload['parsed_path']?.toString();
          _recordRawPath = event.payload['raw_path']?.toString();
          _statusText = '记录已停止';
        });
        break;

      case 'trigger.detected':
        setState(() {
          _statusText = '触发词已命中';
        });
        break;

      case 'metric.offset_delay':
        final offset = _toDouble(event.payload['offset']);
        final delay = _toDouble(event.payload['delay']);
        setState(() {
          _lastOffset = offset;
          _lastDelay = delay;
          if (offset != null) {
            _appendWavePoint(_offsetSeries, offset);
          }
          if (delay != null) {
            _appendWavePoint(_delaySeries, delay);
          }
        });
        break;

      case 'metric.packet_loss':
        final count = event.payload['count'];
        final parsed = int.tryParse(count?.toString() ?? '');
        if (parsed != null) {
          setState(() {
            _packetLoss = parsed;
          });
        }
        break;

      case 'process.result':
        setState(() {
          _analysisLoading = false;
          _analysisResult = event.payload;
          final hasData = event.payload['has_data'] == true;
          _analysisHint = hasData
              ? '分析完成'
              : (event.payload['message']?.toString() ?? '文件无有效数据');
          _statusText = hasData ? '离线分析完成' : '离线分析完成(无有效数据)';
        });
        break;

      case 'error':
        final code = event.code ?? 'UNKNOWN';
        final msg = event.message ?? 'unknown error';
        if (code.startsWith('PROCESS_') ||
            code.startsWith('FILE_') ||
            code.startsWith('INVALID_TRIM_')) {
          setState(() {
            _analysisLoading = false;
            _analysisHint = '分析失败: $code';
          });
        }
        setState(() {
          _statusText = '错误: $code';
        });
        _appendLog('ERROR($code): $msg');
        break;
    }
  }

  void _appendWavePoint(List<double> series, double value) {
    series.add(value);
    if (series.length > _maxWavePoints) {
      series.removeRange(0, series.length - _maxWavePoints);
    }
  }

  double? _toDouble(Object? value) {
    if (value is num) {
      return value.toDouble();
    }
    if (value is String) {
      return double.tryParse(value);
    }
    return null;
  }

  String _fmtNum(Object? value, {int digits = 6}) {
    final d = _toDouble(value);
    if (d == null) {
      return '--';
    }
    return d.toStringAsFixed(digits);
  }

  void _appendLog(String line) {
    final ts = DateTime.now().toIso8601String();
    final output = '[$ts] $line';

    setState(() {
      _logLines.insert(0, output);
      if (_logLines.length > 600) {
        _logLines.removeRange(600, _logLines.length);
      }
    });
  }

  List<String> get _filteredLogs {
    final keyword = _logFilterController.text.trim().toLowerCase();
    if (keyword.isEmpty) {
      return _logLines;
    }
    return _logLines
        .where((line) => line.toLowerCase().contains(keyword))
        .toList(growable: false);
  }

  _SeriesStats? _calcStats(List<double> values) {
    if (values.isEmpty) {
      return null;
    }

    var minVal = values.first;
    var maxVal = values.first;
    var sum = 0.0;
    for (final v in values) {
      sum += v;
      if (v < minVal) {
        minVal = v;
      }
      if (v > maxVal) {
        maxVal = v;
      }
    }
    return _SeriesStats(
      mean: sum / values.length,
      min: minVal,
      max: maxVal,
      count: values.length,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: <Color>[Color(0xFFF8D3A7), Color(0xFFBDE6D8), Color(0xFFF2EFE9)],
          ),
        ),
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: LayoutBuilder(
              builder: (context, constraints) {
                final compact = constraints.maxWidth < 1100;

                if (compact) {
                  return Column(
                    children: <Widget>[
                      _buildHeader(),
                      const SizedBox(height: 12),
                      Expanded(
                        child: ListView(
                          children: <Widget>[
                            _buildControlPanel(),
                            const SizedBox(height: 12),
                            _buildVisualizationPanel(),
                            const SizedBox(height: 12),
                            SizedBox(height: 360, child: _buildLogPanel()),
                          ],
                        ),
                      ),
                    ],
                  );
                }

                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    SizedBox(width: 380, child: _buildControlPanel()),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        children: <Widget>[
                          _buildHeader(),
                          const SizedBox(height: 12),
                          SizedBox(height: 280, child: _buildVisualizationPanel()),
                          const SizedBox(height: 12),
                          Expanded(child: _buildLogPanel()),
                        ],
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 280),
      curve: Curves.easeOutCubic,
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.82),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: const Color(0xFF0F7B7B).withValues(alpha: 0.2),
        ),
      ),
      child: Row(
        children: <Widget>[
          const Icon(Icons.radar, size: 28, color: Color(0xFF0F7B7B)),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  'OFDM Host · Flutter 控制台',
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.w700,
                        color: const Color(0xFF102A43),
                      ),
                ),
                const SizedBox(height: 4),
                AnimatedSwitcher(
                  duration: const Duration(milliseconds: 250),
                  child: Text(
                    _statusText,
                    key: ValueKey<String>(_statusText),
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: const Color(0xFF334E68),
                        ),
                  ),
                ),
              ],
            ),
          ),
          _metricChip('丢包', _packetLoss.toString(),
              background: _packetLoss > 0
                  ? const Color(0xFF9E2A2B)
                  : const Color(0xFF102A43)),
          const SizedBox(width: 8),
          _metricChip('offset', _lastOffset?.toStringAsFixed(6) ?? '--'),
          const SizedBox(width: 8),
          _metricChip('delay', _lastDelay?.toStringAsFixed(6) ?? '--'),
        ],
      ),
    );
  }

  Widget _metricChip(String label, String value, {Color? background}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: background ?? const Color(0xFF102A43),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            label,
            style: const TextStyle(fontSize: 11, color: Color(0xFFBCCCDC)),
          ),
          Text(
            value,
            style: const TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w700,
              color: Colors.white,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildControlPanel() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.86),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: const Color(0xFFE36F2D).withValues(alpha: 0.2),
        ),
      ),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(
              '连接控制',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                    color: const Color(0xFF102A43),
                  ),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _pythonPathController,
              decoration: const InputDecoration(
                labelText: 'Python 命令',
                hintText: 'python 或绝对路径',
              ),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _coreScriptController,
              decoration: const InputDecoration(
                labelText: 'core_service.py 路径',
              ),
            ),
            const SizedBox(height: 10),
            SegmentedButton<bool>(
              segments: const <ButtonSegment<bool>>[
                ButtonSegment<bool>(value: false, label: Text('真实串口')),
                ButtonSegment<bool>(value: true, label: Text('模拟串口')),
              ],
              selected: <bool>{_simulateMode},
              onSelectionChanged: (selection) {
                setState(() {
                  _simulateMode = selection.first;
                });
              },
            ),
            const SizedBox(height: 10),
            if (_simulateMode)
              TextField(
                controller: _simulatePathController,
                decoration: const InputDecoration(
                  labelText: 'simulate_input.txt 路径',
                ),
              )
            else
              DropdownButtonFormField<String>(
                key: ValueKey<String?>(_selectedPort),
                initialValue: _selectedPort,
                decoration: const InputDecoration(labelText: '串口'),
                items: _ports
                    .map((port) => DropdownMenuItem<String>(
                          value: port,
                          child: Text(port),
                        ))
                    .toList(),
                onChanged: (value) {
                  setState(() {
                    _selectedPort = value;
                  });
                },
              ),
            const SizedBox(height: 14),
            Row(
              children: <Widget>[
                Expanded(
                  child: FilledButton.tonal(
                    onPressed: _serviceRunning ? _stopService : _startService,
                    child: Text(_serviceRunning ? '停止服务' : '启动服务'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: FilledButton(
                    onPressed: _toggleSerial,
                    child: Text(_serialConnected ? '关闭串口' : '打开串口'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton(
                onPressed: _refreshPorts,
                child: const Text('刷新串口列表'),
              ),
            ),
            const SizedBox(height: 10),
            Text('当前串口数量: ${_ports.length}'),
            const Divider(height: 24),
            Text(
              '记录控制',
              style: Theme.of(context).textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _recordRootController,
              decoration: const InputDecoration(
                labelText: '记录根目录（会生成 historydata）',
              ),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _recordNoteController,
              decoration: const InputDecoration(
                labelText: '记录备注（可选）',
              ),
            ),
            const SizedBox(height: 8),
            SwitchListTile.adaptive(
              contentPadding: EdgeInsets.zero,
              title: const Text('等待触发词后开始记录'),
              value: _recordWaitTrigger,
              onChanged: (value) {
                setState(() {
                  _recordWaitTrigger = value;
                });
              },
            ),
            SizedBox(
              width: double.infinity,
              child: FilledButton.tonal(
                onPressed: _toggleRecord,
                child: Text((_recordArmed || _recording) ? '停止记录' : '开始记录'),
              ),
            ),
            const SizedBox(height: 8),
            Text(
              '记录状态: ${_recording ? 'recording' : (_recordArmed ? 'armed' : 'idle')}',
            ),
            if (_recordParsedPath != null) ...<Widget>[
              const SizedBox(height: 6),
              Text(
                'parsed: $_recordParsedPath',
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
            if (_recordRawPath != null) ...<Widget>[
              const SizedBox(height: 4),
              Text(
                'raw: $_recordRawPath',
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
            const Divider(height: 24),
            Text(
              '离线分析',
              style: Theme.of(context).textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _analysisFileController,
              decoration: const InputDecoration(
                labelText: '数据文件路径',
                hintText: '../historydata/2026-03-14_16-05-21.txt',
              ),
            ),
            const SizedBox(height: 8),
            Text('剔除头部比例: ${(_analysisTrimRatio * 100).toStringAsFixed(2)}%'),
            Slider(
              value: _analysisTrimRatio,
              min: 0,
              max: 0.2,
              divisions: 40,
              label: '${(_analysisTrimRatio * 100).toStringAsFixed(2)}%',
              onChanged: (value) {
                setState(() {
                  _analysisTrimRatio = value;
                });
              },
            ),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: _analysisLoading ? null : _runFileAnalysis,
                child: Text(_analysisLoading ? '分析中...' : '分析文件'),
              ),
            ),
            const SizedBox(height: 8),
            Text(_analysisHint, style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 8),
            _buildAnalysisResultCard(),
          ],
        ),
      ),
    );
  }

  Widget _buildAnalysisResultCard() {
    final payload = _analysisResult;
    if (payload == null) {
      return const SizedBox.shrink();
    }

    final hasData = payload['has_data'] == true;
    if (!hasData) {
      return Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: const Color(0xFFF8EDE3),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Text(payload['message']?.toString() ?? '文件无有效数据'),
      );
    }

    final offsetStats = payload['offset_stats'];
    final delayStats = payload['delay_stats'];

    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFFEAF4F4),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('offset mean: ${_fmtNum(offsetStats is Map ? offsetStats['mean'] : null)}'),
          Text('offset min:  ${_fmtNum(offsetStats is Map ? offsetStats['min'] : null)}'),
          Text('offset max:  ${_fmtNum(offsetStats is Map ? offsetStats['max'] : null)}'),
          const SizedBox(height: 6),
          Text('delay mean: ${_fmtNum(delayStats is Map ? delayStats['mean'] : null)}'),
          Text('delay min:  ${_fmtNum(delayStats is Map ? delayStats['min'] : null)}'),
          Text('delay max:  ${_fmtNum(delayStats is Map ? delayStats['max'] : null)}'),
          const SizedBox(height: 6),
          Text('converge_time: ${_fmtNum(payload['converge_time'], digits: 3)} s'),
        ],
      ),
    );
  }

  Widget _buildVisualizationPanel() {
    final offsetStats = _calcStats(_offsetSeries);
    final delayStats = _calcStats(_delaySeries);

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.86),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: const Color(0xFF4A6FA5).withValues(alpha: 0.2),
        ),
      ),
      child: Column(
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(Icons.multiline_chart, color: Color(0xFF224870)),
              const SizedBox(width: 8),
              Text(
                '实时波形与统计',
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                      color: const Color(0xFF102A43),
                    ),
              ),
              const Spacer(),
              TextButton(
                onPressed: () {
                  setState(() {
                    _offsetSeries.clear();
                    _delaySeries.clear();
                  });
                },
                child: const Text('清空波形'),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Expanded(
            child: Row(
              children: <Widget>[
                Expanded(
                  child: _buildWaveCard(
                    title: 'offset',
                    values: _offsetSeries,
                    color: const Color(0xFF146EB4),
                    stats: offsetStats,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _buildWaveCard(
                    title: 'delay',
                    values: _delaySeries,
                    color: const Color(0xFFE36F2D),
                    stats: delayStats,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildWaveCard({
    required String title,
    required List<double> values,
    required Color color,
    required _SeriesStats? stats,
  }) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFFF7FAFC),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            '$title 波形',
            style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: CustomPaint(
              painter: _WaveformPainter(
                values: values,
                lineColor: color,
                emptyHint: '等待 $title 数据',
              ),
              child: const SizedBox.expand(),
            ),
          ),
          const SizedBox(height: 6),
          Text(
            stats == null
                ? 'mean --  min --  max --'
                : 'mean ${stats.mean.toStringAsFixed(6)}  min ${stats.min.toStringAsFixed(6)}  max ${stats.max.toStringAsFixed(6)}',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }

  Widget _buildLogPanel() {
    final filtered = _filteredLogs;

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF102A43),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(Icons.data_object, color: Color(0xFF9FB3C8)),
              const SizedBox(width: 8),
              Text(
                '实时事件流',
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.w700,
                    ),
              ),
              const Spacer(),
              TextButton(
                onPressed: () => setState(_logLines.clear),
                child: const Text('清空'),
              ),
            ],
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _logFilterController,
            onChanged: (_) => setState(() {}),
            style: const TextStyle(color: Colors.white),
            decoration: InputDecoration(
              hintText: '日志关键词过滤',
              hintStyle: const TextStyle(color: Color(0xFFAFC3D6)),
              filled: true,
              fillColor: Colors.white.withValues(alpha: 0.08),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: BorderSide.none,
              ),
            ),
          ),
          const SizedBox(height: 10),
          Expanded(
            child: ListView.builder(
              reverse: true,
              itemCount: filtered.length,
              itemBuilder: (context, index) {
                final line = filtered[index];
                final pretty = _tryPrettyJsonLine(line);
                return Container(
                  margin: const EdgeInsets.only(bottom: 6),
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.06),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(
                    pretty,
                    style: const TextStyle(
                      fontFamily: 'monospace',
                      fontSize: 12,
                      color: Color(0xFFE1EAF2),
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  String _tryPrettyJsonLine(String line) {
    final jsonStart = line.indexOf('{');
    if (jsonStart < 0) {
      return line;
    }

    final prefix = line.substring(0, jsonStart);
    final rawJson = line.substring(jsonStart);

    try {
      final decoded = jsonDecode(rawJson);
      const encoder = JsonEncoder.withIndent('  ');
      return '$prefix${encoder.convert(decoded)}';
    } catch (_) {
      return line;
    }
  }
}

class _SeriesStats {
  _SeriesStats({
    required this.mean,
    required this.min,
    required this.max,
    required this.count,
  });

  final double mean;
  final double min;
  final double max;
  final int count;
}

class _WaveformPainter extends CustomPainter {
  _WaveformPainter({
    required this.values,
    required this.lineColor,
    required this.emptyHint,
  });

  final List<double> values;
  final Color lineColor;
  final String emptyHint;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final bgPaint = Paint()..color = const Color(0xFFEFF3F8);
    final borderPaint = Paint()
      ..color = const Color(0xFFD5DFEA)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;

    canvas.drawRRect(
      RRect.fromRectAndRadius(rect, const Radius.circular(10)),
      bgPaint,
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(rect, const Radius.circular(10)),
      borderPaint,
    );

    final plot = Rect.fromLTWH(10, 10, math.max(0, size.width - 20), math.max(0, size.height - 20));
    if (plot.width <= 0 || plot.height <= 0) {
      return;
    }

    final gridPaint = Paint()
      ..color = const Color(0xFFDDE5F0)
      ..strokeWidth = 1;
    for (var i = 1; i < 6; i++) {
      final y = plot.top + plot.height * i / 6;
      canvas.drawLine(Offset(plot.left, y), Offset(plot.right, y), gridPaint);
    }

    if (values.length < 2) {
      final tp = TextPainter(
        text: TextSpan(
          text: emptyHint,
          style: const TextStyle(color: Color(0xFF6B7C93), fontSize: 12),
        ),
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: plot.width);
      tp.paint(canvas, Offset(plot.left + 8, plot.center.dy - tp.height / 2));
      return;
    }

    var maxAbs = 0.001;
    for (final v in values) {
      maxAbs = math.max(maxAbs, v.abs());
    }

    final sampled = <double>[];
    final targetCount = plot.width.clamp(2, 800).toInt();
    if (values.length <= targetCount) {
      sampled.addAll(values);
    } else {
      final step = values.length / targetCount;
      var idx = 0.0;
      while (idx < values.length) {
        sampled.add(values[idx.floor()]);
        idx += step;
      }
      sampled.add(values.last);
    }

    final points = <Offset>[];
    for (var i = 0; i < sampled.length; i++) {
      final x = plot.left + (plot.width * i / (sampled.length - 1));
      final yNorm = (sampled[i] + maxAbs) / (2 * maxAbs);
      final y = plot.bottom - yNorm * plot.height;
      points.add(Offset(x, y));
    }

    final path = Path()..moveTo(points.first.dx, points.first.dy);
    for (var i = 1; i < points.length; i++) {
      path.lineTo(points[i].dx, points[i].dy);
    }

    final linePaint = Paint()
      ..color = lineColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.8
      ..isAntiAlias = true;
    canvas.drawPath(path, linePaint);
  }

  @override
  bool shouldRepaint(covariant _WaveformPainter oldDelegate) {
    return oldDelegate.values != values ||
        oldDelegate.lineColor != lineColor ||
        oldDelegate.emptyHint != emptyHint;
  }
}
