#!/usr/bin/env python3
"""Reap workers of explicitly named, terminal native FATE jobs; preserve all job files."""
import argparse, json, subprocess, urllib.request
p=argparse.ArgumentParser();p.add_argument('job_ids',nargs='+');p.add_argument('--apply',action='store_true');a=p.parse_args()
terminal={'success','failed','canceled','timeout','rejected'}
for role,port in [('guest',19381),('host',19382)]:
    for jid in a.job_ids:
        if not jid.isdigit():raise SystemExit('Invalid native job ID')
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/v2/job/query?job_id={jid}',timeout=30) as r:d=json.load(r)
        if d.get('code')!=0 or not d.get('data') or any(x.get('status') not in terminal for x in d['data']):
            raise SystemExit(f'{role} {jid} is not verified terminal')
script=r'''
import os,json,signal
ids=set(JOB_IDS);matches=[]
for item in os.listdir('/proc'):
    if not item.isdigit():continue
    pid=int(item)
    try:
        cmd=open(f'/proc/{pid}/cmdline','rb').read().replace(b'\0',b' ').decode()
        if 'fate_flow/manager/worker/' not in cmd:continue
        env=open(f'/proc/{pid}/environ','rb').read().split(b'\0')
        job=next((x.split(b'=',1)[1].decode() for x in env if x.startswith(b'FATE_JOB_ID=')),None)
        if job not in ids:
            job=next((j for j in ids if f'/jobs/{j}/' in cmd),None)
        if job in ids:matches.append({'pid':pid,'job_id':job,'command':cmd})
    except (FileNotFoundError,ProcessLookupError):pass
for m in matches:
    if APPLY:
        try:os.kill(m['pid'],signal.SIGTERM)
        except ProcessLookupError:pass
print(json.dumps({'matches':matches,'applied':APPLY}))
'''
for role in ('guest','host'):
    c=f'fate2-flow-{role}-e2e';code='JOB_IDS='+repr(a.job_ids)+'\nAPPLY='+repr(a.apply)+'\n'+script
    r=subprocess.check_output(['docker','exec','-i',c,'/data/projects/fate/env/python/venv/bin/python','-'],input=code,text=True,timeout=45)
    print(json.dumps({"container":c,**json.loads(r)}),flush=True)
