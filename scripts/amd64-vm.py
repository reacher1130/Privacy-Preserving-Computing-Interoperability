#!/usr/bin/env python3
"""Run the amd64 platform in a persistent QEMU guest on an ARM Linux host.

Only --bootstrap installs host packages. Existing disks and SSH identities are
retained; this helper never recreates an existing guest to repair a failure.
"""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import posixpath
import re
import shlex
import shutil
import socket
import subprocess
import tarfile
import time
import urllib.request
import uuid

IMAGE_NAME = 'ubuntu-24.04-server-cloudimg-amd64.img'
IMAGE_BASE = 'https://cloud-images.ubuntu.com/releases/noble/release/'
WEB_PORTS = (18101, 28101, 38101, 18103, 38103, 19383, 19384, 18511)
SERVICE = 'ppci-amd64-vm.service'
UNIT = Path('/etc/systemd/system') / SERVICE
MARKER = '# Managed by PPCI scripts/amd64-vm.py\n'
REQUIRED = ('qemu-system-x86_64', 'qemu-img', 'cloud-localds', 'ssh', 'scp', 'ssh-keygen', 'systemctl')


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def qemu_binary():
    binary = shutil.which('qemu-system-x86_64')
    if binary:
        return binary
    fallback = Path('/usr/libexec/qemu-kvm')
    if fallback.is_file():
        result = subprocess.run([str(fallback), '-machine', 'help'], capture_output=True, text=True, timeout=15)
        if result.returncode == 0 and re.search(r'\bpc-(?:q35|i440fx)-', result.stdout):
            return str(fallback)
    return None


def missing_tools(options=None):
    required = list(REQUIRED)
    if options and not ipaddress.IPv4Address(options.bind_address).is_loopback:
        required.append('iptables')
    return [tool for tool in required
            if not (qemu_binary() if tool == 'qemu-system-x86_64' else shutil.which(tool))]


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def checksum_for(text, name=IMAGE_NAME):
    matches = [row.split()[0] for row in text.splitlines()
               if len(row.split()) == 2 and row.split()[1].lstrip('*') == name]
    if len(matches) != 1 or not re.fullmatch('[0-9a-f]{64}', matches[0]):
        raise RuntimeError('Official SHA256SUMS has no unambiguous image checksum')
    return matches[0]


def bootstrap():
    if shutil.which('apt-get'):
        run('apt-get', 'update')
        run('apt-get', 'install', '-y', 'qemu-system-x86', 'qemu-utils', 'cloud-image-utils', 'openssh-client', 'iptables')
    else:
        manager = shutil.which('dnf') or shutil.which('yum')
        if not manager:
            raise RuntimeError('Install QEMU x86 system emulation and cloud-localds using your distribution package manager')
        # Cross-architecture QEMU packages depend on the enabled distribution repositories.
        run(manager, 'install', '-y', 'qemu-system-x86', 'qemu-img', 'cloud-utils', 'openssh-clients', 'iptables')


def check(options):
    missing = missing_tools(options)
    report = {'host_os': platform.system(), 'host_arch': platform.machine(),
              'guest_arch': 'amd64', 'acceleration': 'tcg', 'missing_tools': missing,
              'state_dir': str(options.state_dir), 'web_bind': options.bind_address,
              'allowed_lan': lan_cidr(options),
              'web_ports': list(WEB_PORTS), 'real_arm_acceptance': False}
    print(json.dumps(report, indent=2))
    if platform.system() != 'Linux':
        raise RuntimeError('This VM helper requires a Linux host with systemd')
    if missing:
        raise RuntimeError('Missing host tools: ' + ', '.join(missing) + '; use --bootstrap to install available distribution packages')
    if not Path('/run/systemd/system').is_dir():
        raise RuntimeError('systemd must be running on the host')


