with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
keywords = ['postgres','psycopg','DATABASE_URL','MARIADB','pymysql','mysql','db_config','get_db','create_engine','sqlite','connection','cursor','import']
for i, l in enumerate(lines, 1):
    if any(k.lower() in l.lower() for k in keywords):
        print(f'{i}: {l.rstrip()}')
