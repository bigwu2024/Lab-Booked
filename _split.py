import os
src = os.path.join('E:\\', '4.2026项目创建', '08.预约系统', 'app.py')
out = os.path.join('E:\\', '4.2026项目创建', '08.预约系统', 'code_parts')
os.makedirs(out, exist_ok=True)

with open(src, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Split into parts of 200 lines each
part_size = 200
for i in range(0, len(lines), part_size):
    chunk = lines[i:i+part_size]
    part_num = i // part_size + 1
    part_file = os.path.join(out, f'part_{part_num}.txt')
    with open(part_file, 'w', encoding='utf-8') as f:
        for j, line in enumerate(chunk):
            f.write(f'{i+j+1}|{line}')
    print(f'Part {part_num}: lines {i+1}-{i+len(chunk)}')

print(f'Total lines: {len(lines)}')
