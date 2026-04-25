with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Print lines 1-15 (imports)
for i in range(min(15, len(lines))):
    print(f'{i+1}: {lines[i].rstrip()}')
print("=== SKIP ===")
# Print lines 50-120 (db config + get_db functions)
for i in range(50, min(120, len(lines))):
    print(f'{i+1}: {lines[i].rstrip()}')
