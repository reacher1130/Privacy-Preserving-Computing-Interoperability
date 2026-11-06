#!/usr/bin/env python3
"""Connect Fateboard to native Guest and bound its JVM without replacing data."""
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
CONTAINER='fateboard-native-e2e'
REMOTE='/data/projects/fate/fateboard/service.sh'
def run(args,**kw):return subprocess.check_output(args,text=True,timeout=120,**kw)
if __name__=='__main__':
    target='fateflow.url=http://fate2-flow-guest-e2e:9380'
    config='/data/projects/fate/fateboard/conf/application.properties'
    flow_changed=run(['docker','exec',CONTAINER,'sh','-c',
                      'if grep -Fxq "$1" "$2"; then echo yes; else echo no; fi',
                      'sh',target,config]).strip()!='yes'
    if flow_changed:
        # Keep credentials in the container; export only the non-sensitive target.
        run(['docker','exec',CONTAINER,'sh','-c',
             'set -eu; if [ ! -f "$1.before-native-guest" ]; then '
             'umask 077; cp "$1" "$1.before-native-guest"; chmod 600 "$1.before-native-guest"; fi; '
             'sed -i "s#^fateflow.url=.*#$2#" "$1"', 'sh',config,target])
    original=run(['docker','exec',CONTAINER,'cat',REMOTE])
    backup=ROOT/'NewProject/.local-backups/optimization-20260908/fateboard-service.sh'
    backup.parent.mkdir(parents=True,exist_ok=True)
    if not backup.exists():backup.write_text(original)
    updated=original.replace('-Xmx2048m -Xms2048m','-Xmx768m -Xms128m -XX:+UseG1GC -XX:ActiveProcessorCount=2')
    # The image entrypoint used set -e with a short asynchronous Flow startup probe.
    # Wait for the actual services before declaring startup failed.
    entry='/data/projects/fate/bin/docker-entrypoint.sh'
    old_entry=run(['docker','exec',CONTAINER,'cat',entry])
    entry_backup=backup.with_name('fateboard-docker-entrypoint.sh')
    if not entry_backup.exists():entry_backup.write_text(old_entry)
    new_entry="""#!/bin/bash
set -e
export TERM=${TERM:-xterm}
source ${WORKDIR}/bin/init_env.sh
cd ${WORKDIR}/fate_flow
bash bin/service.sh start || true
ready=false
for attempt in $(seq 1 120); do
  if curl -fsS --max-time 2 http://127.0.0.1:9380/v2/site/info/query >/dev/null; then ready=true; break; fi
  sleep 2
done
$ready || exit 1
cd ${WORKDIR}/fateboard
bash service.sh start || true
ready=false
for attempt in $(seq 1 120); do
  if curl -fsS --max-time 2 http://127.0.0.1:8080/ >/dev/null; then ready=true; break; fi
  sleep 2
done
$ready || exit 1
cd ${WORKDIR}
exec "$@"
"""
    if old_entry!=new_entry:
        run(['docker','exec','-i',CONTAINER,'sh','-c','cat > '+entry],input=new_entry)
    if updated!=original or flow_changed:
        run(['docker','exec','-i',CONTAINER,'sh','-c','cat > '+REMOTE],input=updated)
        output=run(['docker','exec',CONTAINER,'bash','-lc','export JAVA_HOME=/data/projects/fate/env/jdk/jdk-8u345; export PATH="$JAVA_HOME/bin:$PATH"; cd /data/projects/fate/fateboard; bash service.sh restart'],stderr=subprocess.STDOUT)
        print(output[-700:])
    else:print('Fateboard runtime already configured')
