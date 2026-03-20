"""
处理指定数据文件，计算 offset 和 Delay 的平均值，以及收敛时间。
收敛时间定义：offset 从一开始到首次小于 0.02 的时间差。
用法：python process_data.py 数据文件路径
"""
import sys
import re
from datetime import datetime


def trim_head_samples(values, ratio=0.01):
    """剔除序列头部 ratio 比例样本，保留至少 1 个样本。"""
    if not values:
        return [], 0
    if len(values) == 1:
        return values[:], 0
    drop_count = int(len(values) * ratio)
    drop_count = min(drop_count, len(values) - 1)
    return values[drop_count:], drop_count


def calc_stats_with_trim(values, ratio=0.01):
    """基于剔除头部毛刺后的样本计算均值与最值。"""
    trimmed, dropped = trim_head_samples(values, ratio=ratio)
    if not trimmed:
        return {
            "mean": None,
            "min": None,
            "max": None,
            "raw_count": len(values),
            "used_count": 0,
            "dropped_count": dropped,
        }
    return {
        "mean": sum(trimmed) / len(trimmed),
        "min": min(trimmed),
        "max": max(trimmed),
        "raw_count": len(values),
        "used_count": len(trimmed),
        "dropped_count": dropped,
    }

def parse_file(filepath):
    """
    解析数据文件，提取 offset 和 delay，计算平均值和收敛时间。
    
    Args:
        filepath: 数据文件路径
    
    Returns:
        tuple: (offsets 列表, delays 列表, 收敛时间秒数)
    """
    offsets = []
    delays = []
    offset_times = []
    start_time = None
    converge_time = None
    offset_converged = False
    first_data_time = None
    time_pattern = re.compile(r"\[(.*?)\]")
    offset_pattern = re.compile(r"offset:([\d\.-]+)", re.IGNORECASE)
    delay_pattern = re.compile(r"delay:([\d\.-]+)", re.IGNORECASE)
    
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
            # 只处理 offset/delay 行（大小写不敏感）
            if re.search(r"offset:", line, re.I) and re.search(r"delay:", line, re.I):
                offset_match = offset_pattern.search(line)
                delay_match = delay_pattern.search(line)
                if offset_match and delay_match:
                    offset = float(offset_match.group(1))
                    delay = float(delay_match.group(1))
                    offsets.append(offset)
                    delays.append(delay)
                    offset_times.append(ts)
                    if first_data_time is None:
                        first_data_time = ts
                    # 收敛时间判断
                    if not offset_converged and abs(offset) < 0.02:
                        # 如果没有显式的起点（join/client），使用第一条数据的时间作为起点
                        origin = start_time if start_time else first_data_time
                        converge_time = (ts - origin).total_seconds() if origin else None
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
    offset_stats = calc_stats_with_trim(offsets, ratio=0.01)
    delay_stats = calc_stats_with_trim(delays, ratio=0.01)

    print(
        f"offset 统计样本: 原始 {offset_stats['raw_count']} 条, "
        f"剔除前 {offset_stats['dropped_count']} 条后使用 {offset_stats['used_count']} 条"
    )
    print(
        f"Delay 统计样本: 原始 {delay_stats['raw_count']} 条, "
        f"剔除前 {delay_stats['dropped_count']} 条后使用 {delay_stats['used_count']} 条"
    )
    print(f"offset 平均值: {offset_stats['mean']:.6f}")
    print(f"Delay 平均值: {delay_stats['mean']:.6f}")
    print(f"offset 最小值: {offset_stats['min']:.6f}")
    print(f"offset 最大值: {offset_stats['max']:.6f}")
    print(f"Delay 最小值: {delay_stats['min']:.6f}")
    print(f"Delay 最大值: {delay_stats['max']:.6f}")
    if converge_time is not None:
        print(f"收敛时间: {converge_time:.3f} 秒")
    else:
        print("未检测到 offset 收敛到 <0.02 的时刻")

if __name__ == "__main__":
    main()
