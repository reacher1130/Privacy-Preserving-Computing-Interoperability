#!/usr/bin/env python3
"""Restore only Alice's local mtwx table-result index. Default: read-only check."""

import argparse
import csv
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import urllib.request

from restore_alice_peer_institution import ALICE, KIMI, compare_snapshot, online_backup, quote, readonly, require, same_records, tables

PROJECT, JOB, TASK, REF = 'wckkekky', 'mtwx', 'mtwx-new-n3', 'mtwx-new-n3-output-0'
URI, GRAPH, FINISHED = 'mtwx_new_n3_output_0', 'yoyytwos', '2026-11-03 05:29:22'
ROW = (PROJECT, 'FedTable', 'alice', REF, JOB, TASK, 0)
FIELDS = 'project_id,kind,node_id,ref_id,job_id,task_id,is_deleted'
ARTIFACTS = {
    'alice': (66, 'ecf8d034a46a389915f83ae0a27d5dc294788dfb8660b6892b881aa1ccf263e3', ['age', 'income', 'id']),
    'kimi': (55, '3e3935a03996fb49ed95ffea21960f7d6f665784b79c7579016b08608dfff85d', ['score', 'label', 'id']),
}


def verify_artifacts():
    for site, (size, digest, fields) in ARTIFACTS.items():
        command = ['docker', 'exec', 'gaofeng-kuscia-autonomy-' + site, '/home/kuscia/bin/kubectl',
                   'get', 'domaindata', '-n', site, REF, '-o', 'json']
        resource = json.loads(subprocess.run(command, capture_output=True, check=True, timeout=8).stdout)
        meta, spec = resource['metadata'], resource['spec']
        require((meta['name'], meta['namespace'], spec['author'], spec['relativeURI'], spec['type'],
                 spec['vendor'], spec['dataSource'], spec['fileFormat'])
                == (REF, site, site, URI, 'table', 'secretflow', 'default-data-source', 'csv'),
                'Local DomainData identity does not match: ' + site)
        require(sorted((c['name'], c['type']) for c in spec['columns']) == sorted((c, 'int') for c in fields),
                'DomainData schema differs: ' + site)
        root = Path('/srv/ppci/kuscia') / site / 'root/home/kuscia/var/storage'
        path = root / 'data' / URI
        require(path.resolve() == path and path.is_file() and (root / site / URI).resolve() == path,
                'Local artifact path or Pad alias differs: ' + site)
        raw = path.read_bytes()
        require(len(raw) == size and hashlib.sha256(raw).hexdigest() == digest, 'Artifact bytes differ: ' + site)
        reader = csv.DictReader(io.StringIO(raw.decode()))
        require(reader.fieldnames == fields and sorted(r['id'] for r in reader) == ['1002', '1003', '1004', '1006'],
                'Artifact columns or public intersection differ: ' + site)


def verify_task(db):
    require(db.execute('SELECT graph_id,status,finished_time,is_deleted FROM project_job WHERE project_id=? AND job_id=?',
                       (PROJECT, JOB)).fetchall() == [(GRAPH, 'SUCCEED', FINISHED, 0)], 'Successful job no longer matches')
    rows = db.execute('SELECT status,parties,is_deleted FROM project_job_task WHERE project_id=? AND job_id=? AND task_id=?',
                      (PROJECT, JOB, TASK)).fetchall()
    require(len(rows) == 1 and rows[0][0] == 'SUCCEED' and rows[0][2] == 0
            and sorted(json.loads(rows[0][1])) == ['alice', 'kimi'], 'Successful PSI task or parties changed')
    joins = db.execute('SELECT joins FROM project_fed_table WHERE project_id=? AND fed_table_id=? AND is_deleted=0',
                       (PROJECT, REF)).fetchall()
    require(len(joins) == 1 and sorted((x['nodeId'], x['datatableId']) for x in json.loads(joins[0][0]))
            == [('alice', REF), ('kimi', REF)], 'Federated table recipients changed')
    require(db.execute('SELECT kind,job_id,task_id,is_deleted FROM project_result WHERE project_id=? AND node_id=? AND ref_id=?',
                       (PROJECT, 'kimi', REF)).fetchall() == [('FedTable', JOB, TASK, 0)], 'Peer result projection changed')


def preflight(db):
    verify_task(db)
    definition = db.execute("SELECT sql FROM sqlite_master WHERE name='project_result' AND type='table'").fetchone()
    require(definition and 'autoincrement' in definition[0].lower(), 'Unexpected project_result key')
    indexes = db.execute('PRAGMA index_list(project_result)').fetchall()
    require(any(r[2] and [c[2] for c in db.execute('PRAGMA index_info(' + quote(r[1]) + ')')]
                == ['project_id', 'kind', 'node_id', 'ref_id'] for r in indexes), 'Missing reviewed result uniqueness constraint')
    require(not db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='project_result'").fetchall(),
            'Unexpected project_result trigger')
    rows = db.execute(f'SELECT {FIELDS} FROM project_result WHERE node_id=? AND ref_id=?', ('alice', REF)).fetchall()
    require(not rows or rows == [ROW], 'Existing Alice projection conflicts or is soft-deleted')
    return 'noop' if rows else 'insert'