def image(state, local=None, local_sha=None):
    base = state / IMAGE_NAME
    digest_file = state / 'base-image.sha256'
    if base.exists():
        if not digest_file.is_file() or not re.fullmatch('[0-9a-f]{64}', digest_file.read_text().strip()):
            raise RuntimeError('Existing VM base image has no recorded checksum; retained without modification')
        if sha256(base) != digest_file.read_text().strip():
            raise RuntimeError('Cached VM base image checksum mismatch; retained without modification')
        return base
    if local:
        if not local_sha or not re.fullmatch('[0-9a-f]{64}', local_sha):
            raise RuntimeError('--base-image requires --base-image-sha256 from the official Ubuntu SHA256SUMS')
        expected = local_sha
    else:
        with urllib.request.urlopen(IMAGE_BASE + 'SHA256SUMS', timeout=60) as response:
            expected = checksum_for(response.read().decode('ascii'))
    temporary = state / (IMAGE_NAME + '.' + str(uuid.uuid4()) + '.part')
    try:
        response = local.open('rb') if local else urllib.request.urlopen(IMAGE_BASE + IMAGE_NAME, timeout=120)
        with response, temporary.open('xb') as out:
            shutil.copyfileobj(response, out, 1024 * 1024)
        if sha256(temporary) != expected:
            raise RuntimeError('Ubuntu image SHA256 mismatch; no guest disk created')
        temporary.rename(base)
        digest_file.write_text(expected + '\n')
    finally:
        temporary.unlink(missing_ok=True)
    return base


def cloud_config(public_key):
    if not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/=]+(?: [^\r\n]+)?', public_key):
        raise RuntimeError('Invalid generated SSH public key')
    return '#cloud-config\n' + json.dumps({
        'hostname': 'ppci-amd64', 'ssh_pwauth': False, 'disable_root': True,
        'users': [{'name': 'ppci', 'lock_passwd': True, 'shell': '/bin/bash',
                   'sudo': 'ALL=(ALL) NOPASSWD:ALL', 'ssh_authorized_keys': [public_key]}],
        'growpart': {'mode': 'auto', 'devices': ['/'], 'ignore_growroot_disabled': False},
        'resize_rootfs': True,
    }, indent=2) + '\n'


def settings(options):
    return {'version': 1, 'state_dir': str(options.state_dir),
            'memory_mib': options.memory_mib, 'cpus': options.cpus,
            'ssh_port': options.ssh_port, 'bind_address': options.bind_address,
            'lan_cidr': lan_cidr(options)}


def lan_cidr(options):
    host = ipaddress.IPv4Address(options.bind_address)
    network = ipaddress.IPv4Network(options.lan_cidr or ('127.0.0.0/8' if host.is_loopback else str(host) + '/32'))
    if host not in network:
        raise RuntimeError('--lan-cidr must include --bind-address')
    return str(network)


def reuse_settings(options):
    if options.command not in ('run', 'package', 'status'):
        return
    path = options.state_dir / 'vm.json'
    if not path.is_file():
        raise RuntimeError('No existing PPCI VM; run the initial deployment before run/package/status')
    config = json.loads(path.read_text())
    if config.get('version') != 1 or config.get('state_dir') != str(options.state_dir):
        raise RuntimeError('Existing VM settings have an unsupported format or state directory')
    # Proxy actions use the deployed VM's address and identity, not CLI defaults.
    for name in ('memory_mib', 'cpus', 'ssh_port', 'bind_address', 'lan_cidr'):
        setattr(options, name, config[name])


