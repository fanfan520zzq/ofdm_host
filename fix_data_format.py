"""修复 RX 串口格式数据，将截断的 offset/delay 正确拼接到一行。"""
import re
import sys
from pathlib import Path


def fix_rx_format(input_file, output_file=None):
    if output_file is None:
        output_file = input_file

    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    timestamp_re = re.compile(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]')
    rx_re = re.compile(r'RX：(.*)')

    # Step 1: 收集所有 (timestamp, rx_text) 片段
    lines = content.split('\n')
    segments = []   # [(timestamp, text), ...]
    current_ts = None

    for line in lines:
        ts_m = timestamp_re.search(line)
        if ts_m:
            current_ts = ts_m.group(1)
        rx_m = rx_re.search(line)
        if rx_m and current_ts:
            segments.append((current_ts, rx_m.group(1)))

    # Step 2: 拼成一条连续流，同时记录每个片段的起始位置
    stream = ''
    seg_positions = []   # [(start_pos, timestamp), ...]
    for ts, text in segments:
        seg_positions.append((len(stream), ts))
        stream += text

    def ts_at(pos):
        """返回流中 pos 位置对应的时间戳。"""
        result = seg_positions[0][1]
        for start, ts in seg_positions:
            if start <= pos:
                result = ts
            else:
                break
        return result

    # Step 3: 从流中提取完整的 offset:X  delay:Y 对
    # 支持 "de\nlay" 被拼回来的情况（拼接后流里就是连续的 delay:）
    pair_re = re.compile(
        r'offset\s*:\s*([-\d.]+)\s+delay\s*:\s*([-\d.]+)',
        re.IGNORECASE
    )

    results = []
    for m in pair_re.finditer(stream):
        ts = ts_at(m.start())
        results.append(f'[{ts}] offset:{m.group(1)}  delay:{m.group(2)}')

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(results) + '\n')

    print(f'✓ 共提取 {len(results)} 条记录，输出到: {output_file}')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python fix_rx_format.py 输入文件 [输出文件]')
        print('未指定输出文件则覆盖原文件')
        sys.exit(1)

    in_f = sys.argv[1]
    out_f = sys.argv[2] if len(sys.argv) > 2 else None
    fix_rx_format(in_f, out_f)