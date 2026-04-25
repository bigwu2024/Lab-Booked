import re, sys
path = r'E:\4.2026项目创建\08.预约系统\app.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()
keywords = ['postgres','psycopg','DATABASE_URL','MARIADB','pymysql','mysql','db_config','get_db','create_engine','sqlite','connection','cursor','import']
out = []
for i, line in enumerate(lines, 1):
    low = line.lower()
    if any(k.lower() in low for k in keywords):
        out.append(f'{i}: {line.rstrip()}')
with open(r'E:\4.2026项目创建\08.预约系统\_scan_result.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
print(f'Found {len(out)} lines')
