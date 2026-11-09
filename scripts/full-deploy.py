#!/usr/bin/env python3
"""Build and initialize the complete, independent Linux amd64 demo topology."""
import argparse
import hashlib
import importlib.util
import ipaddress
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
import urllib.request
import uuid

SOURCE = Path(os.environ.get('PPCI_SOURCE_ROOT', Path(__file__).resolve().parents[1])).resolve()
ROOT = Path(os.environ.get('PPCI_ROOT', '/opt/ppci')).resolve()
BUILD = Path(os.environ.get('PPCI_BUILD_ROOT', '/opt/ppci-build')).resolve()
ENVIRONMENTS = SOURCE / 'platform/scripts/environments'
REGISTRY = 'secretflow-registry.cn-hangzhou.cr.aliyuncs.com/secretflow/'
SF_IMAGE = REGISTRY + 'secretflow-lite-anolis8:1.11.0b1'
FATE_IMAGE = 'ppci/fate:portable'
CPP_IMAGE = 'ppci/bfia-cpp:numerics-20260914-v2'
ALIASES = [REGISTRY + name + ':latest' for name in
           ('ecdh', 'ecdh-psi', 'ss-compare', 'ss-lr', 'ss-pearson', 'ss-vif', 'ss-xgb')]
IMAGES = ['ppci/kuscia:home-20260912', 'secretflow/fate2-adapter:0.2.0-native',
          FATE_IMAGE, SF_IMAGE, *ALIASES,
          'registry.baidubce.com/paddledtx/xchain:v3.9',
          'registry.baidubce.com/paddledtx/xdb-storage:2.1',
          'registry.baidubce.com/paddledtx/paddledtx-visual:1.0',
          'ppci/paddledtx-xdb:portable', 'ppci/paddledtx-dai:portable',
          'ppci/paddledtx-dtx-manager:portable', 'ppci/paddledtx-dtx-ui:portable',
          os.environ.get('PPCI_DTX_MYSQL_IMAGE', 'mysql:8.0')]
INTERNAL_NETWORKS = {'kuscia-exchange': '192.168.117.0/24', 'blockchain_network': '172.31.1.0/24'}


