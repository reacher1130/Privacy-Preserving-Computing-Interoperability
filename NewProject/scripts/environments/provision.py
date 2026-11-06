#!/usr/bin/env python3
"""Provision a fresh Linux runtime. Existing runtime data is retained."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request

SOURCE = Path(os.environ.get('PPCI_SOURCE_ROOT', '/opt/ppci-source'))
ROOT = Path(os.environ.get('PPCI_ROOT', '/opt/ppci'))
BUILD = Path(os.environ.get('PPCI_BUILD_ROOT', '/opt/ppci-build'))
SCRIPTS = ROOT / 'NewProject/scripts'
LABEL = 'io.ppci.environment'


def run(*args, **kw):
    print('+', ' '.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **kw)


def ensure_container(name, args):
    p = subprocess.run(['docker', 'inspect', name], capture_output=True, text=True)
    if p.returncode == 0:
        d = json.loads(p.stdout)[0]
        if d['Config'].get('Labels', {}).get(LABEL) != 'portable':
            raise RuntimeError('Existing container is not owned by this provisioner: ' + name)
        if not d['State']['Running']:
            run('docker', 'start', name)
        return
    run('docker', 'run', '-d', '--name', name, '--label', LABEL + '=portable',
        '--restart', 'unless-stopped', '--log-opt', 'max-size=20m', '--log-opt', 'max-file=3', *args)


def network():
    p = subprocess.run(['docker', 'network', 'inspect', 'kuscia-exchange'], capture_output=True, text=True)
    if p.returncode:
        run('docker', 'network', 'create', '--subnet', '192.168.117.0/24', 'kuscia-exchange')
    elif json.loads(p.stdout)[0]['IPAM']['Config'][0]['Subnet'] != '192.168.117.0/24':
        raise RuntimeError('kuscia-exchange exists with another subnet')


def prepare():
    for node in ('alice', 'bob', 'kimi'):
        unit = Path('/etc/systemd/system/ppci-' + node + '.service')
        if unit.exists() and not unit.read_text().startswith('# Managed by PPCI'):
            raise RuntimeError('Existing migration runtime: use build-platform.sh and deploy-built.sh, not fresh provisioning')
    ROOT.mkdir(parents=True, exist_ok=True)
    for path in ('/srv/ppci', '/var/log/ppci', '/var/backups/ppci/releases'):
        Path(path).mkdir(parents=True, exist_ok=True)
    SCRIPTS.mkdir(parents=True, exist_ok=True)
    run('rsync', '-a', '--no-owner', '--no-group', str(SOURCE / 'NewProject/scripts') + '/', str(SCRIPTS) + '/')
    for repo in ('secretpad', 'secretpad-kimi-upstream'):
        target = ROOT / 'NewProject' / repo
        target.mkdir(parents=True, exist_ok=True)
        if repo == 'secretpad-kimi-upstream':
            (target / 'db').mkdir(exist_ok=True)
            (target / 'data').mkdir(exist_ok=True)
        # Only absent configuration files are initialized; identities stay local.
        run('rsync', '-a', '--ignore-existing', '--exclude=certs', '--exclude=server.jks',
            str(SOURCE / 'NewProject' / repo / 'config') + '/', str(target / 'config') + '/')
        (target / 'target').mkdir(exist_ok=True)
    bob = ROOT / 'NewProject/secretpad-bob'
    bob.mkdir(exist_ok=True)
    for name in ('config', 'target'):
        dest = bob / name
        if not dest.exists():
            dest.symlink_to('../secretpad/' + name)
    for node in ('alice', 'bob', 'kimi'):
        p = SCRIPTS / ('start_secretpad_' + node + '.sh')
        s = p.read_text().replace('/tmp/secretpad-alice-local-kuscia', '/srv/ppci/secretpad-alice-local-kuscia')
        s = s.replace('/tmp/secretpad-bob-local-kuscia', '/srv/ppci/secretpad-bob-local-kuscia')
        s = s.replace('/tmp/secretpad-bob-runtime', '/srv/ppci/secretpad-bob-runtime')
        for old in ('/tmp/secretpad-log-alice', '/tmp/secretpad-bob-log', '/tmp/secretpad-kimi-log'):
            s = s.replace(old, '/var/log/ppci/' + node)
        p.write_text(s.replace('198.18.2.76:80', '192.168.117.2:80'))


def fate():
    network()
    script = SCRIPTS / 'environments/native-fate-entrypoint.sh'
    if not script.is_file():
        raise RuntimeError('Run prepare first')
    for role, port in [('guest', 19381), ('host', 19382)]:
        args = ['--network', 'kuscia-exchange', '--ip', '192.168.117.' + ('20' if role == 'guest' else '21'), '--cpus', '2',
                '--ulimit', 'nofile=65536:65536',
                '-e', 'PPCI_FATE_ROLE=' + role,
                '-p', f'192.168.117.1:{port}:9380', '-p', f'127.0.0.1:{port}:9380',
                '-v', f'ppci-fate-{role}-flow:/data/projects/fate/fate_flow',
                '-v', f'{script}:/opt/ppci-fate-entrypoint.sh:ro',
                '--entrypoint', '/bin/bash']
        if os.environ.get('PPCI_FATE_EXTERNAL_BOARD') == '1':
            args += ['-e', 'PPCI_FATE_EXTERNAL_BOARD=1']
        elif role == 'guest':
            args += ['-p', '127.0.0.1:19383:8080']
        ensure_container(f'fate2-flow-{role}-e2e', args + [os.environ.get('PPCI_FATE_IMAGE', 'federatedai/standalone_fate:2.2.0'), '/opt/ppci-fate-entrypoint.sh'])


def kuscia():
    network()
    image = os.environ.get('KUSCIA_IMAGE', 'ppci/kuscia:home-20260912')
    shared = ROOT / 'images'
    shared.mkdir(exist_ok=True)
    for i, node in enumerate(('alice', 'bob', 'kimi'), 1):
        name = 'gaofeng-kuscia-autonomy-' + node
        work = ROOT / ('kuscia-node-bob' if node == 'bob' else name)
        work.mkdir(exist_ok=True)
        work.chmod(0o700)
        conf = work / 'kuscia.yaml'
        if not conf.exists():
            data = subprocess.check_output(['docker', 'run', '--rm', image, 'kuscia', 'init', '--mode', 'autonomy', '--domain', node], text=True)
            data += '\nagent:\n  allowPrivileged: true\n'
            if node == 'bob':
                data += '''  plugins:
    - name: cert-issuance
    - name: config-render
    - name: env-import
      config:
        usePodLabels: false
        envList:
          - envs:
              - name: system.transport
                value: transport.bob.svc
              - name: system.storage
                value: file:///home/kuscia/var/storage
              - name: system.storage.localfile
                value: file:///home/kuscia/var/storage
            selectors:
              - key: maintainer
                value: secretflow-contact@service.alipay.com
'''
            conf.write_text(data)
            conf.chmod(0o600)
        ensure_container(name, ['--network', 'kuscia-exchange', '--ip', f'192.168.117.{i+1}',
            '--hostname', name, '--privileged', '--ulimit', 'nofile=65536:65536',
            '--add-host', 'host.docker.internal:192.168.117.1',
            '-e', 'GOMAXPROCS=2', '-e', 'GOMEMLIMIT=900MiB',
            '-p', f'127.0.0.1:{i}8083:8083', '-p', f'127.0.0.1:{i}8084:8084',
            '-v', f'{name}-containerd:/home/kuscia/containerd',
            '-v', f'ppci-kuscia-{node}-var:/home/kuscia/var',
            '-v', f'{conf}:/home/kuscia/etc/conf/kuscia.yaml',
            '-v', f'{shared}:/home/kuscia/var/images', image, 'bin/kuscia', 'start', '-c', 'etc/conf/kuscia.yaml'])
    target = ROOT / 'NewProject/kuscia/scripts'
    target.mkdir(parents=True, exist_ok=True)
    run('rsync', '-a', str(SOURCE / 'NewProject/kuscia/scripts') + '/', str(target) + '/')
    run('bash', SCRIPTS / 'deploy_three_nodes.sh', env=dict(os.environ, USER='gaofeng', KUSCIA_IMAGE=image))


def upgrade_kuscia():
    """Replace only this provisioner's nodes, retaining stopped rollback containers."""
    image = os.environ.get('KUSCIA_IMAGE', 'ppci/kuscia:home-20260912')
    wanted = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image]))[0]['Id']
    pending = []
    for node in ('alice', 'bob', 'kimi'):
        name = 'gaofeng-kuscia-autonomy-' + node
        info = json.loads(subprocess.check_output(['docker', 'inspect', name]))[0]
        if info['Config'].get('Labels', {}).get(LABEL) != 'portable':
            raise RuntimeError('Refusing to upgrade an unmanaged node: ' + name)
        volumes = {m['Destination']: m.get('Name') for m in info['Mounts'] if m['Type'] == 'volume'}
        if (volumes.get('/home/kuscia/var') != f'ppci-kuscia-{node}-var' or
                volumes.get('/home/kuscia/containerd') != name + '-containerd'):
            raise RuntimeError('Expected persistent data volumes are absent: ' + name)
        if info['Image'] != wanted:
            pending.append((name, info))
    if not pending:
        print('All Kuscia nodes already use ' + wanted)
        return
    stamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    backup = Path('/var/backups/ppci') / ('kuscia-' + stamp)
    backup.mkdir(mode=0o700)
    for name, info in pending:
        record = backup / (name + '.json')
        record.write_text(json.dumps(info, indent=2))
        record.chmod(0o600)
        run('docker', 'cp', name + ':/home/kuscia/etc', backup / (name + '-etc'))
        run('docker', 'stop', '--time', '30', name)
        old_name = name + '-rollback-' + stamp
        run('docker', 'rename', name, old_name)
        run('docker', 'network', 'disconnect', 'kuscia-exchange', old_name)
    print('Rollback containers and configuration retained in ' + str(backup), flush=True)
    kuscia()