def firewall(config):
    """Restrict only this VM's forwarded web sockets; retain all other host rules."""
    host = config['bind_address']
    if ipaddress.IPv4Address(host).is_loopback:
        return
    tool = shutil.which('iptables')
    if not tool:
        raise RuntimeError('Public VM forwarding requires iptables for the requested LAN access restriction')
    chain = 'PPCI_VM_' + hashlib.sha256(config['state_dir'].encode()).hexdigest()[:10]
    comment = 'ppci-amd64-vm'
    rules = [('-s', config['lan_cidr'], '-m', 'comment', '--comment', comment, '-j', 'ACCEPT'),
             ('-m', 'comment', '--comment', comment, '-j', 'DROP')]
    exists = subprocess.run([tool, '-w', '-S', chain], capture_output=True, text=True)
    if exists.returncode:
        run(tool, '-w', '-N', chain)
        for rule in rules:
            run(tool, '-w', '-A', chain, *rule)
    else:
        valid = sum(line.startswith('-A ') for line in exists.stdout.splitlines()) == len(rules)
        for rule in rules:
            valid = valid and subprocess.run([tool, '-w', '-C', chain, *rule],
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        if not valid:
            raise RuntimeError('Existing project firewall chain differs; retained without flushing: ' + chain)
    jump = ('-d', host + '/32', '-p', 'tcp', '-m', 'multiport', '--dports', ','.join(map(str, WEB_PORTS)),
            '-m', 'comment', '--comment', comment, '-j', chain)
    if subprocess.run([tool, '-w', '-C', 'INPUT', *jump], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        run(tool, '-w', '-I', 'INPUT', '1', *jump)


def qemu_command(config):
    state = Path(config['state_dir'])
    # Doubling commas is QEMU's escaping rule for option values.
    disk = str(state / 'guest.qcow2').replace(',', ',,')
    seed = str(state / 'seed.img').replace(',', ',,')
    forwards = [f'hostfwd=tcp:127.0.0.1:{config["ssh_port"]}-:22']
    forwards += [f'hostfwd=tcp:{config["bind_address"]}:{port}-:{port}' for port in WEB_PORTS]
    return [qemu_binary() or '/usr/bin/qemu-system-x86_64',
            '-name', 'ppci-amd64', '-machine', 'q35,accel=tcg', '-cpu', 'max',
            '-smp', str(config['cpus']), '-m', str(config['memory_mib']),
            '-drive', f'file={disk},format=qcow2,if=virtio',
            '-drive', f'file={seed},format=raw,if=virtio,readonly=on',
            '-netdev', 'user,id=net0,' + ','.join(forwards),
            '-device', 'virtio-net-pci,netdev=net0', '-display', 'none',
            '-serial', 'file:' + str(state / 'console.log'), '-monitor', 'none']


def unit_text(config):
    quoted = ['"' + arg.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
              for arg in qemu_command(config)]
    helper = [shutil.which('python3') or '/usr/bin/python3', str(Path(config['state_dir']) / 'helper.py'),
              '--state-dir', config['state_dir'], 'firewall']
    before = ' '.join('"' + a.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"' for a in helper)
    return MARKER + '''[Unit]
Description=PPCI amd64 compatibility VM (QEMU TCG)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
UMask=0077
ExecStartPre=''' + before + '''
ExecStart=''' + ' '.join(quoted) + '''
Restart=on-failure
RestartSec=15
TimeoutStopSec=120
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
'''


def create(options):
    state = options.state_dir
    if state.is_symlink():
        raise RuntimeError('VM state directory must not be a symlink')
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    if state.stat().st_uid != os.geteuid():
        raise RuntimeError('VM state must be owned by the current administrator')
    state.chmod(0o700)
    config_path = state / 'vm.json'
    config = settings(options)
    if config_path.exists():
        if json.loads(config_path.read_text()) != config:
            raise RuntimeError('Existing VM settings differ; reuse its original --state-dir, resource and bind options')
        for name in ('guest.qcow2', 'seed.img', 'id_ed25519', 'id_ed25519.pub'):
            if not (state / name).is_file() or (state / name).is_symlink():
                raise RuntimeError('Incomplete existing VM retained; missing regular file: ' + name)
    else:
        if '--offline' in options.guest_args and not options.base_image and not (state / IMAGE_NAME).is_file():
            raise RuntimeError('Offline ARM deployment needs an existing prepared VM or a cached --base-image and checksum')
        if any((state / name).exists() for name in ('guest.qcow2', 'seed.img', 'id_ed25519', 'id_ed25519.pub')):
            raise RuntimeError('Partial VM initialization retained; inspect state directory before retrying')
        for address, port in [('127.0.0.1', options.ssh_port)] + [(options.bind_address, p) for p in WEB_PORTS]:
            with socket.socket() as probe:
                probe.bind((address, port))
        base = image(state, options.base_image, options.base_image_sha256)
        run('ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', state / 'id_ed25519')
        (state / 'id_ed25519').chmod(0o600)
        (state / 'user-data').write_text(cloud_config((state / 'id_ed25519.pub').read_text().strip()))
        (state / 'meta-data').write_text(json.dumps({'instance-id': 'ppci-' + str(uuid.uuid4()), 'local-hostname': 'ppci-amd64'}))
        run('cloud-localds', state / 'seed.img', state / 'user-data', state / 'meta-data')
        run('qemu-img', 'create', '-f', 'qcow2', '-F', 'qcow2', '-b', base, state / 'guest.qcow2', f'{options.disk_gib}G')
        config_path.write_text(json.dumps(config, indent=2) + '\n')
    text = unit_text(config)
    if UNIT.exists() and UNIT.read_text() != text:
        raise RuntimeError('Existing VM service differs; retained without overwrite: ' + str(UNIT))
    if not UNIT.exists():
        UNIT.write_text(text)
        run('systemctl', 'daemon-reload')
    shutil.copyfile(Path(__file__), state / 'helper.py')
    (state / 'helper.py').chmod(0o700)
    firewall(config)
    run('systemctl', 'enable', '--now', SERVICE)


def ssh_args(options, copy=False):
    return ['scp' if copy else 'ssh', '-P' if copy else '-p', str(options.ssh_port),
            '-i', str(options.state_dir / 'id_ed25519'), '-o', 'BatchMode=yes',
            '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=5',
            '-o', 'StrictHostKeyChecking=accept-new',
            '-o', 'UserKnownHostsFile=' + str(options.state_dir / 'known_hosts')]


def remote(options, args, **kwargs):
    return run(*ssh_args(options), 'ppci@127.0.0.1', shlex.join([str(a) for a in args]), **kwargs)


def wait_ready(options):
    deadline = time.monotonic() + options.wait_seconds
    while time.monotonic() < deadline:
        if subprocess.run(['systemctl', 'is-active', '--quiet', SERVICE]).returncode:
            raise RuntimeError('VM service stopped; inspect journalctl -u ' + SERVICE)
        try:
            remote(options, ['test', '-f', '/var/lib/cloud/instance/boot-finished'],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            time.sleep(5)
    raise TimeoutError('VM SSH/cloud-init readiness timed out; disk retained. Inspect ' + str(options.state_dir / 'console.log'))


def validate_source(path):
    with tarfile.open(path, 'r:*') as archive:
        files = archive.getmembers()
        names = set()
        links = {}
        for member in files:
            parts = Path(member.name).parts
            if not parts or parts[0] != 'ppci-source' or member.name.startswith('/') or '..' in parts:
                raise RuntimeError('Source archive must contain only ppci-source/ paths')
            if member.name in names:
                raise RuntimeError('Source archive contains duplicate paths')
            names.add(member.name)
            if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                raise RuntimeError('Source archive contains unsupported devices')
            if member.issym() or member.islnk():
                if member.linkname.startswith('/'):
                    raise RuntimeError('Source archive contains an absolute link')
                target = posixpath.join(posixpath.dirname(member.name), member.linkname) if member.issym() else member.linkname
                links[member.name] = posixpath.normpath(target)
        def resolve(name, depth=0):
            if name != 'ppci-source' and not name.startswith('ppci-source/'):
                raise RuntimeError('Source archive link escapes ppci-source/')
            if depth > 40:
                raise RuntimeError('Source archive has a cyclic link')
            parts = name.split('/')
            for i in range(1, len(parts) + 1):
                prefix = '/'.join(parts[:i])
                if prefix in links:
                    return resolve(posixpath.normpath(posixpath.join(links[prefix], *parts[i:])), depth + 1)
            return name
        for member in files:
            resolve(member.name)
            if any('/'.join(member.name.split('/')[:i]) in links for i in range(1, len(member.name.split('/')))):
                raise RuntimeError('Source archive writes through a link directory')
        if not any(m.name == 'ppci-source/deploy.sh' and m.isfile() for m in files):
            raise RuntimeError('Source archive does not contain ppci-source/deploy.sh')


def guest_command(options):
    args = list(options.guest_args)
    if args and args[0] == '--':
        args.pop(0)
    action = args.pop(0) if options.command == 'deploy' and args and not args[0].startswith('-') else options.command
    if action == 'deploy':
        action = 'all'
    if action not in ('all', 'check', 'bootstrap', 'sync', 'build', 'up', 'status', 'run', 'package', 'clean'):
        raise RuntimeError('Unknown guest deployment action: ' + action)
    if any(a in ('--host', '--lan-cidr', '--native') or a.startswith(('--host=', '--lan-cidr=')) for a in args):
        raise RuntimeError('Guest host/network/native flags are managed by the VM helper')
    return ['sudo', 'env', 'PPCI_PUBLIC_HOST=' + options.bind_address,
            'bash', '/opt/ppci-source/deploy.sh', action, '--native',
            '--host', '10.0.2.15', '--lan-cidr', '10.0.2.0/24', *args]


def proxy(options):
    args = guest_command(options)
    token = str(uuid.uuid4())
    if options.source_package:
        validate_source(options.source_package)
        target = '/home/ppci/source-' + token + '.tar.gz'
        run(*ssh_args(options, copy=True), options.source_package, 'ppci@127.0.0.1:' + target)
        # Existing runtime state lives outside ppci-source; extraction changes only source files.
        remote(options, ['sudo', 'mkdir', '-p', '/opt/ppci-source'])
        remote(options, ['sudo', 'tar', '-xzf', target, '-C', '/opt', '--no-same-owner', '--no-same-permissions'])
        remote(options, ['rm', target])
    if '--offline' in args:
        index = args.index('--offline') + 1
        if index >= len(args) or not Path(args[index]).is_dir():
            raise RuntimeError('--offline must name an existing host bundle directory')
        target = '/home/ppci/offline-' + token
        remote(options, ['mkdir', '-m', '700', target])
        run(*ssh_args(options, copy=True), '-r', str(Path(args[index]).resolve()) + '/.', 'ppci@127.0.0.1:' + target + '/')
        args[index] = target
    export = None
    if options.command == 'package':
        if '--output' not in args:
            args += ['--output', str(Path.cwd() / 'dist' / time.strftime('%Y%m%d-%H%M%S'))]
        index = args.index('--output') + 1
        if index >= len(args):
            raise RuntimeError('VM package requires --output HOST_DIRECTORY')
        export = Path(args[index]).expanduser().absolute()
        if export.is_symlink():
            raise RuntimeError('Host export directory must not be a symlink')
        export = export.resolve()
        export.mkdir(parents=True, exist_ok=False)
        target = '/home/ppci/export-' + token
        args[index] = target
    remote(options, args)
    if export is not None:
        remote(options, ['sudo', 'chown', '-R', 'ppci:ppci', target])
        run(*ssh_args(options, copy=True), '-r', 'ppci@127.0.0.1:' + target + '/.', str(export) + '/')
        print('VM release copied to ' + str(export))


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--bootstrap', action='store_true')
    result.add_argument('--state-dir', type=Path, default=Path('/var/lib/ppci/amd64-vm'))
    result.add_argument('--source-package', type=Path)
    result.add_argument('--base-image', type=Path, help='Cached official Ubuntu amd64 cloud image, for an offline first boot')
    result.add_argument('--base-image-sha256', help='Official SHA256SUMS value for --base-image')
    result.add_argument('--memory-mib', type=int, default=16384)
    result.add_argument('--cpus', type=int, default=4)
    result.add_argument('--disk-gib', type=int, default=240)
    result.add_argument('--ssh-port', type=int, default=22220)
    result.add_argument('--bind-address', default='127.0.0.1')
    result.add_argument('--lan-cidr', help='Allowed IPv4 source CIDR for public host sockets (default bind address /32)')
    result.add_argument('--wait-seconds', type=int, default=1800)
    result.add_argument('command', choices=('check', 'start', 'status', 'deploy', 'run', 'package', 'firewall'))
    result.add_argument('guest_args', nargs=argparse.REMAINDER)
    return result


def main(argv=None):
    options = parser().parse_args(argv)
    options.state_dir = options.state_dir.expanduser().absolute()
    reuse_settings(options)
    ipaddress.IPv4Address(options.bind_address)
    lan_cidr(options)
    if any(c in str(options.state_dir) for c in '\r\n\x00'):
        raise RuntimeError('Invalid state directory')
    if options.memory_mib < 8192 or options.cpus < 2 or options.disk_gib < 80:
        raise RuntimeError('VM needs at least 8192 MiB RAM, 2 CPUs and an 80 GiB virtual disk')
    if not 1024 <= options.ssh_port <= 65535 or options.ssh_port in WEB_PORTS:
        raise RuntimeError('Invalid or conflicting SSH forwarding port')
    if not 30 <= options.wait_seconds <= 7200:
        raise RuntimeError('Readiness timeout must be between 30 and 7200 seconds')
    if options.command == 'check':
        check(options)
        return
    if options.source_package:
        validate_source(options.source_package)
    if platform.system() != 'Linux' or os.geteuid() != 0:
        raise RuntimeError('VM lifecycle/proxy commands require root on a Linux host')
    if options.command == 'firewall':
        config = json.loads((options.state_dir / 'vm.json').read_text())
        if config['state_dir'] != str(options.state_dir):
            raise RuntimeError('VM firewall state directory mismatch')
        firewall(config)
        return
    if options.command == 'status':
        if not UNIT.is_file() or not UNIT.read_text().startswith(MARKER):
            raise RuntimeError('No PPCI-managed amd64 VM service is installed')
        run('systemctl', 'status', '--no-pager', SERVICE)
        remote(options, guest_command(options))
        return
    if options.bootstrap and missing_tools(options):
        if '--offline' in options.guest_args:
            raise RuntimeError('Offline ARM deployment requires host QEMU/cloud-localds tools to be installed already')
        bootstrap()
    check(options)
    create(options)
    wait_ready(options)
    if options.command != 'start':
        proxy(options)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit('amd64 VM: ' + str(error))
