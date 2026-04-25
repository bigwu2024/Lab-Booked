with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Print lines 1-50
for i in range(min(50, len(lines))):
    print(f'{i+1}: {lines[i].rstrip()}')
