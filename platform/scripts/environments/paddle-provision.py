#!/usr/bin/env python3
"""Initialize the public PaddleDTX demo on a fresh portable Linux runtime."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
from string import Template
import subprocess
import time

import yaml

from provision import SOURCE, ROOT, BUILD, ensure_container, run

WORK = ROOT / 'PaddleDTX/testdatatmp'
CHAIN = 'xchain1.node.com'
ACCOUNT = 'XC1111111111111112@xuper'


def prepare():
    WORK.mkdir(parents=True, exist_ok=True)
    run('rsync', '-a', '--ignore-existing', str(SOURCE / 'PaddleDTX/testdata') + '/', str(WORK) + '/')
    samples = ROOT / 'PaddleDTX/dai/mpc/testdata/vl'
    samples.mkdir(parents=True, exist_ok=True)
    run('rsync', '-a', '--ignore-existing', str(SOURCE / 'PaddleDTX/dai/mpc/testdata/vl') + '/', str(samples) + '/')
    values = dict(BLOCKCHAIN_TYPE='xchain', CONTRACT_NAME='paddlempc', CONTRACT_ACCOUNT='1111111111111112',
                  MNEMONIC=(WORK / 'blockchain/xchain/user/mnemonic').read_text().strip(),
                  STORAGE_MODE_TYPE='local', CHANNEL_NAME='mychannel',
                  **{f'EXECUTOR{i}_HOST': f'executor{i}.node.com' for i in range(1, 4)})
    for sample in WORK.rglob('config.toml.sample'):
        dest = sample.with_suffix('')
        if not dest.exists():
            dest.write_text(Template(sample.read_text()).substitute(values))
            dest.chmod(0o600)
    for i in range(1, 4):
        conf = WORK / f'executor/node{i}/conf'
        target = conf / 'requester-config.toml'
        if not target.exists():
            target.write_text((conf / 'config.toml').read_text())
            target.chmod(0o600)
        # The bundled native DAI fork reads these names; upstream samples use contractName.
        for config in (conf / 'config.toml', target):
            text = config.read_text()
            original = text
            section = re.search(r'(?ms)^[ \t]*\[executor\.blockchain\.xchain\][ \t]*\n(.*?)(?=^[ \t]*\[|\Z)', text)
            if section is None:
                raise RuntimeError('Missing executor xchain configuration: ' + str(config))
            body = section.group(1)
            additions = []
            if not re.search(r'(?m)^[ \t]*dtxContractName[ \t]*=', body):
                legacy = re.search(r'(?m)^[ \t]*contractName[ \t]*=[ \t]*(.+)$', body)
                if legacy is None:
                    raise RuntimeError('Missing executor contractName: ' + str(config))
                additions.append('        dtxContractName = ' + legacy.group(1))
            if not re.search(r'(?m)^[ \t]*managerContractName[ \t]*=', body):
                additions.append('        managerContractName = "data"')
            if additions:
                text = text[:section.end()] + '\n' + '\n'.join(additions) + '\n' + text[section.end():]
            section = re.search(r'(?ms)^[ \t]*\[executor\.storage\][ \t]*\n(.*?)(?=^[ \t]*\[|\Z)', text)
            if section is None:
                raise RuntimeError('Missing executor storage configuration: ' + str(config))
            body = section.group(1)
            legacy_type = re.search(r'(?m)^[ \t]*type[ \t]*=[ \t]*(.+)$', body)
            predict_type = re.search(r'(?m)^[ \t]*predictStorageType[ \t]*=[ \t]*(.+)$', body)
            predict_type = predict_type or legacy_type
            local = re.search(r'(?ms)^[ \t]*\[executor\.storage\.Local\][ \t]*\n(.*?)(?=^[ \t]*\[|\Z)', text)
            predict_path = re.search(r'(?m)^[ \t]*localPredictStoragePath[ \t]*=[ \t]*(.+)$', local.group(1)) if local else None
            defaults = {
                'modelStorageType': '"Local"',
                'predictStorageType': predict_type.group(1) if predict_type else '"Local"',
                'psiStorageType': predict_type.group(1) if predict_type else '"Local"',
                'localPredictStoragePath': predict_path.group(1) if predict_path else '"./predictions"',
                'localPsiStoragePath': '"./predictions/psi"',
                'liveEvaluationStoragePath': '"./evalus/live"',
            }
            additions = [key + ' = ' + value for key, value in defaults.items()
                         if not re.search(r'(?m)^[ \t]*' + key + r'[ \t]*=', body)]
            if additions:
                text = text[:section.end()] + '\n' + '\n'.join(additions) + '\n' + text[section.end():]
                body += '\n' + '\n'.join(additions)
            local_only = all(re.search(r'(?m)^[ \t]*' + key + r'''[ \t]*=[ \t]*["']Local["'][ \t]*(?:#.*)?$''', body)
                             for key in ('modelStorageType', 'predictStorageType', 'psiStorageType'))
            executor = re.search(r'(?ms)^[ \t]*\[executor\][ \t]*\n(.*?)(?=^[ \t]*\[|\Z)', text)
            xdb = re.search(r'(?ms)^[ \t]*\[executor\.storage\.XuperDB\][ \t]*\n(.*?)(?=^[ \t]*\[|\Z)', text)
            key_pattern = r'''(?m)^[ \t]*keyPath[ \t]*=[ \t]*(["'])([^"']+)\1'''
            executor_key = re.search(key_pattern, executor.group(1)) if executor else None
            xdb_key = re.search(key_pattern, xdb.group(1)) if xdb else None
            # Native DAI initializes an unused XDB client even for Local; both clients parse the same ECDSA key format.
            if (local_only and executor_key and xdb_key and xdb_key.group(2) == './ukeys'
                    and not re.search(r'(?m)^[ \t]*privateKey[ \t]*=', xdb.group(1))
                    and not (conf.parent / xdb_key.group(2) / 'private.key').exists()
                    and not Path(executor_key.group(2)).is_absolute()
                    and (conf.parent / executor_key.group(2) / 'private.key').is_file()):
                xdb_body = xdb.group(1)
                xdb_body = xdb_body[:xdb_key.start(2)] + executor_key.group(2) + xdb_body[xdb_key.end(2):]
                text = text[:xdb.start(1)] + xdb_body + text[xdb.end(1):]
            if text != original:
                config.write_text(text)
    network = subprocess.run(['docker', 'network', 'inspect', 'blockchain_network'], capture_output=True, text=True)
    if network.returncode:
        run('docker', 'network', 'create', '--subnet', '172.31.1.0/24', 'blockchain_network')
    elif json.loads(network.stdout)[0]['IPAM']['Config'][0]['Subnet'] != '172.31.1.0/24':
        raise RuntimeError('Existing blockchain_network has an unexpected subnet')


def start_group(group):
    compose = WORK / group / 'docker-compose.yml'
    for service in yaml.safe_load(compose.read_text())['services'].values():
        name = service['container_name']
        args = ['--network', 'blockchain_network', '--hostname', name,
                '--ulimit', 'nofile=65536:65536', '-e', 'GOMAXPROCS=2', '-e', 'GOMEMLIMIT=400MiB']
        for port in service.get('ports', []):
            args += ['-p', '127.0.0.1:' + str(port)]
        for mount in service.get('volumes', []):
            src, dest = mount.split(':', 1)
            # Native Go MPC does not require the host Docker socket.
            if src == '/var/run/docker.sock':
                continue
            src = (compose.parent / src).resolve()
            src.mkdir(parents=True, exist_ok=True)
            args += ['-v', str(src) + ':' + dest]
        if group == 'blockchain/xchain':
            args += ['-v', 'ppci-paddle-' + name + '-ledger:/home/work/xchain/data/blockchain',
                     '-v', 'ppci-paddle-' + name + '-contracts:/home/work/xchain/data/native']
        if group == 'xdb':
            args += ['-v', 'ppci-paddle-' + name + '-data:/home/data']
        if group == 'executor':
            for directory in ('models', 'evalus', 'predictions'):
                args += ['-v', f'ppci-paddle-{name}-{directory}:/home/{directory}']
            binary = BUILD / 'paddle/requester-cli-current'
            if not binary.exists():
                raise FileNotFoundError(binary)
            args += ['-v', str(binary) + ':/home/requester-cli-current:ro']
        image = service['image']
        if group == 'executor':
            image = os.environ.get('PPCI_PADDLE_DAI_IMAGE', image)
        elif group == 'xdb':
            image = os.environ.get('PPCI_PADDLE_XDB_IMAGE', image)
        ensure_container(name, args + [image])


def cli(*args, check=True):
    p = subprocess.run(['docker', 'exec', CHAIN, './xchain-cli', *args,
                        '--host', CHAIN + ':37101'], capture_output=True, text=True)
    print(p.stdout, p.stderr, flush=True)
    if check and (p.returncode or re.search(r'(?im)^(Error|Fail)', p.stdout + p.stderr)):
        raise RuntimeError('Xchain command failed: ' + ' '.join(args[:2]))
    return p.stdout + p.stderr


def deploy_contract():
    marker = WORK / '.contract-deployed.json'
    if marker.exists():
        print('Existing contract deployment retained', flush=True)
        return
    for _ in range(30):
        out = cli('status', check=False)
        if 'trunkHeight' in out:
            break
        time.sleep(2)
    else:
        raise RuntimeError('Xchain did not become ready')
    state_file = WORK / '.contract-init.json'
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    def step(name, action):
        if not state.get(name):
            action()
            state[name] = True
            state_file.write_text(json.dumps(state))
            time.sleep(3)
    def fee_call(args):
        out = cli(*args, check=False)
        m = re.search(r'The gas you[^:\n]*:\s*(\d+)', out)
        if not m:
            raise RuntimeError('Could not determine demo transaction gas')
        return cli(*args, '--fee', m.group(1))
    address = (WORK / 'blockchain/xchain/user/address').read_text().strip()
    step('fund-user', lambda: cli('transfer', '--to', address, '--amount', '110009887797', '--keys', './data/keys'))
    step('create-account', lambda: fee_call(['account', 'new', '--account', '1111111111111112', '--keys', './user']))
    step('fund-account', lambda: cli('transfer', '--to', ACCOUNT, '--amount', '110009887797', '--keys', './data/keys'))
    run('docker', 'cp', BUILD / 'paddle/paddlempc', CHAIN + ':/home/work/xchain/paddlempc')
    fee_call(['native', 'deploy', '--account', ACCOUNT, '--runtime', 'go', '-a', json.dumps({'creator': ACCOUNT}),
              '--cname', 'paddlempc', './paddlempc', '--keys', './user'])
    marker.write_text(json.dumps({'account': ACCOUNT, 'contract': 'paddlempc', 'deployed_at': time.time()}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=('prepare', 'chain', 'contract', 'services', 'all'))
    args = p.parse_args()
    if args.stage in ('prepare', 'all'): prepare()
    if args.stage in ('chain', 'all'): start_group('blockchain/xchain')
    if args.stage in ('contract', 'all'): deploy_contract()
    if args.stage in ('services', 'all'):
        for group in ('xdb', 'executor', 'visualization'):
            start_group(group)


if __name__ == '__main__':
    main()
