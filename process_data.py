"""
处理指定数据文件，计算 offset 和 Delay 的平均值，以及收敛时间。
收敛时间定义：offset 从一开始到首次小于 0.02 的时间差。
用法：python process_data.py 数据文件路径
"""
import sys
import re
from datetime import datetime

def parse_file(filepath):
    offsets = []
    delays = []
    offset_times = []
    start_time = None
    converge_time = None
    offset_converged = False
    time_pattern = re.compile(r"\[(.*?)\]")
    offset_pattern = re.compile(r"offset:([\d\.-]+)")
    delay_pattern = re.compile(r"Delay:([\d\.-]+)")
    
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            # 提取时间戳
            time_match = time_pattern.search(line)
            if time_match:
                ts_str = time_match.group(1)
                try:
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")
                except ValueError:
                    continue
            else:
                continue
            # 检查 join NET success 和 client start
            if "join NET success" in line and start_time is None:
                start_time = ts
            if start_time is not None and "client start" in line:
                start_time = ts  # 以 client start 为准
            # 只处理 offset/Delay 行
            if "offset:" in line and "Delay:" in line:
                offset_match = offset_pattern.search(line)
                delay_match = delay_pattern.search(line)
                if offset_match and delay_match:
                    offset = float(offset_match.group(1))
                    delay = float(delay_match.group(1))
                    offsets.append(offset)
                    delays.append(delay)
                    offset_times.append(ts)
                    # 收敛时间判断
                    if not offset_converged and abs(offset) < 0.02:
                        converge_time = (ts - start_time).total_seconds() if start_time else None
                        offset_converged = True
    return offsets, delays, converge_time

def main():
    if len(sys.argv) < 2:
        print("用法: python process_data.py 数据文件路径")
        return
    filepath = sys.argv[1]
    offsets, delays, converge_time = parse_file(filepath)
    if not offsets or not delays:
        print("未找到有效的 offset/Delay 数据！")
        return
    avg_offset = sum(offsets) / len(offsets)
    avg_delay = sum(delays) / len(delays)
    print(f"offset 平均值: {avg_offset:.6f}")
    print(f"Delay 平均值: {avg_delay:.6f}")
    if converge_time is not None:
        print(f"收敛时间: {converge_time:.3f} 秒")
    else:
        print("未检测到 offset 收敛到 <0.02 的时刻")

if __name__ == "__main__":
    main()
