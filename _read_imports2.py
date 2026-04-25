with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i in range(13, 30):
    print(f'{i+1}: {lines[i].rstrip()}')
