#!/usr/bin/env python3
"""Configure the installed native FATE pair for real cross-container OSX federation."""
import json, subprocess, time, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BACKUP=ROOT/'NewProject/.local-backups/topology-20260907/native-fate'
PARTIES={'guest':'JG0100001100000010','host':'JG0100001100000000'}
def run(args,**kw):
    try:return subprocess.check_output(args,text=True,timeout=120,**kw)
    except subprocess.CalledProcessError as e:
        print(e.output,flush=True);raise
def configure():
    # Docker allocates different IPs after stop/start; its network aliases persist.
    addresses={role:f'fate2-flow-{role}-e2e' for role in PARTIES}
    for role,party in PARTIES.items():
        container=f'fate2-flow-{role}-e2e'
        paths=['fate_flow/conf/service_conf.yaml','osx/conf/broker/route_table.json','osx/conf/broker/broker.properties','osx/service.sh','fate_flow/bin/service.sh','fate_flow/python/fate_flow/controller/parser.py']
        for path in paths:
            backup=BACKUP/role/path;backup.parent.mkdir(parents=True,exist_ok=True)
            if not backup.exists(): backup.write_text(run(['docker','exec',container,'cat','/data/projects/fate/'+path]))
        script=r'''import yaml,json,pathlib,re
root=pathlib.Path('/data/projects/fate')
p=root/'fate_flow/conf/service_conf.yaml';d=yaml.safe_load(p.read_text());d['default_engines']['federation']='osx';d['computing']['standalone']['cores']=2;d['federation']['osx']['mode']='queue';p.write_text(yaml.safe_dump(d,sort_keys=False))
p=root/'osx/conf/broker/broker.properties';s=p.read_text();s=re.sub(r'^self.party=.*$', 'self.party='+PARTY,s,flags=re.M);p.write_text(s)
routes={pid:{'default':[{'ip':ADDRESSES[role],'port':9370}]} for role,pid in PARTIES.items()}
routes[PARTY]['fateflow']=[{'ip':'127.0.0.1','port':9360}]
(root/'osx/conf/broker/route_table.json').write_text(json.dumps({'route_table':routes,'self_party':[PARTY]},indent=2))
p=root/'osx/service.sh';s=p.read_text().replace('-Xms4g -Xmx4g','-Xms128m -Xmx512m -XX:ActiveProcessorCount=2');s=re.sub(r'-XX:MaxDirectMemorySize=\w+', '-XX:MaxDirectMemorySize=256m',s);p.write_text(s)
p=root/'fate_flow/python/fate_flow/controller/parser.py';s=p.read_text().replace('"options": {"data_dir": STANDALONE_DATA_HOME}', '"options": {"data_dir": STANDALONE_DATA_HOME, "task_cores": max(1, int(self.engine_run.get("cores") or 1))}');p.write_text(s)
p=root/'fate_flow/bin/service.sh';s=p.read_text();marker='# Start native federation on container recovery'
if marker not in s:
    s=s.replace('    start)\n        load_config', '    start)\n        '+marker+'\n        (cd /data/projects/fate/osx && bash service.sh start) >/dev/null 2>&1\n        load_config')
if '# Bound native computing thread pools' not in s:
    s=s.replace('#!/bin/bash', '#!/bin/bash\n# Bound native computing thread pools\nexport OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1',1)
p.write_text(s)
'''
        run(['docker','exec','-i',container,'/data/projects/fate/env/python/venv/bin/python','-'],input='PARTY='+repr(party)+'\nPARTIES='+repr(PARTIES)+'\nADDRESSES='+repr(addresses)+'\n'+script)
        run(['docker','exec',container,'bash','-lc','source /data/projects/fate/bin/init_env.sh; cd /data/projects/fate/osx; bash service.sh restart'],stderr=subprocess.STDOUT)
        restart=subprocess.run(['docker','exec',container,'bash','-lc','source /data/projects/fate/bin/init_env.sh; cd /data/projects/fate/fate_flow; TERM=xterm bash bin/service.sh restart 1'],capture_output=True,text=True,timeout=120)
        port=19381 if role=='guest' else 19382
        for _ in range(60):
            try:
                data=json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/v2/site/info/query',timeout=3))
                if data.get('data',{}).get('party_id')==party:break
            except Exception:pass
            time.sleep(2)
        else:raise RuntimeError(role+' native readiness failed: '+restart.stdout[-500:])
        print(role,'native site ready',flush=True)
if __name__=='__main__':configure()
