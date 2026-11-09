#!/usr/bin/env python3
"""Losslessly compress closed, rotated Kuscia logs; never touch active log files."""
import json, subprocess
from pathlib import Path
SCRIPT = r'''
import gzip,hashlib,json,os,subprocess
from pathlib import Path
rows=[]
for path in Path('/home/kuscia/var/logs/envoy').glob('*.log-20*'):
    if not path.is_file() or path.name.endswith(('.gz','.tmp')):continue
    target=Path(str(path)+'.gz');tmp=Path(str(target)+'.optimization.tmp')
    if target.exists() or tmp.exists():continue
    opened=subprocess.run(['fuser',str(path)],capture_output=True)
    if opened.returncode != 1:continue
    before=path.stat();digest=hashlib.sha256()
    try:
        with path.open('rb') as src, tmp.open('xb') as raw:
            os.fchmod(raw.fileno(),before.st_mode & 0o777)
            with gzip.GzipFile(filename=path.name,mode='wb',fileobj=raw,compresslevel=6,mtime=int(before.st_mtime)) as dst:
                while chunk:=src.read(1024*1024):digest.update(chunk);dst.write(chunk)
        verified=hashlib.sha256()
        with gzip.open(tmp,'rb') as stream:
            while chunk:=stream.read(1024*1024):verified.update(chunk)
        after=path.stat()
        if digest.digest()!=verified.digest() or (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise RuntimeError('archive verification failed: '+str(path))
        if subprocess.run(['fuser',str(path)],capture_output=True).returncode!=1:raise RuntimeError('archive opened during compression')
        tmp.rename(target);os.utime(target,(before.st_atime,before.st_mtime));path.unlink()
        rows.append({'source':str(path),'archive':str(target),'beforeBytes':before.st_size,'afterBytes':target.stat().st_size,'sha256':digest.hexdigest()})
    finally:
        if tmp.exists():tmp.unlink()
print(json.dumps(rows))
'''
if __name__=='__main__':
    result=[]
    for node in ('alice','bob','kimi'):
        raw=subprocess.check_output(['docker','exec','-i',f'gaofeng-kuscia-autonomy-{node}','python3','-'],input=SCRIPT,text=True)
        result.append({'node':node,'files':json.loads(raw)})
        print(node,len(result[-1]['files']),'archives compressed',flush=True)
    out=Path(__file__).resolve().parents[1]/'docs/optimization-20260908/log-compression.json'
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2))
