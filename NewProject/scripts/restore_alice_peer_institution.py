#!/usr/bin/env python3
"""Restore only Alice's missing, authoritative Kimi institution metadata.

Use Python 3.11 on the office host. Default is read-only preflight; --apply
creates a private online SQLite backup and performs one insert-only repair.
--self-test uses temporary fixtures only. No credentials are selected or emitted;
other table contents are compared opaquely inside SQLite, without returning rows.

Recovery: retain the 0600 backup and its SHA256. Never copy it over a running
WAL database. Stop Alice first, preserve its current DB/WAL/SHM, and reconcile
any writes after the backup before a reviewed offline restore. This script never
automatically replaces a database or deletes a restored institution.
"""

import argparse
import contextlib
import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import urllib.request


ALICE = Path('/opt/ppci/NewProject/secretpad/db_secretflow/secretpad.sqlite')
KIMI = Path('/opt/ppci/NewProject/secretpad-kimi-upstream/db/secretpad.sqlite')
INST_ID, INST_NAME = 'gqxzwemm', 'kimi'
OWN_INST = 'rqzvglmu'
FIELDS = ('inst_id', 'name', 'is_deleted', 'gmt_create', 'gmt_modified')
EXPECTED_COLUMNS = [
    ('id', 'INTEGER', 0, None, 1),
    ('inst_id', 'VARCHAR(64)', 1, None, 0),
    ('name', 'VARCHAR(256)', 0, 'NULL', 0),
    ('is_deleted', 'TINYINT(1)', 1, "'0'", 0),
    ('gmt_create', 'DATETIME', 1, 'CURRENT_TIMESTAMP', 0),
    ('gmt_modified', 'DATETIME', 1, 'CURRENT_TIMESTAMP', 0),
]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def quote(name):
    return '"' + name.replace('"', '""') + '"'