def verify_delta(db):
    names = tables(db, 'main')
    require(names == tables(db, 'prior'), 'Database table list changed')
    for name in names:
        if name != 'project_result':
            same_records(db, name)
    row = db.execute(f'SELECT id,{FIELDS} FROM main.project_result WHERE node_id=? AND ref_id=?', ('alice', REF)).fetchall()
    require(len(row) == 1 and row[0][1:] == ROW, 'Inserted result differs from the reviewed metadata')
    columns = ','.join(quote(r[1]) + ' COLLATE BINARY' for r in db.execute('PRAGMA main.table_info(project_result)'))
    current = 'SELECT ' + columns + ',count(*) FROM main.project_result WHERE id<>? GROUP BY ' + columns
    before = 'SELECT ' + columns + ',count(*) FROM prior.project_result GROUP BY ' + columns
    for left, right in ((current, before), (before, current)):
        require(db.execute('SELECT count(*) FROM (' + left + ' EXCEPT ' + right + ')', (row[0][0],)).fetchone() == (0,),
                'A pre-existing project result changed')
    return len(names)


def restore(target, backup_path, artifact_check=verify_artifacts):
    artifact_check()
    with readonly(target) as db:
        if preflight(db) == 'noop':
            return {'action': 'noop'}
    backup = online_backup(target, backup_path)
    db = sqlite3.connect(target.resolve().as_uri() + '?mode=rw', uri=True, isolation_level=None, timeout=5)
    try:
        db.execute('BEGIN IMMEDIATE')
        db.execute('ATTACH DATABASE ? AS prior', (backup_path.resolve().as_uri() + '?mode=ro',))
        require(preflight(db) == 'insert', 'Target changed after online backup')
        compare_snapshot(db, False)
        artifact_check()

        def insert_only(action, table, column, namespace, trigger):
            if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
                allowed = namespace == 'main' and not trigger and (
                    action == sqlite3.SQLITE_INSERT and table == 'project_result' or table == 'sqlite_sequence')
                return sqlite3.SQLITE_OK if allowed else sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        db.set_authorizer(insert_only)
        db.execute(f'INSERT INTO project_result({FIELDS},gmt_create,gmt_modified) VALUES (?,?,?,?,?,?,?,?,?)',
                   (*ROW, FINISHED, FINISHED))
        checked = verify_delta(db)
        db.execute('COMMIT')
        return {'action': 'insert', 'backup': backup, 'comparedTables': checked, 'existingRecordsUnchanged': True}
    finally:
        if db.in_transaction:
            db.execute('ROLLBACK')
        db.close()


def verify_api():
    def post(path, payload):
        return urllib.request.urlopen(urllib.request.Request('http://192.168.45.101:18103/api/v1alpha1' + path,
            data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', 'Node-Id': 'alice'}), timeout=10)
    with post('/node/result/list', {'ownerId': 'alice', 'pageNumber': 1, 'pageSize': 100,
                                   'nameFilter': '', 'kindFilters': [], 'timeSortingRule': 'descending'}) as r:
        data = json.load(r)
    require(data.get('status', {}).get('code') == 0, 'Alice result list rejected')
    rows = data['data'].get('nodeAllResultsVOList', [])
    require(sum(r.get('nodeId') == 'alice' and r.get('nodeResultsVO', {}).get('domainDataId') == REF for r in rows) == 1,
            'Alice exact result is not uniquely listed')
    with post('/data/download', {'nodeId': 'alice', 'domainDataId': REF}) as r:
        raw = r.read(4096)
        require(r.headers.get('Content-Type', '').startswith('application/octet-stream'), 'Unexpected download type')
    require(len(raw) == ARTIFACTS['alice'][0] and hashlib.sha256(raw).hexdigest() == ARTIFACTS['alice'][1],
            'Alice download bytes do not match the local result')
    return {'listed': True, 'downloadSha256': ARTIFACTS['alice'][1], 'rows': 4}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    with readonly(KIMI) as db:
        verify_task(db)
    result = {'jobId': JOB, 'projectId': PROJECT, 'taskId': TASK, 'resultId': REF}
    if not args.apply:
        verify_artifacts()
        with readonly(ALICE) as db:
            result['plannedAction'] = preflight(db)
        print(json.dumps(result, indent=2))
        return
    require(os.geteuid() == 0, 'Use the office root process')
    os.umask(0o077)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    log = Path('/var/log/ppci/regression-20261103') / ('alice-mtwx-result-' + stamp + '.json')
    log.parent.mkdir(parents=True, exist_ok=True)
    backup = Path('/var/backups/ppci/native-alice-mtwx-result') / (stamp + '.sqlite')
    with log.open('x') as f:
        try:
            result.update(restore(ALICE, backup))
            result['api'] = verify_api()
        except Exception as error:
            result['error'] = str(error) if isinstance(error, RuntimeError) else type(error).__name__
            raise
        finally:
            json.dump(result, f, indent=2)
            f.write('\n')
            print(json.dumps({'evidence': str(log), **result}, indent=2))


if __name__ == '__main__':
    main()
