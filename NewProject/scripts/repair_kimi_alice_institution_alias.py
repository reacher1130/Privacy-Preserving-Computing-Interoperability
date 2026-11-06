#!/usr/bin/env python3
"""Repair Kimi's one stale Alice node-to-institution link; preflight is read-only."""

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from restore_alice_peer_institution import (
    ALICE, KIMI, FIELDS, api, compare_snapshot, online_backup, quote, readonly,
    require, same_records, schema, tables,
)

CANONICAL = 'rqzvglmu'
LEGACY = 'owszmazx'
KIMI_INST = 'gqxzwemm'
PROJECT = 'wckkekky'
INST_COLUMNS = ','.join(FIELDS)
LEGACY_COLUMNS = {
    'inst.inst_id', 'node.inst_id', 'vote_invite.initiator', 'vote_request.initiator',
    'vote_request.msg', 'vote_request.vote_counter', 'vote_request.party_vote_info',
}


def source_row(path):
    with readonly(path) as db:
        schema(db)
        rows = db.execute(f'SELECT {INST_COLUMNS} FROM inst WHERE inst_id=?', (CANONICAL,)).fetchall()
        require(len(rows) == 1 and rows[0][:3] == (CANONICAL, 'alice', 0), 'Alice authority changed')
        for stamp in rows[0][3:]:
            datetime.datetime.strptime(stamp, '%Y-%m-%d %H:%M:%S')
        require(db.execute("SELECT inst_id,master_node_id,is_deleted FROM node WHERE node_id='alice'").fetchall()
                == [(CANONICAL, 'alice', 0)], 'Alice authority node reference changed')
        return rows[0]


def preflight(db, metadata):
    schema(db)
    require(not db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name='node'").fetchall(),
            'Unexpected node trigger')
    nodes = db.execute("SELECT node_id,inst_id,master_node_id,is_deleted FROM node WHERE node_id IN ('alice','kimi') ORDER BY node_id").fetchall()
    require(len(nodes) == 2 and nodes[1] == ('kimi', KIMI_INST, 'kimi', 0), 'Kimi node reference changed')
    require(nodes[0] in [('alice', LEGACY, 'alice', 0), ('alice', CANONICAL, 'alice', 0)],
            'Kimi peer node does not match the reviewed identity')
    require(db.execute('SELECT node_id,inst_id FROM node WHERE inst_id IN (?,?) AND is_deleted=0',
                       (LEGACY, CANONICAL)).fetchall() == [('alice', nodes[0][1])],
            'Another active node uses an Alice institution identity')
    alias = db.execute('SELECT inst_id,name,is_deleted FROM inst WHERE inst_id=?', (LEGACY,)).fetchall()
    require(alias == [(LEGACY, 'alice', 0)], 'Historical Alice alias changed')
    canonical = db.execute(f'SELECT {INST_COLUMNS} FROM inst WHERE inst_id=?', (CANONICAL,)).fetchall()
    expected_names = sorted([LEGACY] + ([CANONICAL] if canonical else []))
    require([r[0] for r in db.execute("SELECT inst_id FROM inst WHERE lower(name)='alice' ORDER BY inst_id")] == expected_names,
            'Unexpected same-name institution')
    require(db.execute("SELECT route_id,src_node_id,dst_node_id FROM node_route WHERE is_deleted=0 AND route_id IN ('alice__kimi','kimi__alice') ORDER BY route_id").fetchall()
            == [('alice__kimi', 'alice', 'kimi'), ('kimi__alice', 'kimi', 'alice')], 'Native routes changed')
    if canonical:
        require(canonical == [metadata] and nodes[0][1] == CANONICAL, 'Conflicting or incomplete prior repair')
        return 'noop'
    require(nodes[0][1] == LEGACY, 'Canonical node points to a missing institution')
    require(db.execute('SELECT action FROM vote_invite WHERE initiator=? AND is_deleted=0', (LEGACY,)).fetchall()
            == [('APPROVED',)], 'Legacy invite is not the reviewed terminal vote')
    require(db.execute('SELECT status FROM vote_request WHERE initiator=? AND is_deleted=0', (LEGACY,)).fetchall()
            == [(1,)], 'Legacy request is not the reviewed terminal vote')
    require_pending_project(db)
    for table in tables(db, 'main'):
        for col in db.execute('PRAGMA table_info(' + quote(table) + ')'):
            name = col[1]
            if table + '.' + name in LEGACY_COLUMNS or re.search(r'pass|token|credential|secret|signature|cert|private|salt', name, re.I):
                continue
            found = db.execute(f'SELECT 1 FROM {quote(table)} WHERE typeof({quote(name)})=\'text\' AND instr({quote(name)},?)>0 LIMIT 1', (LEGACY,)).fetchone()
            require(found is None, 'Unreviewed legacy reference: ' + table + '.' + name)
    return 'insert-and-relink'


