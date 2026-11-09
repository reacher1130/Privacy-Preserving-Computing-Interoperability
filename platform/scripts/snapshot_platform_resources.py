#!/usr/bin/env python3
import json,re,subprocess,sys,datetime
from pathlib import Path
from platform_runtime import CONTAINERS

def run(args):return subprocess.check_output(args,text=True,errors='replace',timeout=60)
r={'time':datetime.datetime.now().isoformat(),'containers':[],'backends':[]}
for line in run(['docker','stats','--no-stream','--format','{{json .}}']).splitlines():
 d=json.loads(line)
 if d['Name'] in CONTAINERS:r['containers'].append(d)
for line in run(['ps','-axo','pid=,args=']).splitlines():
 fields=line.strip().split(None,1)
 if len(fields)!=2:continue
 pid,cmd=fields
 if not cmd.startswith('/Library/Java/') or ' -jar ' not in cmd or '/NewProject/secretpad' not in cmd:continue
 out=run(['vmmap','-summary',pid]);match=re.search(r'^Physical footprint:\s+(.+)$',out,re.M)
 name='kimi' if 'kimi' in cmd else ('bob' if 'secretpad-bob' in cmd else 'alice')
 r['backends'].append({'node':name,'pid':pid,'footprint':match.group(1).strip() if match else 'unknown','periodicGc':'G1PeriodicGCInterval=60000' in cmd})
Path(sys.argv[1]).write_text(json.dumps(r,indent=2));print('captured',len(r['containers']),'containers',len(r['backends']),'backends')
