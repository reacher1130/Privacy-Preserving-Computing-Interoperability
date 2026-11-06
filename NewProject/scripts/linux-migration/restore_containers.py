#!/usr/bin/env python3
"""Restore this migration's reviewed container manifest without touching other services.

Run on Linux. A restored container is created stopped; start is a separate step.
Exports preserve writable layers; inspect metadata reconstructs runtime settings.
"""
import argparse
import copy
import http.client
import json
from pathlib import Path
import socket
import subprocess
import urllib.parse

class Docker(http.client.HTTPConnection):
    def __init__(self):
        super().__init__('localhost', timeout=120)
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect('/var/run/docker.sock')

def api(method, path, body=None, missing=False):
    conn = Docker()
    conn.request(method, '/v1.45' + path, None if body is None else json.dumps(body), {'Content-Type': 'application/json'})
    res = conn.getresponse()
    raw = res.read()
    conn.close()
    if missing and res.status == 404:
        return None
    if res.status >= 300:
        raise RuntimeError('%s %s: %s' % (method, path, raw.decode()))
    return json.loads(raw) if raw else None

ap = argparse.ArgumentParser()
ap.add_argument('--backup', default='/var/backups/ppci/migration-20260908')
ap.add_argument('--root', default='/opt/ppci')
ap.add_argument('--address', default='192.168.45.101')
ap.add_argument('--only', nargs='*')
args = ap.parse_args()
backup = Path(args.backup)
containers = json.loads((backup / 'containers.json').read_text())
networks = json.loads((backup / 'networks.json').read_text())
label = {'io.ppci.migration': '20260908'}
netmap = {n['Name']: 'ppci-' + n['Name'].replace('_', '-') for n in networks}
for n in networks:
    name = netmap[n['Name']]
    existing = api('GET', '/networks/' + name, missing=True)
    ipam = [v for v in n['IPAM']['Config'] if ':' not in v['Subnet']]
    if n['Name'] == 'bridge':
        ipam = [{'Subnet': '10.240.0.0/24', 'Gateway': '10.240.0.1'}]
    if existing:
        if existing.get('Labels', {}).get('io.ppci.migration') != '20260908':
            raise RuntimeError('Unowned network name conflict: ' + name)
    else:
        api('POST', '/networks/create', {'Name': name, 'Driver': 'bridge', 'Labels': label, 'IPAM': {'Driver': 'default', 'Config': ipam}})

oldroot = '/Users/gaofeng/develop/project/Privacy-Preserving-Computing-Interoperability'
def translate(s):
    return s.replace(oldroot, args.root)

