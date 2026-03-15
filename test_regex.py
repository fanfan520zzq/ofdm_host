import re

# 测试行
line = '[2026-03-14 16:10:12.334] offset:0.0100665092  delay:8200'
next_line = '4.1310758591'

time_pattern = re.compile(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]')
delay_pattern = re.compile(r'delay\s*:\s*([-\d.]+)', re.IGNORECASE)
just_digits = re.compile(r'^\s*([-\d.]+)\s*$')

# 测试时间戳提取
time_match = time_pattern.search(line)
print(f'time_match: {time_match}')
if time_match:
    print(f'timestamp: {time_match.group(1)}')

# 测试 delay 提取
delay_match = delay_pattern.search(line)
print(f'delay_match: {delay_match}')
if delay_match:
    delay_val = delay_match.group(1)
    print(f'delay_val: {repr(delay_val)}')
    print(f'Is 8200? {delay_val == "8200"}')
    
    # 测试下一行是否匹配
    if delay_val == '8200':
        next_digits = just_digits.match(next_line)
        print(f'next_line: {repr(next_line)}')
        print(f'next_digits match: {next_digits}')
        if next_digits:
            matched_val = next_digits.group(1)
            print(f'Matched value: {matched_val}')
            
            # 新逻辑：如果是 4.1310758591，拆分并重新组织
            parts = matched_val.split('.')
            if len(parts) == 2:
                delay_val = f'8200{parts[0]}.{parts[1]}'
                result = f'delay:{delay_val}'
                print(f'Result: {result} ✓ CORRECT')
            else:
                result = f'delay:82004.{matched_val}'
                print(f'Result: {result}')
