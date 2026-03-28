import 'dart:async';
import 'dart:convert';

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
  final CoreServiceClient _client = CoreServiceClient();
  final TextEditingController _pythonPathController =
      TextEditingController(text: 'python');
  final TextEditingController _coreScriptController =
      TextEditingController(text: '../core_service.py');
  final TextEditingController _simulatePathController =
      TextEditingController(text: '../simulate_input.txt');

  final List<String> _logLines = <String>[];
  final List<String> _ports = <String>[];

  StreamSubscription<CoreEvent>? _eventSub;
  StreamSubscription<String>? _stderrSub;

  bool _serviceRunning = false;
  bool _serialConnected = false;
  bool _simulateMode = true;
  String? _selectedPort;
  int _packetLoss = 0;
  double? _lastOffset;
  double? _lastDelay;
  String _statusText = '未连接';

  @override
  void dispose() {
    _eventSub?.cancel();
    _stderrSub?.cancel();
    _client.dispose();
    _pythonPathController.dispose();
    _coreScriptController.dispose();
    _simulatePathController.dispose();
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
          _statusText = '串口已断开';
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

      case 'error':
        final code = event.code ?? 'UNKNOWN';
        final msg = event.message ?? 'unknown error';
        setState(() {
          _statusText = '错误: $code';
        });
        _appendLog('ERROR($code): $msg');
        break;
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

  void _appendLog(String line) {
    final ts = DateTime.now().toIso8601String();
    final output = '[$ts] $line';

    setState(() {
      _logLines.insert(0, output);
      if (_logLines.length > 400) {
        _logLines.removeRange(400, _logLines.length);
      }
    });
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
                final compact = constraints.maxWidth < 1024;
                if (compact) {
                  return Column(
                    children: <Widget>[
                      _buildHeader(),
                      const SizedBox(height: 12),
                      _buildControlPanel(),
                      const SizedBox(height: 12),
                      Expanded(child: _buildLogPanel()),
                    ],
                  );
                }

                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    SizedBox(width: 360, child: _buildControlPanel()),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        children: <Widget>[
                          _buildHeader(),
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
        color: Colors.white.withOpacity(0.82),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFF0F7B7B).withOpacity(0.2)),
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
          _metricChip('丢包', _packetLoss.toString()),
          const SizedBox(width: 8),
          _metricChip('offset', _lastOffset?.toStringAsFixed(6) ?? '--'),
          const SizedBox(width: 8),
          _metricChip('delay', _lastDelay?.toStringAsFixed(6) ?? '--'),
        ],
      ),
    );
  }

  Widget _metricChip(String label, String value) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF102A43),
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
        color: Colors.white.withOpacity(0.86),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFE36F2D).withOpacity(0.2)),
      ),
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
              value: _selectedPort,
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
          Text(
            '当前串口数量: ${_ports.length}',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }

  Widget _buildLogPanel() {
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
          const SizedBox(height: 10),
          Expanded(
            child: ListView.builder(
              reverse: true,
              itemCount: _logLines.length,
              itemBuilder: (context, index) {
                final line = _logLines[index];
                final pretty = _tryPrettyJsonLine(line);
                return Container(
                  margin: const EdgeInsets.only(bottom: 6),
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.06),
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