def platform():
    jdk = Path(os.environ.get('JAVA_HOME', '/usr/lib/jvm/java-21-openjdk'))
    if not (jdk / 'bin/java').is_file():
        raise RuntimeError('Java 21 is required')
    for node in ('alice', 'bob', 'kimi'):
        repo = 'secretpad-kimi-upstream' if node == 'kimi' else 'secretpad'
        pad = ROOT / 'NewProject' / repo
        sourcejar = BUILD / repo / 'target/secretpad.jar'
        targetjar = pad / 'target/secretpad.jar'
        if not targetjar.exists():
            shutil.copy2(sourcejar, targetjar)
        conf = pad / 'config'
        keystore = conf / 'server.jks'
        if not keystore.exists():
            run(jdk / 'bin/keytool', '-genkeypair', '-alias', 'secretpad-server', '-keyalg', 'RSA',
                '-keysize', '2048', '-validity', '3650', '-dname', 'CN=ppci-local',
                '-storetype', 'JKS', '-keystore', keystore, '-storepass', 'secretpad', '-keypass', 'secretpad')
            keystore.chmod(0o600)
        container = 'gaofeng-kuscia-autonomy-' + node
        run('docker', 'exec', container, 'bash', '-c', 'test -s var/certs/kusciaapi-client.crt || bash scripts/deploy/init_kusciaapi_client_certs.sh')
        paths = [conf / 'certs' / 'bob-local'] if node == 'bob' else [conf / 'certs']
        if node == 'kimi':
            paths += [ROOT / 'NewProject/secretpad/config/certs/kimi']
        for dest in paths:
            dest.mkdir(parents=True, exist_ok=True)
            for old, new in [('kusciaapi-client.crt', 'client.crt'), ('kusciaapi-client.key', 'client.pem'), ('token', 'token')]:
                run('docker', 'cp', container + ':/home/kuscia/var/certs/' + old, dest / new)
                (dest / new).chmod(0o600)
        suite = ''
        if node == 'alice' and os.environ.get('PPCI_PUBLIC_HOST'):
            suite = f'''Environment=PPCI_ROOT={ROOT}
Environment=PPCI_BFIA_SUITE_RUNNER={SCRIPTS}/linux-migration/run-bfia-suite.sh
Environment=PPCI_BFIA_SUITE_ROOT=/var/log/ppci/bfia-suite
Environment=PPCI_BFIA_SUITE_ALLOW_DEMO=true
Environment=PPCI_BFIA_SUITE_ORIGIN=http://{os.environ['PPCI_PUBLIC_HOST']}:18101
'''
            Path('/var/log/ppci/bfia-suite/runs').mkdir(parents=True, exist_ok=True, mode=0o700)
        unit = Path('/etc/systemd/system/ppci-' + node + '.service')
        content = f'''# Managed by PPCI environments/provision.py
[Unit]
Description=PPCI {node}
After=docker.service network-online.target
Requires=docker.service
[Service]
Type=simple
Environment=JAVA_HOME={jdk}
Environment=USER=gaofeng
Environment=SECRETPAD_JAVA_HEAP_MAX=512m
Environment=PADDLEDTX_REQUESTER_CONFIG={ROOT}/PaddleDTX/testdatatmp/executor/node1/conf/requester-config.toml
Environment=PADDLEDTX_REQUESTER_BINARY=/home/requester-cli-current
Environment=PADDLEDTX_MODEL_STORAGE_TYPE=Local
Environment=PADDLEDTX_DEMO_SKIP_HEALTH=false
{suite}Environment=PATH={os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin')}
WorkingDirectory={ROOT}
ExecStart=/bin/bash {SCRIPTS}/start_secretpad_{node}.sh
Restart=always
RestartSec=15
TimeoutStopSec=60
UMask=0077
[Install]
WantedBy=multi-user.target
'''
        if unit.exists() and not unit.read_text().startswith('# Managed by PPCI'):
            raise RuntimeError('Unmanaged systemd service: ' + str(unit))
        unit.write_text(content)
    run('systemctl', 'daemon-reload')
    cli = SCRIPTS / 'environments/portablectl.py'
    cli.chmod(0o755)
    link = Path('/usr/local/bin/ppci-platform')
    if not link.exists() and not link.is_symlink(): link.symlink_to(cli)
    run('systemctl', 'enable', '--now', 'ppci-alice', 'ppci-bob', 'ppci-kimi')


