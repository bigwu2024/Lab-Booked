import os
src = os.path.join('E:\\', '4.2026项目创建', '08.预约系统', 'app.py')
dst = os.path.join('E:\\', '4.2026项目创建', '08.预约系统', 'app_dump.txt')
with open(src, 'r', encoding='utf-8') as f:
    content = f.read()
with open(dst, 'w', encoding='utf-8') as f:
    f.write(content)
print(f'Dumped {len(content)} chars')
