with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Lines 1-12 (imports)
for i in range(min(12, len(lines))):
    print(f'{i+1}: {lines[i].rstrip()}')
print("=== 50-90 ===")
for i in range(50, min(90, len(lines))):
    print(f'{i+1}: {lines[i].rstrip()}')