def gateway(env):
    dist = ROOT / 'NewProject/secretpad-frontend-dist-e2e'
    dist.mkdir(parents=True, exist_ok=True)
    run('rsync', '-a', str(BUILD / 'secretpad-frontend/apps/platform/dist') + '/', str(dist) + '/')
    # Read-only static files; private backend identities are outside this tree.
    for path in [dist] + list(dist.rglob('*')):
        path.chmod(0o755 if path.is_dir() else 0o644)
    conf = Path('/etc/nginx/conf.d/ppci.conf')
    content = '# Managed by PPCI environments/provision.py\n'
    for node, port, backend in [('alice', 18101, 18080), ('bob', 28101, 28090), ('kimi', 38101, 38090)]:
        fixed_profile = ''
        if node == 'kimi':
            # The unmodified upstream Kimi backend has no multi-protocol API.
            # This read-only deployment profile describes its fixed native mode.
            profile = json.dumps({'status': {'code': 0, 'msg': 'success'}, 'data': {
                'defaultProtocol': 'secretflow', 'activeProtocol': 'secretflow', 'canSwitch': False,
                'supportedProtocols': ['secretflow'], 'engineByProtocol': {'secretflow': 'SecretFlow / Kuscia'}}},
                separators=(',', ':'))
            fixed_profile = f'''  location = /api/v1alpha1/config/protocol {{
    if ($request_method !~ ^(GET|HEAD)$) {{ return 405; }}
    default_type application/json;
    add_header Cache-Control "no-store" always;
    return 200 '{profile}';
  }}
'''
        content += f'''server {{
  listen {env['host']}:{port};
  root {dist};
  index index.html;
  client_max_body_size 100m;
{fixed_profile}
  location ~ ^/(api|v1|sync)/ {{
    proxy_pass http://127.0.0.1:{backend};
    proxy_set_header Host $host;
    proxy_read_timeout 180s;
  }}
  location ~* \\.(?:html|js|css|map)$ {{
    add_header Cache-Control "no-store, max-age=0" always;
    try_files $uri =404;
  }}
  location / {{ try_files $uri $uri/ /index.html; }}
}}
'''
    native_port = os.environ.get('PPCI_NATIVE_UI_PORT')
    guest_board_port = 19483 if os.environ.get('PPCI_FATE_EXTERNAL_BOARD') == '1' else 19383
    host_board_port = 19484 if os.environ.get('PPCI_FATE_EXTERNAL_BOARD') == '1' else 19384
    native_routes = f'''  location /dtx/v1/ {{ proxy_pass http://127.0.0.1:{native_port}; proxy_set_header Host $host; }}
  location /static/unicom-dtx/ {{ proxy_pass http://127.0.0.1:{native_port}; }}
  location /dtx/console/ {{ proxy_pass http://127.0.0.1:{native_port}; }}
''' if native_port else '''  location /dtx/console/static/ { proxy_pass http://127.0.0.1:8233/static/; }
  location /dtx/console/ { proxy_pass http://127.0.0.1:8233/; }
'''
    content += f'''server {{
  listen {env['host']}:19383;
  location / {{
    proxy_pass http://127.0.0.1:{guest_board_port};
    proxy_set_header Host $host;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
  }}
}}
server {{
  listen {env['host']}:19384;
  location / {{
    proxy_pass http://127.0.0.1:{host_board_port};
    proxy_set_header Host $host;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
  }}
}}
server {{
  listen {env['host']}:18511;
  location /v1/ {{ proxy_pass http://127.0.0.1:8511; }}
{native_routes}
  location / {{ proxy_pass http://127.0.0.1:8233; }}
}}
'''
    content = content.replace('  listen ', f'  allow {env["lan_cidr"]};\n  deny all;\n  listen ')
    if conf.exists() and not conf.read_text().startswith('# Managed by PPCI'):
        raise RuntimeError('Unmanaged nginx config exists: ' + str(conf))
    conf.write_text(content)
    run('nginx', '-t')
    run('systemctl', 'enable', '--now', 'nginx')
    run('systemctl', 'reload', 'nginx')
    if subprocess.run(['systemctl', 'is-active', '--quiet', 'firewalld']).returncode == 0:
        for port in (18101, 28101, 38101, 19383, 19384, 18511):
            rule = f'rule family="ipv4" source address="{env["lan_cidr"]}" port port="{port}" protocol="tcp" accept'
            run('firewall-cmd', '--permanent', '--add-rich-rule=' + rule)
        run('firewall-cmd', '--reload')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=('prepare', 'kuscia', 'upgrade-kuscia', 'fate', 'platform', 'gateway'))
    p.add_argument('--environment', choices=('home', 'office'), default='home')
    a = p.parse_args()
    env = json.loads((SOURCE / 'NewProject/scripts/environments' / (a.environment + '.json')).read_text())
    env['host'] = os.environ.get('PPCI_PUBLIC_HOST', env['host'])
    env['lan_cidr'] = os.environ.get('PPCI_LAN_CIDR', env['lan_cidr'])
    if a.stage == 'prepare': prepare()
    elif a.stage == 'fate': fate()
    elif a.stage == 'kuscia': kuscia()
    elif a.stage == 'upgrade-kuscia': upgrade_kuscia()
    elif a.stage == 'platform': platform()
    elif a.stage == 'gateway': gateway(env)


if __name__ == '__main__':
    main()
