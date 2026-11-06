#!/usr/bin/env python3
"""Configure the migrated copy and systemd services; never starts services."""
from pathlib import Path
import shutil
import subprocess

root = Path('/opt/ppci')
backup = Path('/var/backups/ppci/migration-20260908/linux-config-originals')
backup.mkdir(parents=True, exist_ok=True)
logroot = Path('/var/log/ppci')
logroot.mkdir(exist_ok=True)
jdk = Path('/usr/lib/jvm/java-21-openjdk').resolve()
assert (jdk / 'bin/java').is_file()
for node in ('alice', 'bob', 'kimi'):
    p = root / 'NewProject/scripts' / ('start_secretpad_' + node + '.sh')
    dest = backup / p.name
    if not dest.exists():
        shutil.copy2(p, dest)
    s = dest.read_text().replace('/Library/Java/JavaVirtualMachines/zulu-21.jdk/Contents/Home', str(jdk))
    s = s.replace('/tmp/secretpad-alice-local-kuscia', '/srv/ppci/secretpad-alice-local-kuscia')
    s = s.replace('/tmp/secretpad-bob-local-kuscia', '/srv/ppci/secretpad-bob-local-kuscia')
    s = s.replace('/tmp/secretpad-bob-runtime', '/srv/ppci/secretpad-bob-runtime')
    for old in ('/tmp/secretpad-log-alice', '/tmp/secretpad-bob-log', '/tmp/secretpad-kimi-log'):
        s = s.replace(old, '/var/log/ppci/' + node)
    s = s.replace('198.18.2.76:80', '192.168.117.2:80')
    p.write_text(s)
    unit = Path('/etc/systemd/system/ppci-' + node + '.service')
    content = '''[Unit]
Description=PPCI SecretPad {node}
After=docker.service network-online.target
Requires=docker.service
Wants=network-online.target

[Service]
Type=simple
Environment=JAVA_HOME={jdk}
Environment=USER=gaofeng
WorkingDirectory=/opt/ppci
ExecStart=/bin/bash /opt/ppci/NewProject/scripts/start_secretpad_{node}.sh
Restart=always
RestartSec=15
TimeoutStopSec=90
UMask=0077

[Install]
WantedBy=multi-user.target
'''.format(node=node, jdk=jdk)
    if unit.exists() and unit.read_text() != content:
        raise RuntimeError('Existing unit differs: ' + str(unit))
    unit.write_text(content)
for name in ('secretpad-ui-native-alice.conf', 'secretpad-ui-native-kimi.conf'):
    conf = root / 'NewProject/scripts' / name
    saved = backup / name
    if not saved.exists():
        shutil.copy2(conf, saved)
    text = saved.read_text()
    text = text.replace('server {', 'server {\n    absolute_redirect off;')
    text = text.replace('location / {', 'location = / { return 302 /edge?tab=workbench; }\n    location / {')
    conf.write_text(text)
conf = root / 'NewProject/scripts/paddledtx-ui-native.conf'
saved = backup / conf.name
if not saved.exists():
    shutil.copy2(conf, saved)
conf.write_text(saved.read_text().replace('server {', 'server {\n    absolute_redirect off;').replace('location / {',
    'location = / { return 302 /dtx/console/; }\n    location / {'))
cli = root / 'NewProject/scripts/linux-migration/platformctl.py'
cli.chmod(0o755)
link = Path('/usr/local/bin/ppci-platform')
if link.exists() or link.is_symlink():
    if link.resolve() != cli.resolve():
        raise RuntimeError('Existing command differs: ' + str(link))
else:
    link.symlink_to(cli)
subprocess.run(['systemctl', 'daemon-reload'], check=True)
print('Linux launchers and systemd units prepared; services not started.')
