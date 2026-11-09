#!/usr/bin/env python3
"""Restore the office PaddleDTX manager without replacing its compute ledger.

Run on the office Linux server as root, after the recovery backups exist.
The historical manager/vendor sources must remain in the runtime directory.
All generated credentials and build outputs stay on that server.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import time

SOURCE = Path('/opt/ppci/privacy-computing-interconnectivity/shared-exchange-Connectivity')
BUILD = Path('/opt/ppci-build/dtx-manager')
STATE = Path('/srv/ppci/dtx-manager')
BACKUP = Path('/var/backups/ppci/office-recovery-20261102')
GO = '/opt/ppci-tools/go124/go/bin/go'
ACCOUNT = 'XC1111111111111112@xuper'
CONTAINER = 'ppci-dtx-manager'
IMAGE = 'ppci/dtx-manager:recovery-20261102'
SCRIPTS = Path(__file__).resolve().parent


def call(args, cwd=None, data=None, check=True, env=None):
    result = subprocess.run([str(x) for x in args], cwd=str(cwd) if cwd else None,
                            input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            universal_newlines=True, env=env)
    if check and result.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(str(x) for x in args[:3]) +
                           ' (output suppressed; inspect server build/service logs)')
    return result


def private_file(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as out:
        out.write(text)
    path.chmod(0o600)


def mysql(sql):
    # SQL, passwords and query results never appear in process arguments or output.
    return call(['docker', 'exec', '-i', 'mysql', 'sh', '-c',
                 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot --batch --skip-column-names'],
                data=sql).stdout


def build():
    BUILD.mkdir(mode=0o700, parents=True, exist_ok=True)
    BUILD.chmod(0o700)
    # Only the disposable build copy is mirrored; runtime state is elsewhere.
    call(['rsync', '-a', '--delete', '--exclude=/.git', '--exclude=/log', '--exclude=/bin',
          str(SOURCE / 'dtx-manager') + '/', str(BUILD) + '/'])
    module = BUILD / 'go.mod'
    vendor = BUILD / 'vendor/modules.txt'
    vendored = set(re.findall(r'^# (\S+) v', vendor.read_text(), re.M))
    lines = []
    for line in module.read_text().splitlines():
        requirement = re.match(r'^\s+(\S+) v\S+', line)
        if requirement and requirement.group(1) not in vendored:
            continue  # Historical unused Kubernetes requirements lack vendor entries.
        if not line.startswith('replace baidu/blockchain/dtx-manager =>'):
            lines.append(line)
    module.write_text('\n'.join(lines) + '\n')
    vendor.write_text('\n'.join(x for x in vendor.read_text().splitlines()
                                if not x.startswith('# baidu/blockchain/dtx-manager =>')) + '\n')
    for name in ('auth', 'upload', 'sdk-log', 'chain-task'):
        patch = SCRIPTS / 'patches' / ('paddledtx-manager-' + name + '.patch')
        call(['git', 'apply', '--check', patch], cwd=BUILD)
        call(['git', 'apply', patch], cwd=BUILD)
    (BUILD / 'bin').mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(GOENV='off', GOPROXY='off', GOTOOLCHAIN='local', CGO_ENABLED='0', GOFLAGS='-mod=vendor')
    log = Path('/var/log/ppci/dtx-manager-build-20261102.log')
    with log.open('w') as out:
        for args in ([GO, 'test', '-p', '2', './pkg/auth', './pkg/filesafe', './controllers',
                      '-run', 'Test(AuthorizationRecoveryBoundary|UploadRecoveryBoundary|RecoveryAuthorityPolicy|ChainTask)', '-count=1'],
                     [GO, 'build', '-p', '2', '-ldflags=-s -w', '-o', str(BUILD / 'bin/dtx-manager'), '.']):
            result = subprocess.run(args, cwd=str(BUILD), env=env, stdout=out, stderr=subprocess.STDOUT)
            if result.returncode:
                raise RuntimeError('Manager build/test failed; inspect ' + str(log))
    # The native contract is a historical nested module. Reuse only missing SDK
    # modules from the existing PaddleDTX vendor and compile in an isolated GOPATH.
    for rel in ('github.com/xuperchain/xuperchain', 'github.com/go-playground', 'github.com/leodido'):
        dest = BUILD / 'vendor' / rel
        if not dest.exists():
            shutil.copytree(str(SOURCE / 'PaddleDTX/dai/vendor' / rel), str(dest))
    gopath = Path('/opt/ppci-build/dtx-manager-gopath')
    link = gopath / 'src/baidu/blockchain/dtx-manager'
    link.parent.mkdir(parents=True, exist_ok=True)
    if not link.exists():
        link.symlink_to(BUILD)
    env.update(GO111MODULE='off', GOPATH=str(gopath))
    env.pop('GOFLAGS', None)
    with Path('/var/log/ppci/dtx-manager-contract-build-20261102.log').open('w') as out:
        result = subprocess.run([GO, 'build', '-p', '2', '-ldflags=-s -w', '-o',
                                 str(BUILD / 'bin/dtxmanager-native'),
                                 'baidu/blockchain/dtx-manager/blockchain/xchain/contract'],
                                cwd=str(gopath), env=env, stdout=out, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError('Native management contract build failed; inspect server log')


def contract():
    cli = ['docker', 'exec', 'xchain1.node.com', './xchain-cli']
    query = cli + ['native', 'query', 'data', '--method', 'ListOrgInfo', '--keys', './user']
    result = call(query, check=False)
    if result.returncode == 0:
        return
    if 'get contract desc' not in result.stdout + result.stderr or 'Key not found' not in result.stdout + result.stderr:
        raise RuntimeError('Cannot safely establish whether the management contract exists')
    binary = BUILD / 'bin/dtxmanager-native'
    call(['docker', 'cp', binary, 'xchain1.node.com:/home/work/xchain/dtxmanager-recovery-20261102'])
    deploy = cli + ['native', 'deploy', '--account', ACCOUNT, '--runtime', 'go',
                    '-a', json.dumps({'creator': ACCOUNT}), '--cname', 'data',
                    './dtxmanager-recovery-20261102', '--keys', './user']
    quote = call(deploy, check=False)
    gas = re.search(r'The gas you[^:\n]*:\s*(\d+)', quote.stdout + quote.stderr)
    if not gas:
        raise RuntimeError('Could not determine management contract transaction fee')
    result = call(deploy + ['--fee', gas.group(1)])
    private_file(BACKUP / 'data-deployment.json', json.dumps({
        'contract': 'data', 'account': ACCOUNT, 'transaction': result.stdout,
        'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}, indent=2))
    for _ in range(20):
        if call(query, check=False).returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError('Management contract did not become queryable')


def credentials():
    for directory in ('private', 'conf', 'log', 'data', 'upload'):
        p = STATE / directory
        p.mkdir(parents=True, exist_ok=True)
        p.chmod(0o700)
    for filename, username in [('credentials.json', 'admin'), ('probe-credentials.json', 'recovery-probe')]:
        path = STATE / 'private' / filename
        if not path.exists():
            private_file(path, json.dumps({'username': username, 'password': secrets.token_urlsafe(24)}))
    db = STATE / 'private/database.json'
    if not db.exists():
        private_file(db, json.dumps({'password': secrets.token_urlsafe(32)}))
    password = json.loads(db.read_text())['password']
    assert re.match(r'^[A-Za-z0-9_-]+$', password)
    mysql("CREATE DATABASE IF NOT EXISTS ppci_dtx CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
          "CREATE USER IF NOT EXISTS 'ppci_dtx'@'%' IDENTIFIED BY '" + password + "';\n"
          "GRANT ALL PRIVILEGES ON ppci_dtx.* TO 'ppci_dtx'@'%';\n")
    return password


def configure(password, bootstrap):
    keys = SOURCE / 'PaddleDTX/testdata/xdb/data1/keys'
    pub = (keys / 'public.key').read_text().strip()
    pri = (keys / 'private.key').read_text().strip()
    assert re.match(r'^[a-fA-F0-9]+$', pub) and re.match(r'^[a-fA-F0-9]+$', pri)
    secret = STATE / 'private/session-key'
    if not secret.exists():
        private_file(secret, secrets.token_hex(16))
    app = '''appname = ppci-dtx-manager
httpaddr = {listen}
httpport = 8488
runmode = prod
copyrequestbody = true
dbUser = ppci_dtx
dbPassword = {db_password}
dbHost = mysql
dbPort = 3306
dbName = ppci_dtx
runSyncdb = true
logLevel = 6
logPath = ./log
secretKey = {secret}
localPath = /home/data
[orginfo]
id = ppci-office-alice
name = PPCI Office Alice
did = ppci-office-alice
pubkey = {pub}
prikey = {pri}
[xdb]
name = data-node1
host = dataowner1.node.com:80
nodeID = {pub}
privatekey = {pri}
namespace = paddlempc
'''.format(listen='127.0.0.1' if bootstrap else '0.0.0.0', db_password=password,
           secret=secret.read_text(), pub=pub, pri=pri)
    private_file(STATE / 'conf/app.conf', app)
    config = SOURCE / 'PaddleDTX/testdata/executor/node1/conf/requester-config.toml'
    match = re.search(r'(?im)^\s*mnemonic\s*=\s*[\'"]([^\'"]+)[\'"]', config.read_text())
    if not match:
        raise RuntimeError('Missing existing requester identity; refusing to generate a replacement')
    private_file(STATE / 'conf/blockchain.toml', '''[blockchain]
type = "xchain"
[blockchain.xchain]
mnemonic = {mnemonic}
dtxContractName = "paddlempc"
managerContractName = "data"
contractAccount = "{account}"
chainAddress = "xchain1.node.com:37101"
chainName = "xuper"
'''.format(mnemonic=json.dumps(match.group(1)), account=ACCOUNT))


def install():
    image_context = BUILD / 'image'
    image_context.mkdir(exist_ok=True)
    shutil.copy2(str(BUILD / 'bin/dtx-manager'), str(image_context / 'dtx-manager'))
    shutil.copy2('/usr/share/zoneinfo/Asia/Shanghai', str(image_context / 'localtime'))
    shutil.copy2('/etc/pki/tls/certs/ca-bundle.crt', str(image_context / 'ca-certificates.crt'))
    (image_context / 'Dockerfile').write_text('''FROM scratch
COPY dtx-manager /home/dtx-manager
COPY localtime /etc/localtime
COPY ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
WORKDIR /home
ENTRYPOINT ["/home/dtx-manager"]
''')
    call(['docker', 'build', '-t', IMAGE, image_context])
    current = call(['docker', 'inspect', CONTAINER], check=False)
    if current.returncode == 0:
        raise RuntimeError('Existing recovery manager retained; inspect it instead of recreating')
    gateway = call(['docker', 'exec', 'paddledtx-native-e2e', 'getent', 'hosts', 'host.docker.internal']).stdout.split()[0]
    args = ['docker', 'create', '--name', CONTAINER, '--network', 'ppci-blockchain-network',
            '--restart', 'unless-stopped', '--read-only', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--memory', '512m', '--cpus', '2',
            '-e', 'GOMAXPROCS=2', '--tmpfs', '/tmp:rw,nosuid,noexec,size=16m',
            '-p', '127.0.0.1:8084:8488', '-p', gateway + ':8084:8488']
    for directory in ('conf', 'log', 'data', 'upload'):
        args += ['-v', str(STATE / directory) + ':/home/' + directory + (':ro' if directory == 'conf' else ':rw')]
    call(args + [IMAGE])
    call(['docker', 'network', 'connect', 'mysql_default', CONTAINER])
    call(['docker', 'start', CONTAINER])


def finish_bootstrap(password):
    for _ in range(60):
        result = call(['docker', 'inspect', CONTAINER, '--format', '{{.State.Running}}'])
        if result.stdout.strip() != 'true':
            raise RuntimeError('Manager bootstrap exited; inspect its server log')
        try:
            rows = mysql("SELECT salt FROM ppci_dtx.common_user WHERE username='admin';\n").strip().splitlines()
        except RuntimeError:
            rows = []
        if rows:
            break
        time.sleep(1)
    else:
        raise RuntimeError('Manager did not initialize its dedicated database')
    # Existing salt also encrypts the user's signing key; never change it here.
    admin = json.loads((STATE / 'private/credentials.json').read_text())
    wire = hashlib.md5(admin['password'].encode()).hexdigest()
    digest = base64.b64encode(hashlib.md5((wire + rows[0]).encode()).digest()).decode()
    mysql("UPDATE ppci_dtx.common_user SET password='" + digest + "' WHERE username='admin';\n")
    call(['docker', 'stop', '-t', '15', CONTAINER])
    configure(password, bootstrap=False)
    call(['docker', 'start', CONTAINER])


def restore_native_login():
    """Disable the retired anonymous demo in the source and the served HTML."""
    if os.geteuid() != 0:
        raise RuntimeError('Run on the office server as root')
    assert (STATE / 'conf/app.conf').is_file(), 'Restore the real manager before enabling its login'
    frontend = SOURCE / 'dtx-fe'
    files = [('source', frontend / 'src/public/index.html'),
             ('served', frontend / 'build/static/unicom-dtx/page/index.html')]
    enabled = 'window.__DTX_DEMO_AUTH_DISABLED__ = true;'
    disabled = 'window.__DTX_DEMO_AUTH_DISABLED__ = false;'
    for _, path in files:
        text = path.read_text()
        if text.count(enabled) + text.count(disabled) != 1:
            raise RuntimeError('Unrecognized native login flag retained: ' + str(path))
    backup = BACKUP / 'native-login-before'
    backup.mkdir(mode=0o700, parents=True, exist_ok=True)
    for label, path in files:
        saved = backup / (label + '-index.html')
        if not saved.exists():
            shutil.copy2(str(path), str(saved))
            saved.chmod(0o600)
    if enabled in files[0][1].read_text():
        patch = SCRIPTS / 'patches/paddledtx-native-login.patch'
        call(['git', 'apply', '--check', patch], cwd=frontend)
        call(['git', 'apply', patch], cwd=frontend)
    served = files[1][1]
    text = served.read_text().replace(enabled, disabled)
    old_comment = ('// The local interoperability demo intentionally has no login wall. The\n'
                   '      // native DTX layout and routes remain unchanged; only the demo auth gate\n'
                   '      // and request signature are disabled when no user profile exists.')
    text = text.replace(old_comment, '// The restored manager requires normal login and signed requests.')
    temporary = served.with_name(served.name + '.login-recovery')
    temporary.write_text(text)
    temporary.chmod(served.stat().st_mode & 0o777)
    os.replace(str(temporary), str(served))
    record = []
    for label, path in files:
        assert disabled in path.read_text() and enabled not in path.read_text()
        record.append({'file': str(path), 'before_sha256': hashlib.sha256(
            (backup / (label + '-index.html')).read_bytes()).hexdigest(),
            'after_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    private_file(BACKUP / 'native-login-deployment.json', json.dumps({
        'demo_auth_disabled': False, 'files': record,
        'login_route': '/dtx/console/login', 'logout_route': '/dtx/console/logout',
        'browser_state_changed': False}, indent=2))
    print('Native source/served HTML now require normal login; browser state was not changed.')


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Run on the office server as root')
    for filename in ('mysql-before.sql.gz', 'xchain1-rootfs-before.tar.gz',
                     'xchain1-mounted-before.tar.gz', 'containers-before.json'):
        assert (BACKUP / filename).is_file(), 'Required pre-change recovery backup is missing'
    existing = call(['docker', 'inspect', CONTAINER], check=False)
    if existing.returncode == 0:
        raise RuntimeError('Existing recovery manager retained; no overwrite attempted')
    archive = BACKUP / 'manager-source-before.tar.gz'
    if not archive.exists():
        call(['tar', '--exclude=dtx-manager/.git', '--exclude=dtx-manager/log',
              '--exclude=dtx-manager/bin', '-czf', archive, '-C', SOURCE, 'dtx-manager',
              'PaddleDTX/dai/vendor/github.com/xuperchain/xuperchain',
              'PaddleDTX/dai/vendor/github.com/go-playground', 'PaddleDTX/dai/vendor/github.com/leodido'])
        archive.chmod(0o600)
    build()
    contract()
    password = credentials()
    configure(password, bootstrap=True)
    install()
    finish_bootstrap(password)
    restore_native_login()
    private_file(BACKUP / 'manager-release.json', json.dumps({
        'container': CONTAINER, 'image': IMAGE, 'database': 'ppci_dtx',
        'binary_sha256': hashlib.sha256((BUILD / 'bin/dtx-manager').read_bytes()).hexdigest(),
        'contract_binary_sha256': hashlib.sha256((BUILD / 'bin/dtxmanager-native').read_bytes()).hexdigest(),
        'original_source_archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'credentials_path': str(STATE / 'private/credentials.json')}, indent=2))
    print('Manager installed; run check_paddledtx_manager.go for signed API acceptance.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-login-only', action='store_true',
                        help='restore native login without reinstalling the manager')
    args = parser.parse_args()
    if args.native_login_only:
        restore_native_login()
    else:
        main()
