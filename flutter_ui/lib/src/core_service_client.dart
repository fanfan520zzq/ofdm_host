import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'models.dart';

class CoreServiceClient {
  Process? _process;
  final StreamController<CoreEvent> _eventController =
      StreamController<CoreEvent>.broadcast();
  final StreamController<String> _stderrController =
      StreamController<String>.broadcast();

  int _requestCounter = 0;

  Stream<CoreEvent> get events => _eventController.stream;
  Stream<String> get stderrLines => _stderrController.stream;
  bool get isRunning => _process != null;

  String _nextId() {
    _requestCounter += 1;
    return 'req-${DateTime.now().microsecondsSinceEpoch}-$_requestCounter';
  }

  Future<void> start({
    required String pythonExecutable,
    required String coreScriptPath,
    double heartbeatSeconds = 5,
  }) async {
    if (_process != null) {
      return;
    }

    final process = await Process.start(
      pythonExecutable,
      <String>[
        coreScriptPath,
        '--heartbeat-seconds',
        heartbeatSeconds.toString(),
      ],
      runInShell: true,
    );

    _process = process;

    process.stdout
        .transform(utf8.decoder)
        .transform(const LineSplitter())
        .listen(_handleStdoutLine, onDone: _handleProcessDone);

    process.stderr
        .transform(utf8.decoder)
        .transform(const LineSplitter())
        .listen(_stderrController.add);
  }

  Future<void> stop() async {
    final process = _process;
    if (process == null) {
      return;
    }

    send(type: 'app.shutdown', payload: <String, dynamic>{});
    await Future<void>.delayed(const Duration(milliseconds: 120));

    process.kill(ProcessSignal.sigterm);
    _process = null;
  }

  String send({
    required String type,
    required Map<String, dynamic> payload,
    String? id,
  }) {
    final process = _process;
    if (process == null) {
      throw StateError('Core service is not running');
    }

    final reqId = id ?? _nextId();
    final message = <String, dynamic>{
      'id': reqId,
      'type': type,
      'payload': payload,
    };

    process.stdin.writeln(jsonEncode(message));
    return reqId;
  }

  String init() => send(type: 'app.init', payload: <String, dynamic>{});

  String listPorts() => send(type: 'serial.list_ports', payload: <String, dynamic>{});

  String openRealSerial({required String port, required int baudrate}) {
    return send(
      type: 'serial.open',
      payload: <String, dynamic>{
        'mode': 'real',
        'port': port,
        'baudrate': baudrate,
      },
    );
  }

  String openSimulateSerial({
    required String simulateFile,
    required int baudrate,
  }) {
    return send(
      type: 'serial.open',
      payload: <String, dynamic>{
        'mode': 'simulate',
        'file': simulateFile,
        'baudrate': baudrate,
      },
    );
  }

  String closeSerial() => send(type: 'serial.close', payload: <String, dynamic>{});

  void _handleStdoutLine(String line) {
    if (line.trim().isEmpty) {
      return;
    }

    try {
      final event = CoreEvent.fromLine(line);
      _eventController.add(event);
    } catch (_) {
      _stderrController.add('invalid core stdout line: $line');
    }
  }

  void _handleProcessDone() {
    _process = null;
  }

  Future<void> dispose() async {
    await stop();
    await _eventController.close();
    await _stderrController.close();
  }
}
