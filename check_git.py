import subprocess, os, sys

os.chdir(r'E:\4.2026项目创建\08.预约系统')

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout + r.stderr

out = []
out.append('=== GIT STATUS ===')
out.append(run(['git', 'status', '--short']))
out.append('=== GIT REMOTE ===')
out.append(run(['git', 'remote', '-v']))
out.append('=== GIT LOG ===')
out.append(run(['git', 'log', '--oneline', '-5']))
out.append('=== GH AUTH ===')
out.append(run(['gh', 'auth', 'status']))
out.append('=== GITIGNORE ===')
gi = os.path.join(r'E:\4.2026项目创建\08.预约系统', '.gitignore')
if os.path.exists(gi):
    with open(gi, 'r', encoding='utf-8') as f:
        out.append(f.read())
else:
    out.append('NO .gitignore FILE')
out.append('=== BRANCH ===')
out.append(run(['git', 'branch', '-a']))

result = '\n'.join(out)
print(result)
