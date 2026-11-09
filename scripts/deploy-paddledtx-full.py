#!/usr/bin/env python3
"""Build and initialize the real native PaddleDTX manager/UI on a fresh target."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import subprocess
import sys
import time

SOURCE = Path(os.environ.get('PPCI_SOURCE_ROOT', Path(__file__).resolve().parents[1])).resolve()
ROOT = Path(os.environ.get('PPCI_ROOT', '/opt/ppci')).resolve()
BUILD = Path(os.environ.get('PPCI_BUILD_ROOT', '/opt/ppci-build')).resolve()
STAGE = BUILD / 'paddle-native'
STATE = Path(os.environ.get('PPCI_DTX_STATE_ROOT', ROOT / 'native/dtx-manager'))
PATCHES = SOURCE / 'platform/scripts/patches'
NETWORK = 'blockchain_network'
LABEL = 'io.ppci.environment=portable'
IMAGE_PREFIX = 'ppci/paddledtx-'


def call(*args, cwd=None, data=None, env=None, check=True):
    result = subprocess.run([str(x) for x in args], cwd=cwd, input=data, env=env,
                            capture_output=True, text=True)
    if check and result.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(str(x) for x in args[:3]) + '\n' + result.stderr[-4000:])
    return result


def private_file(path, text):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as output:
        output.write(text)
    path.chmod(0o600)


def patch(directory, name):
    path = PATCHES / name
    if call('git', 'apply', '--check', path, cwd=directory, check=False).returncode == 0:
        call('git', 'apply', path, cwd=directory)
    else:
        call('git', 'apply', '--reverse', '--check', path, cwd=directory)


def sources():
    STAGE.mkdir(parents=True, exist_ok=True)
    destination = STAGE / 'source'
    manifest = json.loads((SOURCE / 'platform/thirdparty/paddledtx-source.json').read_text())
    marker = STAGE / 'source.json'
    if marker.exists():
        if json.loads(marker.read_text())['sha256'] != manifest['sha256']:
            raise RuntimeError('Native source changed; use a new PPCI_BUILD_ROOT to retain previous artifacts')
    else:
        call(sys.executable, SOURCE / 'scripts/prepare-legacy-source.py', '--extract', destination)
        marker.write_text(json.dumps(manifest))
    manager = destination / 'dtx-manager'
    frontend = destination / 'dtx-fe'
    paddle = destination / 'PaddleDTX'
    for name in ('auth', 'upload', 'sdk-log', 'chain-task'):
        patch(manager, 'paddledtx-manager-' + name + '.patch')
    patch(paddle / 'dai', 'paddledtx-file-metadata.patch')
    for name in ('login', 'download', 'chain-task'):
        patch(frontend, 'paddledtx-native-' + name + '.patch')
    # The native contract is a nested module; build in GOPATH with the exact vendored SDK.
    for rel in ('github.com/xuperchain/xuperchain', 'github.com/go-playground', 'github.com/leodido'):
        target = manager / 'vendor' / rel
        if not target.exists():
            shutil.copytree(paddle / 'dai/vendor' / rel, target)
    return manager, frontend, paddle


def build():
    manager, frontend, paddle = sources()
    arch = os.environ.get('PPCI_TARGET_ARCH', {'x86_64': 'amd64', 'aarch64': 'arm64'}.get(platform.machine(), platform.machine()))
    if arch not in ('amd64', 'arm64'):
        raise RuntimeError('Native builds support amd64 and arm64')
    env = dict(os.environ, GOOS='linux', GOARCH=arch, CGO_ENABLED='0', GOTOOLCHAIN='local', GOENV='off',
               GOMAXPROCS='2', GOMEMLIMIT='1500MiB', GOPROXY='off', GOFLAGS='-mod=vendor',
               GOCACHE=str(BUILD / 'gocache'))
    binary = STAGE / 'bin'
    binary.mkdir(exist_ok=True)
    module = manager / 'go.mod'
    vendors = set(re.findall(r'^# (\S+) v', (manager / 'vendor/modules.txt').read_text(), re.M))
    module.write_text('\n'.join(line for line in module.read_text().splitlines()
                                if not line.startswith('replace baidu/blockchain/dtx-manager =>') and
                                not ((match := re.match(r'^\s+(\S+) v\S+', line)) and match.group(1) not in vendors)) + '\n')
    modules = manager / 'vendor/modules.txt'
    modules.write_text('\n'.join(line for line in modules.read_text().splitlines()
                                 if not line.startswith('# baidu/blockchain/dtx-manager =>')) + '\n')
    for output, directory, package in [('dtx-manager', manager, '.'), ('executor', paddle / 'dai', '.'),
                                        ('executor-cli', paddle / 'dai', './executor/cmd'),
                                        ('requester-cli-current', paddle / 'dai', './requester/cmd'),
                                        ('paddlempc', paddle / 'dai', './blockchain/xchain/contract'),
                                        ('xdb', paddle / 'xdb', '.'), ('xdb-cli', paddle / 'xdb', './cmd/client')]:
        print('Building native ' + output, flush=True)
        call('go', 'build', '-p', '2', '-ldflags=-s -w', '-o', binary / output, package, cwd=directory, env=env)
    call('go', 'build', '-p', '2', '-o', binary / 'check-manager', SOURCE / 'platform/scripts/check_paddledtx_manager.go', cwd=manager, env=env)
    # Tests execute on the build host; cross-built binaries are checked by target deployment.
    if arch == {'x86_64': 'amd64', 'aarch64': 'arm64'}.get(platform.machine(), platform.machine()) and sys.platform.startswith('linux'):
        call('go', 'test', '-p', '2', './pkg/auth', './pkg/filesafe', './controllers', '-run',
             'Test(AuthorizationRecoveryBoundary|UploadRecoveryBoundary|RecoveryAuthorityPolicy|ChainTask)', '-count=1', cwd=manager, env=env)
        call('go', 'test', '-p', '2', './util/filemeta', '-count=1', cwd=paddle / 'dai', env=env)
    gopath = STAGE / 'gopath'
    link = gopath / 'src/baidu/blockchain/dtx-manager'
    link.parent.mkdir(parents=True, exist_ok=True)
    if not link.exists():
        link.symlink_to(manager)
    contract_env = dict(env, GO111MODULE='off', GOPATH=str(gopath))
    contract_env.pop('GOFLAGS')
    call('go', 'build', '-p', '2', '-ldflags=-s -w', '-o', binary / 'dtxmanager-native',
         'baidu/blockchain/dtx-manager/blockchain/xchain/contract', cwd=gopath, env=contract_env)
    paddle_output = BUILD / 'paddle'
    paddle_output.mkdir(exist_ok=True)
    for name in ('paddlempc', 'requester-cli-current'):
        shutil.copy2(binary / name, paddle_output / name)
    print('Building native frontend (normal signed login enabled)', flush=True)
    call('npm', 'ci', '--ignore-scripts', '--legacy-peer-deps', '--no-audit', '--fund=false', cwd=frontend)
    call('node', '--test', 'scripts/check-download.cjs', cwd=frontend)
    call('npm', 'run', 'build', cwd=frontend, env=dict(os.environ, NODE_OPTIONS='--max-old-space-size=3072'))
    html = frontend / 'build/static/unicom-dtx/page/index.html'
    if 'window.__DTX_DEMO_AUTH_DISABLED__ = false;' not in html.read_text():
        raise RuntimeError('Native frontend must require normal login')
    for kind, names, entry in [('dai', ('executor', 'executor-cli', 'requester-cli-current'), 'executor'),
                               ('xdb', ('xdb', 'xdb-cli'), 'xdb'),
                               ('dtx-manager', ('dtx-manager',), 'dtx-manager')]:
        context = STAGE / ('image-' + kind)
        context.mkdir(exist_ok=True)
        for name in names:
            shutil.copy2(binary / name, context / name)
        (context / 'Dockerfile').write_text('FROM debian:bookworm-slim\nWORKDIR /home\n' +
                                           ''.join('COPY ' + name + ' /home/' + name + '\n' for name in names) +
                                           'ENTRYPOINT ["/home/' + entry + '"]\n')
        call('docker', 'build', '--platform', 'linux/' + arch, '-t', IMAGE_PREFIX + kind + ':portable', context)
    ui = STAGE / 'image-dtx-ui'
    ui.mkdir(exist_ok=True)
    shutil.copytree(frontend / 'build', ui / 'html', dirs_exist_ok=True)
    (ui / 'default.conf').write_text('''server {
  listen 80;
  root /usr/share/nginx/html;
  client_max_body_size 100m;
  location /dtx/v1/ { proxy_pass http://ppci-dtx-manager:8488; proxy_read_timeout 180s; }
  location /static/ { try_files $uri =404; }
  location / { try_files $uri $uri/ /static/unicom-dtx/page/index.html; }
}
''')
    (ui / 'Dockerfile').write_text('FROM nginx:1.27-alpine\nCOPY html /usr/share/nginx/html\nCOPY default.conf /etc/nginx/conf.d/default.conf\n')
    call('docker', 'build', '--platform', 'linux/' + arch, '-t', IMAGE_PREFIX + 'dtx-ui:portable', ui)
    (STAGE / 'built.json').write_text(json.dumps({'architecture': arch, 'source_sha256': json.loads((STAGE / 'source.json').read_text())['sha256'],
                                                'images': [IMAGE_PREFIX + name + ':portable' for name in ('dai', 'xdb', 'dtx-manager', 'dtx-ui')]}))


def container(name, arguments):
    result = call('docker', 'inspect', name, check=False)
    if result.returncode == 0:
        info = json.loads(result.stdout)[0]
        if info['Config'].get('Labels', {}).get('io.ppci.environment') != 'portable':
            raise RuntimeError('Existing unmanaged container retained: ' + name)
        wanted = json.loads(call('docker', 'image', 'inspect', arguments[-1]).stdout)[0]['Id']
        if info['Image'] != wanted:
            raise RuntimeError('Existing container uses another image and is retained: ' + name + '; back up its state and perform a reviewed upgrade before retrying')
        if not info['State']['Running']:
            call('docker', 'start', name)
        return
    call('docker', 'run', '-d', '--name', name, '--label', LABEL, '--network', NETWORK,
         '--restart', 'unless-stopped', '--log-opt', 'max-size=20m', '--log-opt', 'max-file=3', *arguments)


def mysql(sql):
    return call('docker', 'exec', '-i', 'ppci-dtx-mysql', 'sh', '-c',
                'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot --batch --skip-column-names', data=sql).stdout.strip()


def deploy():
    binary = STAGE / 'bin/dtxmanager-native'
    if not binary.is_file():
        raise RuntimeError('Run native build (or import a complete release) first')
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    STATE.chmod(0o700)
    for name in ('private', 'conf', 'log', 'data', 'upload'):
        (STATE / name).mkdir(mode=0o700, exist_ok=True)
    credentials = STATE / 'private/credentials.json'
    if not credentials.exists():
        private_file(credentials, json.dumps({'username': 'admin', 'password': secrets.token_urlsafe(24)}))
    env_file = STATE / 'private/mysql.env'
    if not env_file.exists():
        private_file(env_file, 'MYSQL_ROOT_PASSWORD=' + secrets.token_urlsafe(32) + '\nMYSQL_DATABASE=ppci_dtx\nMYSQL_USER=ppci_dtx\nMYSQL_PASSWORD=' + secrets.token_urlsafe(32) + '\n')
    values = dict(line.split('=', 1) for line in env_file.read_text().splitlines())
    container('ppci-dtx-mysql', ['--env-file', env_file, '-v', 'ppci-dtx-mysql:/var/lib/mysql',
                               os.environ.get('PPCI_DTX_MYSQL_IMAGE', 'mysql:8.0')])
    for attempt in range(90):
        if call('docker', 'exec', 'ppci-dtx-mysql', 'sh', '-c', 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqladmin ping -uroot --silent', check=False).returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError('Native MySQL did not become ready')
    chain = ['docker', 'exec', 'xchain1.node.com', './xchain-cli']
    query = chain + ['native', 'query', 'data', '--method', 'ListOrgInfo', '--keys', './user']
    result = call(*query, check=False)
    if result.returncode != 0:
        if 'get contract desc' not in result.stdout + result.stderr or 'Key not found' not in result.stdout + result.stderr:
            raise RuntimeError('Cannot safely establish whether the management contract exists')
        call('docker', 'cp', binary, 'xchain1.node.com:/home/work/xchain/dtxmanager-native')
        args = chain + ['native', 'deploy', '--account', 'XC1111111111111112@xuper', '--runtime', 'go',
                        '-a', json.dumps({'creator': 'XC1111111111111112@xuper'}), '--cname', 'data', './dtxmanager-native', '--keys', './user']
        quote = call(*args, check=False)
        gas = re.search(r'The gas you[^:\n]*:\s*(\d+)', quote.stdout + quote.stderr)
        if not gas:
            raise RuntimeError('Could not determine native management contract transaction fee')
        call(*args, '--fee', gas.group(1))
    work = ROOT / 'PaddleDTX/testdatatmp'
    keys = work / 'xdb/data1/keys'
    public = (keys / 'public.key').read_text().strip()
    private = (keys / 'private.key').read_text().strip()
    requester = (work / 'executor/requester/keys/public.key').read_text().strip()
    mnemonic = (work / 'blockchain/xchain/user/mnemonic').read_text().strip()
    if not re.fullmatch('[a-fA-F0-9]{128}', public) or not re.fullmatch('[a-fA-F0-9]{128}', requester) or not re.fullmatch('[a-fA-F0-9]+', private):
        raise RuntimeError('Invalid target PaddleDTX keys')
    conf = STATE / 'conf/app.conf'
    bootstrapped = STATE / 'private/bootstrapped.json'
    def configure(bootstrap):
        private_file(conf, f'''appname = ppci-dtx-manager
httpaddr = {'127.0.0.1' if bootstrap else '0.0.0.0'}
httpport = 8488
runmode = prod
copyrequestbody = true
dbUser = ppci_dtx
dbPassword = {values['MYSQL_PASSWORD']}
dbHost = ppci-dtx-mysql
dbPort = 3306
dbName = ppci_dtx
runSyncdb = {'true' if bootstrap else 'false'}
logLevel = 6
logPath = ./log
secretKey = {secrets.token_hex(16)}
localPath = /home/data
[orginfo]
id = ppci-alice
name = PPCI Alice
did = ppci-alice
pubkey = {public}
prikey = {private}
[xdb]
name = data-node1
host = dataowner1.node.com:80
nodeID = {public}
privatekey = {private}
namespace = paddlempc
''')
        private_file(STATE / 'conf/blockchain.toml', '[blockchain]\ntype = "xchain"\n[blockchain.xchain]\nmnemonic = ' + json.dumps(mnemonic, ensure_ascii=False) + '\ndtxContractName = "paddlempc"\nmanagerContractName = "data"\ncontractAccount = "XC1111111111111112@xuper"\nchainAddress = "xchain1.node.com:37101"\nchainName = "xuper"\n')
    if not conf.exists():
        configure(bootstrap=not bootstrapped.exists())
    arguments = ['--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--memory', '512m', '--cpus', '2',
                 '-e', 'GOMAXPROCS=2', '-e', 'PPCI_CHAIN_TASK_REQUESTER=' + requester.lower(), '--tmpfs', '/tmp:rw,nosuid,noexec,size=16m']
    for name in ('conf', 'log', 'data', 'upload'):
        arguments += ['-v', str(STATE / name) + ':/home/' + name + (':ro' if name == 'conf' else ':rw')]
    container('ppci-dtx-manager', arguments + [IMAGE_PREFIX + 'dtx-manager:portable'])
    if not bootstrapped.exists():
        for _ in range(60):
            try:
                salt = mysql("SELECT salt FROM ppci_dtx.common_user WHERE username='admin';\n")
            except RuntimeError:
                salt = ''
            if salt:
                break
            time.sleep(1)
        else:
            raise RuntimeError('Native manager failed to initialize its schema')
        wire = hashlib.md5(json.loads(credentials.read_text())['password'].encode()).hexdigest()
        digest = base64.b64encode(hashlib.md5((wire + salt).encode()).digest()).decode()
        mysql("UPDATE ppci_dtx.common_user SET password='" + digest + "' WHERE username='admin';\n")
        call('docker', 'stop', '-t', '15', 'ppci-dtx-manager')
        configure(bootstrap=False)
        call('docker', 'start', 'ppci-dtx-manager')
        private_file(bootstrapped, json.dumps({'created': time.time(), 'requester': requester.lower()}))
    container('ppci-dtx-native-ui', ['-p', '127.0.0.1:18088:80', IMAGE_PREFIX + 'dtx-ui:portable'])
    for _ in range(30):
        check = call(STAGE / 'bin/check-manager', '-chain-baseline', '-base-url', 'http://127.0.0.1:18088', '-credentials', credentials, check=False)
        if check.returncode == 0:
            private_file(STATE / 'private/manager-check.json', check.stdout)
            break
        time.sleep(1)
    else:
        raise RuntimeError('Native manager signed login/list verification failed; inspect target service logs')
    print('Native manager/UI deployed; target admin credentials: ' + str(credentials))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('build', 'deploy', 'prepare'))
    args = parser.parse_args()
    try:
        if args.stage == 'build':
            build()
        elif args.stage == 'prepare':
            sources()
        else:
            deploy()
    except (RuntimeError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