for c in containers:
    name = c['Name'].lstrip('/')
    if args.only and name not in args.only:
        continue
    existing = api('GET', '/containers/' + name + '/json', missing=True)
    if existing:
        if existing['Config'].get('Labels', {}).get('io.ppci.migration') != '20260908':
            raise RuntimeError('Unowned container name conflict: ' + name)
        print('Already created ' + name, flush=True)
        continue
    orig = c['Config']['Image']
    kuscia = orig.startswith('secretflow/kuscia:')
    archive = backup / (name + '-rootfs.tar.gz')
    if kuscia:
        image = 'ppci/kuscia:amd64-20260908'
        if not archive.with_name(archive.name + '.sha256').is_file():
            print('Awaiting backup ' + name, flush=True)
            continue
    elif orig.startswith('arm64v8/nginx:'):
        image = 'nginx:1.27'
    elif orig.startswith('alpine/socat'):
        image = 'alpine/socat:latest'
    else:
        image = 'ppci-migration/' + name.replace('.', '-') + ':20260908'
        if not archive.with_name(archive.name + '.sha256').is_file():
            print('Awaiting backup ' + name, flush=True)
            continue
        if not api('GET', '/images/' + image + '/json', missing=True):
            subprocess.run(['sha256sum', '-c', str(archive) + '.sha256'], check=True)
            subprocess.run(['docker', 'import', '--platform', 'linux/amd64', str(archive), image], check=True)
    image_info = api('GET', '/images/' + image + '/json', missing=True)
    if not image_info:
        print('Awaiting image ' + image, flush=True)
        continue
    if image_info['Architecture'] != 'amd64':
        raise RuntimeError('Wrong architecture ' + image)
    cfg = {k: copy.deepcopy(c['Config'][k]) for k in ('Hostname', 'Domainname', 'User', 'Env', 'Cmd', 'Entrypoint', 'WorkingDir', 'ExposedPorts', 'StopSignal') if c['Config'].get(k) is not None}
    cfg.update(Image=image, Labels=label, Tty=c['Config']['Tty'], OpenStdin=c['Config']['OpenStdin'])
    cfg['Env'] = [translate(v) for v in cfg.get('Env', [])]
    cfg['Cmd'] = [translate(v) for v in cfg.get('Cmd') or []] or None
    if name in ('fate2-flow-guest-e2e', 'fate2-flow-host-e2e'):
        cfg['Cmd'] = [v.replace('host: host.docker.internal\n  port: 19382', 'host: fate2-flow-host-e2e\n  port: 9380').replace('host: host.docker.internal\n  port: 19381', 'host: fate2-flow-guest-e2e\n  port: 9380') for v in cfg['Cmd']]
    old = c['HostConfig']
    host = {k: copy.deepcopy(old[k]) for k in ('Privileged', 'CapAdd', 'CapDrop', 'SecurityOpt', 'ShmSize', 'Memory', 'MemorySwap', 'NanoCpus', 'Ulimits') if old.get(k) is not None}
    host.update(RestartPolicy={'Name': 'unless-stopped'}, LogConfig={'Type': 'json-file', 'Config': {'max-size': '20m', 'max-file': '3'}}, ExtraHosts=['host.docker.internal:host-gateway'])
    host['Binds'] = []
    for m in c['Mounts']:
        if m['Type'] == 'bind':
            src = translate(m['Source'])
            if not Path(src).exists():
                raise RuntimeError('Missing bind source: ' + src)
            host['Binds'].append(src + ':' + m['Destination'] + (':ro' if not m['RW'] else ''))
        elif m['Type'] == 'volume':
            vol = 'ppci-' + m['Name']
            api('POST', '/volumes/create', {'Name': vol, 'Labels': label})
            host['Binds'].append(vol + ':' + m['Destination'])
        else:
            raise RuntimeError('Unsupported mount ' + m['Type'])
    host['PortBindings'] = copy.deepcopy(old.get('PortBindings') or {})
    if name in ('fate2-flow-e2e', 'fate2-flow-guest-e2e', 'fate2-flow-host-e2e'):
        # Nested Kuscia workers reach these through host.docker.internal.
        # Keep the host loopback binding and add only Docker's internal gateway.
        for ports in host['PortBindings'].values():
            ports.extend([dict(p, HostIp='172.17.0.1') for p in list(ports) if p['HostIp'] == '127.0.0.1'])
    if kuscia:
        node = name.rsplit('-', 1)[1]
        state = Path('/srv/ppci/kuscia') / node
        marker = state / '.state-restored'
        root = state / 'root'
        if not marker.exists():
            if root.exists():
                raise RuntimeError('Incomplete state extraction requires review: ' + str(root))
            root.mkdir(parents=True)
            subprocess.run(['sha256sum', '-c', str(archive) + '.sha256'], check=True)
            subprocess.run(['tar', '-xzf', str(archive), '-C', str(root),
                            'home/kuscia/var/k3s', 'home/kuscia/var/certs',
                            'home/kuscia/var/storage', 'home/kuscia/etc/kubeconfig',
                            'home/kuscia/etc/kuscia.kubeconfig', 'etc/rancher'], check=True)
            marker.touch()
        var = root / 'home/kuscia/var'
        (var / 'images').mkdir(exist_ok=True)
        host['Binds'].insert(0, str(var) + ':/home/kuscia/var')
        host['Binds'].append(str(root / 'etc/rancher') + ':/etc/rancher')
        for fn in ('kubeconfig', 'kuscia.kubeconfig'):
            host['Binds'].append(str(root / 'home/kuscia/etc' / fn) + ':/home/kuscia/etc/' + fn)
    if 'nginx' in orig or name == 'fateboard-native-e2e':
        for ports in host['PortBindings'].values():
            for p in ports:
                p['HostIp'] = args.address
    ends = {}
    for network, ep in c['NetworkSettings']['Networks'].items():
        settings = {'Aliases': list(set((ep.get('Aliases') or []) + [name]))}
        if ep.get('IPAMConfig'):
            settings['IPAMConfig'] = {k: v for k, v in ep['IPAMConfig'].items() if k == 'IPv4Address'}
        ends[netmap[network]] = settings
    if name == 'kusciaapi-kimi-proxy':
        ends = {netmap['kuscia-exchange']: {'Aliases': [name]}}
    # Keep automatic proxy allocation away from the three fixed Kuscia node IPs.
    proxy_ips = {n: f'192.168.117.{i}' for i, n in enumerate([
        'bfia-alice-proxy', 'bfia-bob-proxy', 'kusciaapi-alice-proxy',
        'kusciaapi-bob-proxy', 'kusciaapi-kimi-proxy'], 10)}
    if name in proxy_ips:
        ends[netmap['kuscia-exchange']]['IPAMConfig'] = {'IPv4Address': proxy_ips[name]}
    host['NetworkMode'] = netmap[old['NetworkMode']]
    if name == 'kusciaapi-kimi-proxy':
        host['NetworkMode'] = netmap['kuscia-exchange']
    cfg.update(HostConfig=host, NetworkingConfig={'EndpointsConfig': ends})
    api('POST', '/containers/create?name=' + urllib.parse.quote(name), cfg)
    print('Created stopped ' + name, flush=True)
