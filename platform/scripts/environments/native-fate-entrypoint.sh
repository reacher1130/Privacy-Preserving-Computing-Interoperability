#!/usr/bin/env bash
# A fresh native Guest/Host pair, with independent persistent Flow volumes.
set -eo pipefail
ulimit -n 65536
cd /data/projects/fate
source bin/init_env.sh
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
python - <<'PY'
import json, os, pathlib, re, yaml
root = pathlib.Path('/data/projects/fate')
role = os.environ['PPCI_FATE_ROLE']
parties = {'guest': 'JG0100001100000010', 'host': 'JG0100001100000000'}
party = parties[role]
p = root / 'fate_flow/conf/service_conf.yaml'
d = yaml.safe_load(p.read_text())
d['party_id'] = party
d['fateflow']['host'] = '0.0.0.0'
d['default_engines']['federation'] = 'osx'
d['computing']['standalone']['cores'] = 2
d['federation']['osx']['mode'] = 'queue'
p.write_text(yaml.safe_dump(d, sort_keys=False))
p = root / 'fate_flow/conf/job_default_config.yaml'
d = yaml.safe_load(p.read_text())
d['job_cores'] = 1
d['computing_partitions'] = 1
d['task_run']['standalone']['cores'] = 1
p.write_text(yaml.safe_dump(d, sort_keys=False))
p = root / 'osx/conf/broker/broker.properties'
p.write_text(re.sub(r'^self.party=.*$', 'self.party=' + party, p.read_text(), flags=re.M))
routes = {pid: {'default': [{'ip': f'fate2-flow-{r}-e2e', 'port': 9370}]} for r, pid in parties.items()}
routes[party]['fateflow'] = [{'ip': '127.0.0.1', 'port': 9360}]
(root / 'osx/conf/broker/route_table.json').write_text(json.dumps({'route_table': routes, 'self_party': [party]}, indent=2))
p = root / 'osx/service.sh'
s = p.read_text().replace('-Xms4g -Xmx4g', '-Xms128m -Xmx512m -XX:ActiveProcessorCount=2')
p.write_text(re.sub(r'-XX:MaxDirectMemorySize=\w+', '-XX:MaxDirectMemorySize=256m', s))
p = root / 'fate_flow/python/fate_flow/controller/parser.py'
p.write_text(p.read_text().replace('"options": {"data_dir": STANDALONE_DATA_HOME}', '"options": {"data_dir": STANDALONE_DATA_HOME, "task_cores": max(1, int(self.engine_run.get("cores") or 1))}'))
PY
(cd osx && bash service.sh start)
(cd fate_flow && TERM=xterm bash bin/service.sh start 1)
if [[ "$PPCI_FATE_ROLE" == guest && "${PPCI_FATE_EXTERNAL_BOARD:-0}" != 1 ]]; then
  export JAVA_TOOL_OPTIONS='-Xms64m -Xmx256m -XX:ActiveProcessorCount=2'
  (cd fateboard && bash service.sh start)
fi
exec sleep infinity
