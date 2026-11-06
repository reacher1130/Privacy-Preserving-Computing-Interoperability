#!/usr/bin/env python3
"""Conservative project-only cleanup. Default prints the exact plan; --apply removes it."""
import argparse, json, os, shutil, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
STALE_CONTAINERS=['secretpad-frontend-e2e-broken-20260906','secretpad-frontend-dev-e2e','fate2-standalone-e2e']
STALE_IMAGES=['paddledtx-dai:2.1-local-20260905','paddledtx-dai:2.1-local-20260905-cgo','paddledtx-dai:2.1-local-20260905-static-cgo']
GENERATED=['NewProject/secretpad-frontend/apps/platform/dist','NewProject/secretpad-frontend/apps/platform/src/.umi','NewProject/secretpad-frontend/apps/platform/src/.umi-production','NewProject/secretpad-frontend/typing-errors.log','NewProject/secretpad-frontend/typing-errors2.log']
TARS=['gaofeng-kuscia-autonomy-alice/images/fate2-adapter-0.1.0.tar','gaofeng-kuscia-autonomy-alice/images/image_ZJ2gKE2Z.tar','gaofeng-kuscia-autonomy-alice/images/fate2-adapter-0.1.1-e2e.tar','gaofeng-kuscia-autonomy-alice/images/fate2-adapter-0.1.1-e2e-current.tar','kuscia-node-bob/images/fate2-adapter-0.1.1-e2e.tar','kuscia-node-bob/images/fate2-adapter-0.1.1-e2e-current.tar']
def cmd(args): return subprocess.check_output(args,text=True,timeout=45).strip()
def size(p):
    if p.is_file(): return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob('*') if f.is_file() and not f.is_symlink())
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--apply',action='store_true');args=ap.parse_args()
    ids=cmd(['docker','ps','-aq']).splitlines(); containers=json.loads(cmd(['docker','inspect',*ids])) if ids else []
    used={c['Image'] for c in containers}; named={c['Name'].lstrip('/'):c for c in containers}
    # Exact file mounts must not be unlinked. Directory mounts can contain old import
    # tarballs: these six explicit archives have already been imported into containerd.
    mounts=[Path(m['Source']).resolve() for c in containers for m in c.get('Mounts',[]) if m['Type']=='bind']
    def protected(p): return any(p==m or m in p.parents for m in mounts)
    files=[]
    for path in GENERATED:
        p=ROOT/path
        if p.exists() and not p.is_symlink() and not protected(p): files.append(p)
    for directory, dirs, names in os.walk(ROOT):
        dirs[:]=[d for d in dirs if d not in ('.git','node_modules','vendor','.cache','.local-backups','acceptance-20260907') and not Path(directory,d).is_symlink()]
        if '.DS_Store' in names:
            p=Path(directory)/'.DS_Store'
            if not protected(p): files.append(p)
    # Retain one current FATE adapter export plus both locally tagged Docker images.
    canonical=ROOT/'NewProject/thirdparty/fate2-adapter/fate2-adapter-0.1.1-e2e-current.tar'
    if canonical.is_file():
        cmd(['docker','image','inspect','secretflow/fate2-adapter:0.1.0','secretflow/fate2-adapter:0.1.1-e2e'])
        files += [ROOT/p for p in TARS if (ROOT/p).is_file() and (ROOT/p).resolve() not in mounts]
    images=[]
    for tag in STALE_IMAGES:
        probe=subprocess.run(['docker','image','inspect',tag],capture_output=True,text=True)
        if probe.returncode==0:
            image=json.loads(probe.stdout)[0]
            if image['Id'] not in used: images.append({'tag':tag,'id':image['Id'],'bytes':image['Size']})
    removable=[n for n in STALE_CONTAINERS if n in named and not named[n]['State']['Running']]
    report={'apply':args.apply,'containers':removable,'images':images,'files':[{'path':str(p.relative_to(ROOT)),'bytes':size(p)} for p in files], 'skippedRunning':[n for n in STALE_CONTAINERS if n in named and named[n]['State']['Running']]}
    report['fileBytes']=sum(x['bytes'] for x in report['files'])
    report['imageLogicalBytes']=sum(x['bytes'] for x in images)
    report['note']='Image logical sizes include shared layers; not a claim about physical bytes freed. No volumes, ledgers, databases, source repositories, node_modules, or compiler caches are removed.'
    evidence=ROOT/'NewProject/docs/acceptance-20260907';evidence.mkdir(parents=True,exist_ok=True)
    if args.apply:
        for name in removable:
            current=json.loads(cmd(['docker','inspect',name]))[0]
            if current['State']['Running']: raise RuntimeError(name+' became active')
            cmd(['docker','rm',name])
        for image in images: cmd(['docker','image','rm',image['tag']])
        for p in files:
            if p.is_dir(): shutil.rmtree(p)
            else: p.unlink()
        report['completed']=True
    (evidence/('cleanup-applied.json' if args.apply else 'cleanup-plan.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
