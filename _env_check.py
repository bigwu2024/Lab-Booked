import os, sys
# Check environment
info = []
info.append(f"Python: {sys.executable}")
info.append(f"CWD: {os.getcwd()}")
info.append(f"Platform: {sys.platform}")
info.append(f"PID: {os.getpid()}")

# Check if E: drive exists
if os.path.exists(r'E:\\'):
    info.append("E:\\ drive exists")
    p = r'E:\\4.2026项目创建\\08.预约系统'
    if os.path.exists(p):
        info.append(f"Project dir exists: {p}")
        info.append(f"Files: {os.listdir(p)[:20]}")
    else:
        info.append(f"Project dir NOT found: {p}")
else:
    info.append("E:\\ drive NOT found")
    
# Check home
info.append(f"Home: {os.path.expanduser('~')}")
info.append(f"User: {os.environ.get('USERNAME','?')}")

print('\\n'.join(info))
