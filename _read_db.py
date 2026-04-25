with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Print first 60 lines (imports + config)
print("=== LINES 1-60 ===")
for i, l in enumerate(lines[:60], 1):
    print(f'{i}: {l.rstrip()}')

# Find and print get_db_config and get_db functions
print("\n=== DB FUNCTIONS ===")
for i, l in enumerate(lines, 1):
    if 'def get_db' in l or 'db_config' in l.lower() or 'DATABASE_URL' in l:
        start = max(0, i-2)
        end = min(len(lines), i+30)
        for j in range(start, end):
            print(f'{j+1}: {lines[j].rstrip()}')
        print("---")
