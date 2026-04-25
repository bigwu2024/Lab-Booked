path = r'E:\4.2026项目创建\08.预约系统\app.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
out_path = r'E:\4.2026项目创建\08.预约系统\_content_dump.txt'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(content)
print(f'Written {len(content)} chars to {out_path}')
