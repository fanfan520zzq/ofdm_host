import 'dart:convert';

class CoreEvent {
  CoreEvent({
    required this.type,
    required this.timestamp,
    required this.payload,
    this.id,
    this.code,
    this.message,
    required this.rawLine,
  });

  final String type;
  final int timestamp;
  final Map<String, dynamic> payload;
  final String? id;
  final String? code;
  final String? message;
  final String rawLine;

  factory CoreEvent.fromLine(String line) {
    final decoded = jsonDecode(line);
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('Core event is not a json object');
    }

    final payload = decoded['payload'];
    return CoreEvent(
      id: decoded['id']?.toString(),
      type: decoded['type']?.toString() ?? 'unknown',
      timestamp: int.tryParse(decoded['ts']?.toString() ?? '') ?? 0,
      payload: payload is Map<String, dynamic> ? payload : <String, dynamic>{},
      code: decoded['code']?.toString(),
      message: decoded['message']?.toString(),
      rawLine: line,
    );
  }
}
