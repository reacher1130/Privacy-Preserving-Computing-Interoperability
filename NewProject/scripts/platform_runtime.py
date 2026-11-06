#!/usr/bin/env python3
"""Restore/check the installed local platform without replacing stateful containers."""
import argparse, json, os, subprocess, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
NODES = [f'{os.environ.get("USER", "gaofeng")}-kuscia-autonomy-{n}' for n in ('alice','bob','kimi')]
CONTAINERS = NODES + ['kusciaapi-alice-proxy','kusciaapi-bob-proxy','kusciaapi-kimi-proxy','bfia-alice-proxy','bfia-bob-proxy'] + [f'xchain{i}.node.com' for i in (1,2,3)] + [f'{kind}{i}.node.com' for kind in ('dataowner','storage') for i in (1,2,3)] + ['executor1.node.com','executor2.node.com','fate2-flow-e2e','fate2-flow-guest-e2e','fate2-flow-host-e2e','secretpad-frontend-multiparty-e2e','secretpad-frontend-e2e','secretpad-native-e2e','secretpad-native-kimi-e2e','fateboard-native-e2e','paddledtx-native-e2e']
if Path('/srv/ppci/dtx-manager/conf/app.conf').is_file():
    CONTAINERS.append('ppci-dtx-manager')
def run(args, timeout=40):
    return subprocess.check_output(args, text=True, timeout=timeout).strip()
def get(url, data=None):
    req=urllib.request.Request(url, data=None if data is None else json.dumps(data).encode(), headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=25) as r: return json.load(r)
def backend(node, port):
    if node == 'kimi': envelope=get(f'http://127.0.0.1:{port}/api/v1alpha1/node/list', {})
    else: envelope=get(f'http://127.0.0.1:{port}/api/v1alpha1/config/protocol')
    if envelope.get('status', {}).get('code') != 0:
        raise RuntimeError(envelope.get('status', 'Missing API status'))
    return envelope
def only_storage_blocks_tasks(paddle):
    executors=paddle.get('executors', [])
    storage=paddle.get('storage', [])
    return (paddle.get('requesterConfigured') is True
            and paddle.get('modelStorageType')=='XuperDB'
            and paddle.get('storageReady') is False
            and bool(executors) and all(p.get('ready') is True for p in executors)
            and bool(storage) and all(p.get('checked') is True for p in storage)
            and any(p.get('ready') is False for p in storage))
def restore():
    # These contain chain ledgers, uploaded data, and FATE state in overlays.
    # Never run compose up --force-recreate or docker rm on these instances.
    existing = set(run(['docker','ps','-a','--format','{{.Names}}']).splitlines())
    missing = [c for c in CONTAINERS if c not in existing]
    if missing: raise RuntimeError('Missing installed containers (restore backups first): '+', '.join(missing))
    running=set(run(['docker','ps','--format','{{.Names}}']).splitlines())
    newly_started = set()
    for c in CONTAINERS:
        if c not in running:
            print(run(['docker','start',c], timeout=120), flush=True)
            newly_started.add(c)
    # Native services can outlive their launcher or take longer to boot than Docker.
    # Recover only a pair just started here; never interrupt existing native jobs.
    if newly_started.intersection({'fate2-flow-guest-e2e','fate2-flow-host-e2e'}):
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            try:
                assert all(get(f'http://127.0.0.1:{port}/v2/site/info/query').get('data',{}).get('party_id')
                           for port in (19381,19382))
                break
            except Exception: time.sleep(2)
        else:
            from configure_native_fate import configure
            configure()

    for node,port in [('alice',18080),('bob',28090),('kimi',38090)]:
        try:
            backend(node, port); continue
        except Exception: pass
        # Refuse a duplicate JVM if startup is already underway.
        commands=run(['ps','-axo','command='])
        marker={'alice':'secretpad-alice-local-kuscia','bob':'secretpad-bob','kimi':'secretpad-kimi-upstream'}[node]
        if any('java' in line and marker in line for line in commands.splitlines()):
            print(node+': JVM exists; waiting for readiness')
        else:
            log=(ROOT/'NewProject'/'.runtime'); log.mkdir(exist_ok=True)
            with (log/f'{node}-launch.log').open('ab') as out:
                subprocess.Popen(['bash',str(ROOT/'NewProject'/'scripts'/f'start_secretpad_{node}.sh')],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=out,stderr=out,start_new_session=True)
        deadline=time.monotonic()+300
        while time.monotonic()<deadline:
            try: backend(node, port); break
            except Exception: time.sleep(2)
        else: raise RuntimeError(node+' failed readiness within 300 seconds')
