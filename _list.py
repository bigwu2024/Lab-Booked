import os

p = r'E:\4.2026项目创建\08.预约系统'
print('Path exists:', os.path.exists(p))
print('Is directory:', os.path.isdir(p))

if os.path.isdir(p):
    for root, dirs, files in os.walk(p):
        level = root.replace(p, '').count(os.sep)
        indent = ' ' * 2 * level
        print(f'{indent}{os.path.basename(root)}/')
        subindent = ' ' * 2 * (level + 1)
        for file in files:
            print(f'{subindent}{file}')
else:
    print('Directory does not exist!')