def run(*args, **kwargs):
    print('+', ' '.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def configuration(host, cidr):
    address = ipaddress.IPv4Address(host)
    if not any(address in ipaddress.IPv4Network(net) for net in ('127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')):
        raise ValueError('--host must be a loopback or private LAN IPv4 address assigned to this machine')
    network = ipaddress.IPv4Network(cidr or str(address) + '/24', strict=False)
    if address not in network or network.prefixlen < 8:
        raise ValueError('--lan-cidr must contain --host and be restricted to the deployment LAN')
    private = [ipaddress.IPv4Network(net) for net in ('127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')]
    if not any(network.subnet_of(net) for net in private):
        raise ValueError('--lan-cidr must stay inside loopback or RFC1918 private address space')
    for path in (SOURCE, ROOT, BUILD):
        if str(path) == '/' or any(c.isspace() or c in ':\n\r' for c in str(path)):
            raise ValueError('Deployment paths must be absolute, non-root paths without whitespace or colons')
    if any(a == b or a in b.parents or b in a.parents for a, b in ((SOURCE, ROOT), (SOURCE, BUILD), (ROOT, BUILD))):
        raise ValueError('Source, build and runtime directories must be separate')
    return {'host': str(address), 'lan_cidr': str(network)}


def validate_routes(routes, networks):
    """Only the project's existing Docker bridges may route its fixed subnets."""
    allowed = {}
    reserved = {name: ipaddress.IPv4Network(cidr) for name, cidr in INTERNAL_NETWORKS.items()}
    for network in networks:
        subnets = [ipaddress.ip_network(item['Subnet'], strict=False)
                   for item in (network.get('IPAM', {}).get('Config') or []) if item.get('Subnet')]
        ipv4 = [subnet for subnet in subnets if subnet.version == 4]
        name = network['Name']
        if name in reserved:
            if ipv4 != [reserved[name]]:
                raise RuntimeError('Project Docker network has an unexpected subnet: ' + name)
            bridge = (network.get('Options') or {}).get('com.docker.network.bridge.name') or 'br-' + network['Id'][:12]
            allowed[name] = bridge
        elif any(subnet.overlaps(internal) for subnet in ipv4 for internal in reserved.values()):
            raise RuntimeError('Another Docker network overlaps a required internal subnet: ' + name)
    for route in routes:
        destination = route.get('dst', 'default')
        if destination in ('default', '0.0.0.0/0'):
            continue
        subnet = ipaddress.ip_network(destination, strict=False)
        if subnet.version != 4:
            continue
        for name, internal in reserved.items():
            if subnet.overlaps(internal) and not (name in allowed and subnet.subnet_of(internal) and route.get('dev') == allowed[name]):
                raise RuntimeError(f'Host route {destination} on {route.get("dev", "unknown")} overlaps required {internal}')


def preflight(offline=False):
    if platform.system() != 'Linux' or platform.machine().lower() not in ('x86_64', 'amd64'):
        raise RuntimeError('Run the full stack inside Linux amd64; use the root ARM VM command on arm64 hosts')
    if os.geteuid() != 0 or not Path('/run/systemd/system').is_dir():
        raise RuntimeError('Root and a running systemd host are required')
    required = ('docker', 'java', 'keytool', 'rsync', 'nginx', 'openssl', 'rg', 'flock', 'timeout', 'ip')
    missing = [name for name in required if not shutil.which(name)]
    if missing:
        raise RuntimeError('Missing dependencies; run ./deploy.sh bootstrap: ' + ', '.join(missing))
    run('docker', 'info', stdout=subprocess.DEVNULL)
    identifiers = subprocess.check_output(['docker', 'network', 'ls', '--quiet'], text=True).split()
    networks = json.loads(subprocess.check_output(['docker', 'network', 'inspect', *identifiers], text=True)) if identifiers else []
    routes = json.loads(subprocess.check_output(['ip', '-j', 'route', 'show'], text=True))
    validate_routes(routes, networks)
    if shutil.which('getenforce') and subprocess.check_output(['getenforce'], text=True).strip() != 'Disabled':
        missing = [name for name in ('semanage', 'restorecon', 'setsebool') if not shutil.which(name)]
        if missing:
            raise RuntimeError('SELinux requires policycoreutils-python-utils: ' + ', '.join(missing))
    for node in ('alice', 'bob', 'kimi'):
        unit = Path('/etc/systemd/system/ppci-' + node + '.service')
        if unit.exists() and not unit.read_text().startswith('# Managed by PPCI'):
            raise RuntimeError('Existing unmanaged deployment; fresh installer will not overwrite ' + str(unit))
    if offline:
        for tag in IMAGES:
            run('docker', 'image', 'inspect', tag, stdout=subprocess.DEVNULL)


def build_fate():
    """Compile the reviewed compatibility classes against the official distribution."""
    context = BUILD / 'fate-image'
    context.mkdir(parents=True, exist_ok=True)
    board = SOURCE / 'platform/fate/fate_board/src/main/java/org/fedai/fate/board'
    files = ('websocket/JobWebSocketController.java', 'services/JobWebSocketService.java',
             'controller/JobManagerController.java', 'services/JobDetailService.java',
             'websocket/LogWebSocketController.java', 'controller/JobDetailController.java')
    reviewed = context / 'reviewed-source'
    staged_board = reviewed / 'board'
    for name in files:
        target = staged_board / 'src/main/java/org/fedai/fate/board' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(board / name, target)
    staged_flow = reviewed / 'flow'
    parser = staged_flow / 'python/fate_flow/controller/parser.py'
    parser.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE / 'platform/fate/fate_flow/python/fate_flow/controller/parser.py', parser)
    for directory, name in ((staged_flow, 'flow.patch'), (staged_board, 'board-string-party-id.patch')):
        patch = SOURCE / 'platform/patches/fate' / name
        check = subprocess.run(['git', '-C', str(directory), 'apply', '--reverse', '--check', str(patch)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if check.returncode:
            subprocess.run(['git', '-C', str(directory), 'apply', '--check', str(patch)], check=True)
            subprocess.run(['git', '-C', str(directory), 'apply', str(patch)], check=True)
    sources = context / 'sources'
    sources.mkdir(exist_ok=True)
    for name in files:
        shutil.copy2(staged_board / 'src/main/java/org/fedai/fate/board' / name, sources / Path(name).name)
    if 'String partyId' not in (sources / 'JobWebSocketService.java').read_text():
        raise RuntimeError('Reviewed FATE string party-ID patch was not applied')
    shutil.copy2(parser, context / 'parser.py')
    (context / 'Dockerfile').write_text('''FROM federatedai/standalone_fate:2.2.0
USER root
COPY sources /tmp/ppci-board-source
RUN cd /data/projects/fate/fateboard && mkdir -p /tmp/ppci-board-classes && \\
    /data/projects/fate/env/jdk/jdk-8u345/bin/javac -encoding UTF-8 -cp 'fateboard.jar:lib/*' -d /tmp/ppci-board-classes /tmp/ppci-board-source/*.java && \\
    /data/projects/fate/env/jdk/jdk-8u345/bin/jar uf fateboard-2.1.0.jar -C /tmp/ppci-board-classes . && \\
    rm -rf /tmp/ppci-board-source /tmp/ppci-board-classes
COPY parser.py /data/projects/fate/fate_flow/python/fate_flow/controller/parser.py
''')
    run('docker', 'build', '-t', FATE_IMAGE, context)


def build():
    for command in ('go', 'mvn', 'node', 'pnpm'):
        if not shutil.which(command):
            raise RuntimeError('Missing build tool: ' + command)
    BUILD.mkdir(parents=True, exist_ok=True)
    for component in ('backend', 'kimi', 'frontend'):
        run('bash', SOURCE / 'platform/scripts/linux-migration/build-platform.sh', component)
    for component in ('kuscia', 'adapter'):
        run('bash', ENVIRONMENTS / 'build-runtime.sh', component)
    run(sys.executable, SOURCE / 'scripts/deploy-paddledtx-full.py', 'build')
    tools = BUILD / 'tools'
    tools.mkdir(exist_ok=True)
    bazel = tools / 'bazel-6.5.0'
    if not bazel.exists():
        url = 'https://github.com/bazelbuild/bazel/releases/download/6.5.0/bazel-6.5.0-linux-x86_64'
        temporary = bazel.with_suffix('.download')
        urllib.request.urlretrieve(url, temporary)
        expected = 'a40ac69263440761199fcb8da47ad4e3f328cbe79ffbf4ecc14e5ba252857307'
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != expected:
            temporary.unlink()
            raise RuntimeError('Bazel checksum mismatch')
        temporary.rename(bazel)
    for stage in ('build', 'base', 'image', 'python'):
        run(sys.executable, ENVIRONMENTS / 'build-bfia.py', stage)
    context = BUILD / 'bfia-suite-image'
    run(sys.executable, SOURCE / 'images/bfia-suite/prepare-context.py', '--output', context,
        '--rg', '/opt/ppci-tools/rg/rg')
    if (SOURCE / '.git').exists():
        revision = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
    else:
        revision = json.loads((SOURCE / '.ppci-source.json').read_text())['revision']
    suite_tag = 'ppci/bfia-suite:source-' + revision[:12]
    run('docker', 'build', '--build-arg', 'SOURCE_REVISION=' + revision,
        '--build-arg', 'BFIA_CPP_IMAGE=' + CPP_IMAGE,
        '--build-arg', 'BFIA_PYTHON_BASE=ppci/bfia-python:amd64-20260908', '-t', suite_tag, context)
    build_fate()
    for tag in IMAGES:
        if subprocess.run(['docker', 'image', 'inspect', tag], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            run('docker', 'pull', tag)
    (BUILD / 'release-images.json').write_text(json.dumps([*IMAGES, suite_tag], indent=2) + '\n')
    (BUILD / '.ppci-prebuilt-artifacts').write_text('PPCI prebuilt artifacts\n')


def provisioner():
    sys.path.insert(0, str(ENVIRONMENTS))
    spec = importlib.util.spec_from_file_location('provision', ENVIRONMENTS / 'provision.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wait_http(url, seconds=180):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with opener.open(url, timeout=3) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(2)
    raise RuntimeError('Service did not become ready: ' + url)


def fateboards(p):
    for role, port in [('guest', 19483), ('host', 19484)]:
        state = ROOT / 'fateboard' / role
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        credentials = state / 'credentials.properties'
        if not credentials.exists():
            credentials.write_text('server.board.login.username=ppci_fate_' + role +
                                   '\nserver.board.login.password=' + secrets.token_hex(24) + '\n')
            credentials.chmod(0o600)
        command = '''set -eu
cd /data/projects/fate/fateboard
sed -E '/^(fateflow\\.(url|url-list|http_app_key|http_secret_key)|server\\.board\\.(login|encrypt)\\.[^=]+|server\\.servlet\\.session\\.cookie\\.name|zookeeper\\.enable)=/d' conf/application.properties > /tmp/ppci-board.properties
printf '\\nfateflow.url=http://fate2-flow-%s-e2e:9380\\nzookeeper.enable=false\\nserver.board.encrypt.enable=false\\nserver.servlet.session.cookie.name=PPCI_FATE_%s_SESSION\\n' "$PPCI_FATE_ROLE" "$PPCI_FATE_ROLE" >> /tmp/ppci-board.properties
cat /run/ppci-credentials.properties >> /tmp/ppci-board.properties
exec /data/projects/fate/env/jdk/jdk-8u345/bin/java -Xms128m -Xmx512m -XX:ActiveProcessorCount=2 -Dspring.config.location=/tmp/ppci-board.properties -Dssh_config_file=/data/projects/fate/fateboard/ssh/ -cp 'lib/*:fateboard.jar' org.fedai.fate.board.bootstrap.Bootstrap
'''
        name = 'fateboard-native-e2e' if role == 'guest' else 'fateboard-host-native-e2e'
        p.ensure_container(name, ['--network', 'kuscia-exchange', '--cpus', '2', '--memory', '1g',
            '-p', f'127.0.0.1:{port}:8080', '-e', 'PPCI_FATE_ROLE=' + role,
            '-v', f'{credentials}:/run/ppci-credentials.properties:ro',
            '--entrypoint', '/bin/bash', FATE_IMAGE, '-c', command])
        wait_http(f'http://127.0.0.1:{port}/')


def retain_previous_container(name, image):
    previous = subprocess.run(['docker', 'inspect', name], capture_output=True, text=True)
    if previous.returncode:
        return
    info = json.loads(previous.stdout)[0]
    if info['Config'].get('Labels', {}).get('io.ppci.environment') != 'portable':
        raise RuntimeError('Refusing to replace an unmanaged container: ' + name)
    wanted = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image]))[0]['Id']
    if info['Image'] == wanted:
        return
    rollback = name + '-rollback-' + uuid.uuid4().hex[:12]
    run('docker', 'stop', '--time', '30', name)
    run('docker', 'rename', name, rollback)
    for network in info['NetworkSettings']['Networks']:
        run('docker', 'network', 'disconnect', network, rollback)
    print('Previous container retained: ' + rollback)


def import_engines():
    shared = ROOT / 'images'
    shared.mkdir(parents=True, exist_ok=True)
    groups = [('native.tar', [SF_IMAGE], ('alice', 'kimi')),
              ('fate-adapter.tar', ['secretflow/fate2-adapter:0.2.0-native'], ('alice',)),
              ('bfia-cpp.tar', [CPP_IMAGE, *ALIASES], ('alice', 'bob'))]
    for filename, tags, nodes in groups:
        archive = shared / filename
        run('docker', 'save', '-o', archive, *tags)
        for node in nodes:
            container = 'gaofeng-kuscia-autonomy-' + node
            run('docker', 'exec', container, 'kuscia', 'image', 'load', '-i', '/home/kuscia/var/images/' + filename)
    container = 'gaofeng-kuscia-autonomy-alice'
    run('docker', 'exec', '-i', container, 'kubectl', 'apply', '-f', '-',
        input=(SOURCE / 'platform/thirdparty/fate2-adapter/scripts/app_image.fate2.yaml').read_text(), text=True)


def selinux():
    if not shutil.which('getenforce') or subprocess.check_output(['getenforce'], text=True).strip() == 'Disabled':
        return
    run('setsebool', '-P', 'httpd_can_network_connect', 'on')
    pattern = str(ROOT / 'NewProject/secretpad-frontend-dist-e2e') + '(/.*)?'
    existing = subprocess.check_output(['semanage', 'fcontext', '-l', '-C'], text=True)
    action = '-m' if any(line.split() and line.split()[0] == pattern for line in existing.splitlines()) else '-a'
    run('semanage', 'fcontext', action, '-t', 'httpd_sys_content_t', pattern)
    labels = subprocess.check_output(['semanage', 'port', '-l'], text=True)
    for port in (18101, 28101, 38101, 19383, 19384, 18511):
        owner = None
        for line in labels.splitlines():
            fields = line.split(None, 2)
            if len(fields) != 3 or fields[1] != 'tcp':
                continue
            for first, last in re.findall(r'(\d+)(?:-(\d+))?', fields[2]):
                if int(first) <= port <= int(last or first):
                    if fields[0] not in ('port_t', 'unreserved_port_t', 'reserved_port_t'):
                        owner = fields[0]
        if owner and owner != 'http_port_t':
            raise RuntimeError(f'SELinux TCP port {port} belongs to {owner}; choose a dedicated host')
        if not owner:
            run('semanage', 'port', '-a', '-t', 'http_port_t', '-p', 'tcp', port)


def deploy(env, offline):
    preflight(offline)
    metadata = BUILD / 'runtime-release.json'
    if not metadata.is_file():
        raise RuntimeError('Missing runtime release metadata; run deploy.sh all or restore a published release package')
    release = json.loads(metadata.read_text())
    if not isinstance(release, dict) or release.get('format') != 2 or not isinstance(release.get('images'), list):
        raise RuntimeError('Unsupported runtime release metadata')
    suites = [image for image in release['images']
              if isinstance(image, dict) and image.get('component') == 'bfia-suite']
    if len(suites) != 1 or not all(isinstance(suites[0].get(key), str) for key in ('reference', 'tag', 'id')):
        raise RuntimeError('Runtime release must identify one pinned BFIA suite image')
    suite = suites[0]
    actual = json.loads(subprocess.check_output(['docker', 'image', 'inspect', suite['tag']], text=True))[0]
    if actual['Architecture'] != 'amd64' or actual['Id'] != suite['id']:
        raise RuntimeError('Runtime BFIA suite image does not match the release')
    if not offline:
        for tag in IMAGES:
            run('docker', 'image', 'inspect', tag, stdout=subprocess.DEVNULL)
    p = provisioner()
    p.prepare()
    for name in ('fate2-flow-guest-e2e', 'fate2-flow-host-e2e', 'fateboard-native-e2e', 'fateboard-host-native-e2e'):
        retain_previous_container(name, FATE_IMAGE)
    p.fate()
    for port in (19381, 19382):
        wait_http(f'http://127.0.0.1:{port}/v2/site/info/query')
    fateboards(p)
    nodes = ['gaofeng-kuscia-autonomy-' + node for node in ('alice', 'bob', 'kimi')]
    present = [subprocess.run(['docker', 'inspect', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
               for name in nodes]
    if all(present):
        p.upgrade_kuscia()
    else:
        p.kuscia()
    run(sys.executable, SOURCE / 'scripts/bfia-suite-kuscia.py', 'install', '--runtime-root', ROOT,
        '--image-ref', suite['reference'], '--image-tag', suite['tag'], '--image-id', suite['id'])
    import_engines()
    run(sys.executable, ENVIRONMENTS / 'paddle-provision.py', 'all')
    run(sys.executable, SOURCE / 'scripts/deploy-paddledtx-full.py', 'deploy')
    for repo in ('secretpad', 'secretpad-kimi-upstream'):
        jar = ROOT / 'NewProject' / repo / 'target/secretpad.jar'
        if jar.exists():
            backup = Path('/var/backups/ppci/releases') / (time.strftime('%Y%m%d-%H%M%S') + '-' + repo)
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(jar, backup / jar.name)
        shutil.copy2(BUILD / repo / 'target/secretpad.jar', jar.with_suffix('.jar.next'))
        jar.with_suffix('.jar.next').replace(jar)
    p.platform()
    run('systemctl', 'restart', 'ppci-alice', 'ppci-bob', 'ppci-kimi')
    for port in (18080, 28090, 38090):
        wait_http(f'http://127.0.0.1:{port}/actuator/health')
    selinux()
    p.gateway(env)
    if shutil.which('restorecon'):
        run('restorecon', '-RF', ROOT / 'NewProject/secretpad-frontend-dist-e2e')
    for port in (18101, 28101, 38101, 19383, 19384):
        wait_http(f'http://{env["host"]}:{port}/')
    wait_http(f'http://{env["host"]}:18511/dtx/console/login')
    run(sys.executable, ENVIRONMENTS / 'bfia-partners.py')
    run(sys.executable, ENVIRONMENTS / 'paddle-demo-data.py')
    run(sys.executable, ENVIRONMENTS / 'portablectl.py', 'status')
    print('FATEBoard credentials are local-only: ' + str(ROOT / 'fateboard/{guest,host}/credentials.properties'))


def algorithms():
    result = Path('/var/log/ppci/bfia-suite')
    identifier = str(uuid.uuid4())
    (result / 'runs' / identifier).mkdir(parents=True, mode=0o700)
    run('bash', SOURCE / 'platform/scripts/linux-migration/run-bfia-suite.sh', identifier,
        env=dict(os.environ, PPCI_BFIA_SUITE_ROOT=str(result)))
    for name in ('native-smoke.py', 'secretflow-smoke.py', 'bfia-smoke.py'):
        run(sys.executable, ENVIRONMENTS / name)
    run(sys.executable, SOURCE / 'scripts/paddle-smoke.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('preflight', 'build', 'deploy', 'status', 'run'))
    parser.add_argument('--host', required=True)
    parser.add_argument('--lan-cidr')
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    env = configuration(args.host, args.lan_cidr)
    public_host = str(ipaddress.IPv4Address(os.environ.get('PPCI_PUBLIC_HOST', env['host'])))
    no_proxy = ','.join(filter(None, (os.environ.get('no_proxy', os.environ.get('NO_PROXY', '')),
                                    'localhost', '127.0.0.1', env['host'])))
    os.environ.update(PPCI_SOURCE_ROOT=str(SOURCE), PPCI_ROOT=str(ROOT), PPCI_BUILD_ROOT=str(BUILD),
        PPCI_PUBLIC_HOST=public_host, PPCI_LAN_CIDR=env['lan_cidr'], PPCI_FATE_EXTERNAL_BOARD='1',
        PPCI_FATE_IMAGE=FATE_IMAGE, PPCI_NATIVE_UI_PORT='18088', PPCI_TARGET_ARCH='amd64',
        PPCI_PADDLE_DAI_IMAGE='ppci/paddledtx-dai:portable',
        PPCI_PADDLE_XDB_IMAGE='ppci/paddledtx-xdb:portable', NO_PROXY=no_proxy, no_proxy=no_proxy, USER='gaofeng')
    if not os.environ.get('JAVA_HOME') and shutil.which('java'):
        os.environ['JAVA_HOME'] = str(Path(shutil.which('java')).resolve().parents[1])
    if args.stage == 'preflight':
        preflight(args.offline)
    elif args.stage == 'build':
        if args.offline:
            raise RuntimeError('Offline packages already contain builds; use deploy --offline')
        preflight()
        build()
    elif args.stage == 'deploy':
        deploy(env, args.offline)
    elif args.stage == 'status':
        run(sys.executable, ENVIRONMENTS / 'portablectl.py', 'status')
    else:
        algorithms()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print('PPCI: ' + str(error), file=sys.stderr)
        sys.exit(1)