def status():
    result={'containers':[], 'backends':{}, 'chain':[], 'errors':[]}
    storage_task_error=None
    rows=json.loads(run(['docker','inspect',*CONTAINERS]))
    for c in rows:
        result['containers'].append({'name':c['Name'].lstrip('/'),'running':c['State']['Running'],'image':c['Config']['Image']})
        if not c['State']['Running']: result['errors'].append(c['Name']+' stopped')
    if 'ppci-dtx-manager' in CONTAINERS:
        try:
            response=get('http://127.0.0.1:8084/dtx/v1/data/list?pageNo=1&pageSize=1')
            rejected=response.get('code')=='SignErr'
            result['paddledtxManager']={'apiResponsive':True,'anonymousRejected':rejected}
            if not rejected: result['errors'].append('PaddleDTX manager anonymous access boundary failed')
        except Exception as e: result['errors'].append('PaddleDTX manager: '+str(e))
    proxy_ips = {name: f'192.168.117.{i}' for i, name in enumerate([
        'bfia-alice-proxy', 'bfia-bob-proxy', 'kusciaapi-alice-proxy',
        'kusciaapi-bob-proxy', 'kusciaapi-kimi-proxy'], 10)}
    for c in rows:
        name = c['Name'].lstrip('/')
        network = c['NetworkSettings']['Networks'].get('ppci-kuscia-exchange')
        if name in proxy_ips and network:
            fixed = (network.get('IPAMConfig') or {}).get('IPv4Address')
            if fixed != proxy_ips[name] or network.get('IPAddress') != fixed:
                result['errors'].append(name+' must retain its dedicated static proxy IP')
    for node,port in [('alice',18080),('bob',28090),('kimi',38090)]:
        try:
            envelope=backend(node, port)
            if envelope['status']['code']!=0: raise RuntimeError(envelope['status'])
            result['backends'][node]=envelope['data']
        except Exception as e: result['errors'].append(node+': '+str(e))
    try:
        result['paddledtx']=get('http://127.0.0.1:18080/api/v1alpha1/paddledtx/status')['data']
        if not result['paddledtx']['ready']:
            error='PaddleDTX not ready: '+str(result['paddledtx'].get('error', 'Unknown readiness error'))
            result['errors'].append(error)
            if only_storage_blocks_tasks(result['paddledtx']): storage_task_error=error
    except Exception as e: result['errors'].append(str(e))
    for i in (1,2,3):
        try:
            data=json.loads(run(['docker','exec',f'xchain{i}.node.com','./xchain-cli','status']))
            result['chain'].append({'node':i,**data['blockchains'][0]['ledger']})
        except Exception as e: result['errors'].append(f'chain {i}: {e}')
    # A healthy container is not enough: verify the required protocol boundaries.
    result['topology']={'routes':[], 'fate':[], 'platformNodes':3,
                        'independentNativePlatforms':['FATE', 'PaddleDTX']}
    bob=result['backends'].get('bob', {})
    if bob.get('supportedProtocols') != ['bfia'] or bob.get('activeProtocol') != 'bfia':
        result['errors'].append('Bob must expose only BFIA')
    for node, route, expected in [('alice','alice-bob','bfia'),('bob','bob-alice','bfia'),
                                   ('alice','alice-kimi','kuscia'),('kimi','kimi-alice','kuscia')]:
        try:
            data=json.loads(run(['docker','exec',f'{os.environ.get("USER", "gaofeng")}-kuscia-autonomy-{node}',
                                 'kubectl','get','clusterdomainroute',route,'-o','json']))
            actual=data['spec']['interConnProtocol']
            ready=any(c.get('type')=='Ready' and c.get('status')=='True' for c in data.get('status',{}).get('conditions',[]))
            result['topology']['routes'].append({'node':node,'route':route,'protocol':actual,'ready':ready})
            if actual!=expected or not ready: result['errors'].append(route+' protocol or readiness mismatch')
        except Exception as e: result['errors'].append(route+': '+str(e))
    for role,port in [('guest',19381),('host',19382)]:
        try:
            request=urllib.request.Request(f'http://127.0.0.1:{port}/v2/site/info/query',
                        headers={'Content-Type':'application/json'}, method='GET')
            with urllib.request.urlopen(request,timeout=25) as response: data=json.load(response)
            ready=data.get('code')==0 and bool(data.get('data',{}).get('party_id'))
            result['topology']['fate'].append({'role':role,'port':port,'ready':ready})
            if not ready: result['errors'].append('Native FATE '+role+' not ready')
        except Exception as e: result['errors'].append('Native FATE '+role+': '+str(e))
        try:
            container=f'fate2-flow-{role}-e2e'
            routes=json.loads(run(['docker','exec',container,'cat',
                '/data/projects/fate/osx/conf/broker/route_table.json']))['route_table']
            for peer,party in [('guest','JG0100001100000010'),('host','JG0100001100000000')]:
                expected=f'fate2-flow-{peer}-e2e'
                entries=routes.get(party,{}).get('default',[])
                if not any(e.get('ip')==expected and e.get('port')==9370 for e in entries):
                    result['errors'].append(f'Native FATE {role} route to {peer} must use stable Docker name {expected}')
        except Exception as e: result['errors'].append('Native FATE '+role+' routes: '+str(e))
    heights=[c['trunkHeight'] for c in result['chain']]
    if len(heights)==3 and max(heights)-min(heights)>3: result['errors'].append('chain heights diverged')
    result['healthy']=not result['errors']
    result['runtimeHealthy']=not [e for e in result['errors'] if e!=storage_task_error]
    result['taskReadinessErrors']=[storage_task_error] if storage_task_error else []
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result['healthy']
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('action',choices=['start','status']); args=ap.parse_args()
    if args.action=='start': restore()
    raise SystemExit(0 if status() else 1)