def require_pending_project(db):
    vote = db.execute('''SELECT c.type,c.initiator,v.vote_participant_id,v.type,v.action,p.status
        FROM project_approval_config c JOIN vote_invite v ON v.vote_id=c.vote_id
        JOIN project p ON p.project_id=c.project_id
        WHERE c.project_id=? AND c.is_deleted=0 AND v.is_deleted=0 AND p.is_deleted=0''', (PROJECT,)).fetchall()
    require(vote == [('PROJECT_CREATE', CANONICAL, KIMI_INST, 'PROJECT_CREATE', 'REVIEWING', 0)],
            'Exact native project vote is not pending with the reviewed participants')


def verify_delta(db, metadata):
    names = tables(db, 'main')
    require(names == tables(db, 'prior'), 'Table list changed')
    for name in names:
        if name not in ('inst', 'node'):
            same_records(db, name)
    require(db.execute('SELECT * FROM main.inst WHERE inst_id<>? ORDER BY id', (CANONICAL,)).fetchall()
            == db.execute('SELECT * FROM prior.inst ORDER BY id').fetchall(), 'Existing institution rows changed')
    require(db.execute(f'SELECT {INST_COLUMNS} FROM main.inst WHERE inst_id=?', (CANONICAL,)).fetchall()
            == [metadata], 'Canonical institution differs from source')
    node_columns = [r[1] for r in db.execute('PRAGMA main.table_info(node)')]
    original = ','.join(quote(c) for c in node_columns)
    adjusted = ','.join("CASE WHEN node_id='alice' THEN '" + CANONICAL + "' ELSE inst_id END"
                        if c == 'inst_id' else quote(c) for c in node_columns)
    require(db.execute('SELECT COUNT(*) FROM main.node').fetchone() == db.execute('SELECT COUNT(*) FROM prior.node').fetchone(),
            'Node count changed')
    for left, right in [(f'SELECT {original} FROM main.node', f'SELECT {adjusted} FROM prior.node'),
                        (f'SELECT {adjusted} FROM prior.node', f'SELECT {original} FROM main.node')]:
        require(db.execute('SELECT COUNT(*) FROM (' + left + ' EXCEPT ' + right + ')').fetchone() == (0,),
                'A node changed outside the one permitted institution field')
    require_pending_project(db)
    return len(names)


def repair(source, target, backup_path):
    metadata = source_row(source)
    with readonly(target) as db:
        if preflight(db, metadata) == 'noop':
            return {'action': 'noop'}
    backup = online_backup(target, backup_path)
    db = sqlite3.connect(target.resolve().as_uri() + '?mode=rw', uri=True, isolation_level=None, timeout=5)
    try:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        db.execute('ATTACH DATABASE ? AS prior', (backup_path.resolve().as_uri() + '?mode=ro',))
        require(source_row(source) == metadata and preflight(db, metadata) == 'insert-and-relink', 'Preflight changed')
        compare_snapshot(db, False)

        def only_expected_writes(action, table, column, namespace, trigger):
            if action not in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
                return sqlite3.SQLITE_OK
            permitted = namespace == 'main' and not trigger and (
                action == sqlite3.SQLITE_INSERT and table == 'inst'
                or action == sqlite3.SQLITE_UPDATE and table == 'node' and column == 'inst_id'
                or table == 'sqlite_sequence')
            return sqlite3.SQLITE_OK if permitted else sqlite3.SQLITE_DENY

        db.set_authorizer(only_expected_writes)
        db.execute(f'INSERT INTO inst ({INST_COLUMNS}) VALUES (?,?,?,?,?)', metadata)
        changed = db.execute("UPDATE node SET inst_id=? WHERE node_id='alice' AND master_node_id='alice' AND inst_id=? AND is_deleted=0",
                             (CANONICAL, LEGACY)).rowcount
        require(changed == 1, 'Node compare-and-swap did not update exactly one row')
        compared = verify_delta(db, metadata)
        db.execute('COMMIT')
        return {'action': 'insert-and-relink', 'backup': backup, 'comparedBusinessTables': compared,
                'historicalAliasPreserved': True, 'otherRecordsUnchanged': True, 'projectVoteStillPending': True}
    finally:
        if db.in_transaction:
            db.execute('ROLLBACK')
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='apply the reviewed repair after backup and rechecks')
    args = parser.parse_args()
    metadata = source_row(ALICE)
    with readonly(KIMI) as db:
        action = preflight(db, metadata)
    alice_inst = api(18103, '/inst/get', {'instId': CANONICAL})
    require((alice_inst.get('instId'), alice_inst.get('instName')) == (CANONICAL, 'alice'), 'Alice API authority changed')
    kimi_context = api(38103, '/user/get', {})
    require(kimi_context.get('ownerId') == KIMI_INST and kimi_context.get('platformNodeId') == 'kimi', 'Kimi API identity changed')
    result = {'target': str(KIMI), 'source': str(ALICE), 'projectId': PROJECT,
              'plannedAction': action, 'sourceInstitution': dict(zip(FIELDS, metadata))}
    if args.apply and action != 'noop':
        require(os.geteuid() == 0, 'Apply must run on the office host as root')
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup = Path('/var/backups/ppci/native-kimi-alice-institution') / (stamp + '.sqlite')
        result.update(repair(ALICE, KIMI, backup))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
