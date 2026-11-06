#!/usr/bin/env python3
"""Read-only health report for the fresh portable Linux topology."""
import json
import os
import subprocess
import sys
import urllib.request


def main():
    if sys.argv[1:] != ['status']:
        raise SystemExit('Usage: ppci-platform status')
    report = {'containers': {}, 'services': {}, 'nativeFate': {}, 'paddleDTX': {}, 'engines': {}, 'bfiaPartners': {}, 'healthy': True}
    gateway = subprocess.run(['systemctl', 'is-active', '--quiet', 'nginx']).returncode == 0
    report['gateway'] = {'active': gateway}
    report['healthy'] &= gateway
    names = ['gaofeng-kuscia-autonomy-' + n for n in ('alice', 'bob', 'kimi')]
    names += ['fate2-flow-guest-e2e', 'fate2-flow-host-e2e']
    names += [f'{kind}{i}.node.com' for kind in ('xchain', 'dataowner', 'storage', 'executor') for i in (1, 2, 3)]
    names += ['paddledtx-visual']
    if os.environ.get('PPCI_FATE_EXTERNAL_BOARD') == '1':
        names += ['fateboard-native-e2e', 'fateboard-host-native-e2e',
                  'ppci-dtx-mysql', 'ppci-dtx-manager', 'ppci-dtx-native-ui']
    for name in names:
        p = subprocess.run(['docker', 'inspect', name], capture_output=True, text=True)
        state = json.loads(p.stdout)[0]['State'] if p.returncode == 0 else {'Running': False, 'Error': 'missing'}
        report['containers'][name] = {'running': state['Running'], 'error': state.get('Error', '')}
        report['healthy'] &= state['Running']
    for node, port in [('alice', 18080), ('bob', 28090), ('kimi', 38090)]:
        try:
            data = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/actuator/health', timeout=5))
            report['services'][node] = data
            report['healthy'] &= data.get('status') == 'UP'
        except Exception as e:
            report['services'][node] = {'error': str(e)}
            report['healthy'] = False
    for role, port, party in [('guest', 19381, 'JG0100001100000010'), ('host', 19382, 'JG0100001100000000')]:
        try:
            data = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/v2/site/info/query', timeout=5))
            report['nativeFate'][role] = data
            report['healthy'] &= data.get('data', {}).get('party_id') == party
        except Exception as e:
            report['nativeFate'][role] = {'error': str(e)}
            report['healthy'] = False
    for i in (1, 2, 3):
        try:
            request = urllib.request.Request(f'http://127.0.0.1:{8510+i}/v1/task/list',
                                             data=b'{}', headers={'Content-Type': 'application/json'})
            data = json.load(urllib.request.urlopen(request, timeout=10))
            ok = str(data.get('code')) == '0'
            report['paddleDTX'][f'executor{i}'] = {'ready': ok, 'code': data.get('code')}
            report['healthy'] &= ok
        except Exception as e:
            report['paddleDTX'][f'executor{i}'] = {'error': str(e)}
            report['healthy'] = False
    registry = 'secretflow-registry.cn-hangzhou.cr.aliyuncs.com/secretflow/'
    bfia = [registry + name + ':latest' for name in ('ecdh', 'ecdh-psi', 'ss-compare', 'ss-lr', 'ss-pearson', 'ss-vif', 'ss-xgb')]
    sf = registry + 'secretflow-lite-anolis8:1.11.0b1'
    expected = {'alice': [sf, 'docker.io/secretflow/fate2-adapter:0.2.0-native', *bfia],
                'bob': bfia, 'kimi': [sf]}
    for node, required in expected.items():
        try:
            data = json.loads(subprocess.check_output(['docker', 'exec', 'gaofeng-kuscia-autonomy-' + node,
                                                      'crictl', 'images', '-o', 'json'], timeout=15))
            present = {tag for item in data['images'] for tag in item.get('repoTags', [])}
            missing = sorted(set(required) - present)
            report['engines'][node] = {'ready': not missing, 'missingImages': missing}
            report['healthy'] &= not missing
        except Exception as e:
            report['engines'][node] = {'error': str(e)}
            report['healthy'] = False
    for node, port, peer in [('alice', 18080, 'bob'), ('bob', 28090, 'alice')]:
        try:
            data = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/api/v1bfia/node/list/approved', timeout=10))
            ready = data.get('status', {}).get('code') == 0 and any(n.get('nodeId') == peer for n in data.get('data', []))
            report['bfiaPartners'][node] = {'peer': peer, 'ready': ready}
            report['healthy'] &= ready
        except Exception as e:
            report['bfiaPartners'][node] = {'error': str(e)}
            report['healthy'] = False
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report['healthy'] else 1)


if __name__ == '__main__':
    main()