@contextlib.contextmanager
def readonly(path):
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True,
                         isolation_level=None, timeout=5)
    try:
        db.execute('PRAGMA query_only=ON')
        yield db
    finally:
        db.close()


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def schema(db):
    columns = [(row[1], row[2].upper(), *row[3:]) for row in db.execute('PRAGMA table_info(inst)')]
    require(columns == EXPECTED_COLUMNS, 'Institution schema differs from reviewed schema')
    definition = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='inst'").fetchone()[0]
    require('autoincrement' in definition.lower(), 'Institution local PK is not AUTOINCREMENT')
    indexes = {(row[1], row[2], tuple(item[2] for item in db.execute('PRAGMA index_info(' + quote(row[1]) + ')')))
               for row in db.execute('PRAGMA index_list(inst)')}
    require(indexes == {('upk_inst_id', 1, ('inst_id',)), ('key_inst_name', 0, ('name',))},
            'Institution indexes differ from reviewed constraints')
    require(not list(db.execute('PRAGMA foreign_key_list(inst)')), 'Unexpected institution foreign keys')
    require(not list(db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='inst'")),
            'Unexpected institution triggers')


def authoritative(source):
    with readonly(source) as db:
        schema(db)
        rows = db.execute('SELECT ' + ','.join(FIELDS) + ' FROM inst WHERE inst_id=?', (INST_ID,)).fetchall()
        require(len(rows) == 1, 'Authoritative institution is missing or duplicated')
        row = rows[0]
        require(row[:3] == (INST_ID, INST_NAME, 0), 'Authoritative institution identity/name/deletion changed')
        for stamp in row[3:]:
            datetime.datetime.strptime(stamp, '%Y-%m-%d %H:%M:%S')
        require(db.execute("SELECT inst_id,is_deleted FROM node WHERE node_id='kimi'").fetchall()
                == [(INST_ID, 0)], 'Authoritative Kimi node reference changed')
        return row


def preflight(db, metadata):
    schema(db)
    require(db.execute("SELECT inst_id,is_deleted FROM node WHERE node_id='kimi'").fetchall()
            == [(INST_ID, 0)], 'Alice Kimi node reference changed')
    require(db.execute("SELECT inst_id,is_deleted FROM node WHERE node_id='alice'").fetchall()
            == [(OWN_INST, 0)], 'Alice own node reference changed')
    require(db.execute('SELECT name,is_deleted FROM inst WHERE inst_id=?', (OWN_INST,)).fetchall()
            == [('alice', 0)], 'Alice own institution changed')
    require(not db.execute('SELECT 1 FROM inst WHERE name=? AND inst_id<>?',
                          (INST_NAME, INST_ID)).fetchall(), 'Same institution name has a different identity')
    rows = db.execute('SELECT ' + ','.join(FIELDS) + ' FROM inst WHERE inst_id=?', (INST_ID,)).fetchall()
    require(not rows or rows == [metadata], 'Existing institution conflicts or is soft-deleted')
    return 'noop' if rows else 'insert'


def tables(db, namespace):
    return [row[0] for row in db.execute('SELECT name FROM ' + namespace
            + ".sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def same_records(db, table, exclude_restored=False):
    columns = ','.join(quote(row[1]) + ' COLLATE BINARY'
                       for row in db.execute('PRAGMA main.table_info(' + quote(table) + ')'))
    where = " WHERE inst_id<>'gqxzwemm'" if exclude_restored else ''
    # GROUP BY + COUNT compares multisets, including duplicated opaque records.
    selects = ['SELECT ' + columns + ',COUNT(*) FROM ' + ns + '.' + quote(table)
               + where + ' GROUP BY ' + columns for ns in ('main', 'prior')]
    for left, right in (selects, selects[::-1]):
        require(db.execute('SELECT COUNT(*) FROM (' + left + ' EXCEPT ' + right + ')').fetchone()[0] == 0,
                'Record set changed outside the permitted institution delta: ' + table)


def compare_snapshot(db, allow_insert):
    names = tables(db, 'main')
    require(names == tables(db, 'prior'), 'Database tables changed since online backup')
    definitions = "SELECT type,name,tbl_name,sql FROM {ns}.sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
    require(db.execute(definitions.format(ns='main')).fetchall()
            == db.execute(definitions.format(ns='prior')).fetchall(), 'Database schema changed since online backup')
    for name in names:
        same_records(db, name, exclude_restored=allow_insert and name == 'inst')
    if allow_insert:
        require(db.execute('SELECT COUNT(*) FROM main.inst').fetchone()[0]
                == db.execute('SELECT COUNT(*) FROM prior.inst').fetchone()[0] + 1,
                'Institution delta is not exactly one row')
    return len(names)


def online_backup(target, destination):
    require(hasattr(sqlite3.Connection, 'backup'), 'Use Python 3.11: online SQLite backup support is required')
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.parent.chmod(0o700)
    fd = os.open(str(destination), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    with readonly(target) as source, contextlib.closing(sqlite3.connect(str(destination))) as backup:
        source.backup(backup)
    destination.chmod(0o600)
    with readonly(destination) as backup:
        require(backup.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'Backup integrity check failed')
    return {'path': str(destination), 'sha256': sha256(destination), 'mode': oct(destination.stat().st_mode & 0o777)}


def restore(target, source, backup_path, record, _after_backup=None):
    metadata = authoritative(source)
    with readonly(target) as initial:
        expected_action = preflight(initial, metadata)
    record.update(authoritativeInstitution=dict(zip(FIELDS, metadata)), plannedAction=expected_action)
    record['backup'] = online_backup(target, backup_path)
    if _after_backup:
        _after_backup()
    db = sqlite3.connect(target.resolve().as_uri() + '?mode=rw', uri=True,
                         isolation_level=None, timeout=5)
    try:
        db.execute('BEGIN IMMEDIATE')
        db.execute('ATTACH DATABASE ? AS prior', (backup_path.resolve().as_uri() + '?mode=ro',))
        require(authoritative(source) == metadata, 'Authoritative institution changed after preflight')
        require(preflight(db, metadata) == expected_action, 'Target institution changed after preflight')
        compare_snapshot(db, False)
        if expected_action == 'insert':
            def only_institution_insert(action, table, column, database, trigger):
                if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
                    allowed = database == 'main' and ((action == sqlite3.SQLITE_INSERT and table == 'inst')
                                                      or table == 'sqlite_sequence')
                    return sqlite3.SQLITE_OK if allowed else sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            db.set_authorizer(only_institution_insert)
            db.execute('INSERT INTO inst (inst_id,name,is_deleted,gmt_create,gmt_modified) VALUES (?,?,?,?,?)', metadata)
            require(db.execute('SELECT ' + ','.join(FIELDS) + ' FROM inst WHERE inst_id=?', (INST_ID,)).fetchall()
                    == [metadata], 'Inserted metadata differs from authoritative record')
        record['comparedBusinessTables'] = compare_snapshot(db, expected_action == 'insert')
        db.execute('COMMIT')
        record.update(committed=True, action=expected_action)
        db.set_authorizer(None)
        db.execute('BEGIN')
        compare_snapshot(db, expected_action == 'insert')
        record['localRowId'] = db.execute('SELECT id FROM inst WHERE inst_id=?', (INST_ID,)).fetchone()[0]
        db.execute('ROLLBACK')
        record.update(otherInstitutionRecordsUnchanged=True, nodeAndRouteRecordsUnchanged=True,
                      allOtherBusinessRecordSetsUnchanged=True)
    except Exception:
        if db.in_transaction:
            db.execute('ROLLBACK')
        raise
    finally:
        db.close()


def api(port, path, body=None):
    request = urllib.request.Request('http://192.168.45.101:' + str(port) + '/api/v1alpha1' + path,
              data=None if body is None else json.dumps(body).encode(),
              headers={'Content-Type': 'application/json'}, method='GET' if body is None else 'POST')
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    require(payload.get('status', {}).get('code') == 0, 'Read-only API failed: ' + path)
    return payload.get('data')


def user_context():
    data = api(18103, '/user/get', {})
    return {key: data.get(key) for key in ('ownerId', 'ownerType', 'platformType', 'platformNodeId', 'deployMode')}


def self_test():
    definition = '''CREATE TABLE inst(id INTEGER PRIMARY KEY AUTOINCREMENT,inst_id varchar(64) NOT NULL,
        name varchar(256) DEFAULT NULL,is_deleted tinyint(1) NOT NULL DEFAULT '0',
        gmt_create datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,gmt_modified datetime NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE UNIQUE INDEX upk_inst_id ON inst(inst_id);
        CREATE INDEX key_inst_name ON inst(name);
        CREATE TABLE node(node_id TEXT,inst_id TEXT,is_deleted INTEGER);
        CREATE TABLE node_route(route_id TEXT,src_node_id TEXT,dst_node_id TEXT);
        CREATE TABLE opaque(payload BLOB);'''
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        target, source = root / 'alice.sqlite', root / 'kimi.sqlite'
        metadata = (INST_ID, INST_NAME, 0, '2026-07-18 03:11:03', '2026-07-18 03:11:03')
        for path, own in ((target, (OWN_INST, 'alice')), (source, (INST_ID, INST_NAME))):
            with sqlite3.connect(str(path)) as db:
                db.execute('PRAGMA journal_mode=WAL')
                db.executescript(definition)
                db.execute('INSERT INTO inst(inst_id,name,is_deleted,gmt_create,gmt_modified) VALUES(?,?,?,?,?)',
                           metadata if path == source else (own[0], own[1], 0, metadata[3], metadata[4]))
                db.executemany('INSERT INTO node VALUES(?,?,0)', [('kimi', INST_ID), ('alice', OWN_INST)])
                db.executemany('INSERT INTO node_route VALUES(?,?,?)', [('r_kimi_alice', 'kimi', 'alice'), ('r_alice_kimi', 'alice', 'kimi')])
                db.executemany('INSERT INTO opaque VALUES(?)', [(b'a',), (b'a',), (b'b',)])
        record = {}
        restore(target, source, root / 'first.sqlite', record)
        require(record['action'] == 'insert' and record['allOtherBusinessRecordSetsUnchanged'], 'Insert self-test failed')
        second = {}
        restore(target, source, root / 'second.sqlite', second)
        require(second['action'] == 'noop', 'Repeat self-test failed')
        with sqlite3.connect(str(target)) as db:
            db.execute('DELETE FROM inst WHERE inst_id=?', (INST_ID,))
        def concurrent_change():
            with sqlite3.connect(str(target)) as db:
                db.execute('INSERT INTO opaque VALUES(?)', (b'concurrent',))
        try:
            restore(target, source, root / 'concurrent.sqlite', {}, concurrent_change)
        except RuntimeError:
            with readonly(target) as db:
                require(not db.execute('SELECT 1 FROM inst WHERE inst_id=?', (INST_ID,)).fetchall(), 'Conflict inserted a row')
        else:
            raise RuntimeError('Concurrent record change was not rejected')
        for conflict in [(INST_ID, 'different', 0), (INST_ID, INST_NAME, 1), ('different-id', INST_NAME, 0)]:
            with sqlite3.connect(str(target)) as db:
                db.execute('INSERT INTO inst(inst_id,name,is_deleted) VALUES(?,?,?)', conflict)
            try:
                with readonly(target) as db:
                    preflight(db, metadata)
            except RuntimeError:
                pass
            else:
                raise RuntimeError('Conflicting/soft-deleted identity was not rejected')
            with sqlite3.connect(str(target)) as db:
                db.execute('DELETE FROM inst WHERE inst_id=?', (conflict[0],))
        print(json.dumps({'selfTest': 'passed', 'cases': ['insert', 'repeat-noop', 'concurrent-change-rollback',
                         'different-metadata-rejection', 'soft-delete-rejection', 'same-name-other-id-rejection']}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='perform reviewed insert-only recovery')
    parser.add_argument('--self-test', action='store_true', help='test temporary fixtures only')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    metadata = authoritative(KIMI)
    with readonly(ALICE) as db:
        action = preflight(db, metadata)
    context = user_context()
    require(context['ownerId'] == OWN_INST and context['platformNodeId'] == 'alice'
            and context['platformType'] == 'AUTONOMY', 'Alice user context differs from reviewed context')
    require(api(38103, '/inst/get', {'instId': INST_ID}) == {'instId': INST_ID, 'instName': INST_NAME, 'localNodeId': None},
            'Kimi authoritative API metadata differs')
    if not args.apply:
        print(json.dumps({'readOnlyPreflight': True, 'plannedAction': action,
                          'authoritativeInstitution': dict(zip(FIELDS, metadata)), 'aliceUserContext': context}, indent=2))
        return
    require(os.geteuid() == 0, 'Apply must run as root on the office host')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = Path('/var/backups/ppci/office-recovery-20261102/alice-peer-institution') / (stamp + '.sqlite')
    evidence = Path('/var/log/ppci/regression-20261102') / ('native-alice-peer-institution-restore-' + stamp + '.json')
    record = {'startedAt': stamp, 'success': False, 'committed': False,
              'target': str(ALICE), 'source': str(KIMI), 'aliceUserContextBefore': context}
    try:
        protocol = api(18103, '/config/protocol')
        restore(ALICE, KIMI, backup, record)
        record['aliceUserContextAfter'] = user_context()
        require(record['aliceUserContextAfter'] == context, 'Alice user context changed')
        require(api(18103, '/config/protocol') == protocol, 'Active protocol configuration changed')
        page = api(18103, '/nodeRoute/page', {'page': 1, 'size': 10, 'search': '', 'ownerId': 'alice', 'sort': {}})
        require(page.get('total') == 1 and len(page.get('list', [])) == 1, 'Native Alice page does not contain exactly one route')
        route = page['list'][0]
        require(route.get('srcNodeId') == 'kimi' and route.get('dstNodeId') == 'alice', 'Unexpected native page route')
        record.update(success=True, protocolUnchanged=True, activeProtocol=protocol.get('activeProtocol'),
                      nativePage={'total': page['total'], 'route': {key: route.get(key) for key in ('routeId', 'srcNodeId', 'dstNodeId', 'status')}})
    except Exception as error:
        record['error'] = str(error)
        raise
    finally:
        evidence.parent.mkdir(parents=True, exist_ok=True)
        with evidence.open('x') as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        print(json.dumps({'evidence': str(evidence), **record}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
