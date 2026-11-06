#!/usr/bin/env python3
"""Initialize the two owned local demo nodes' partner directories through platform APIs."""
import json
from pathlib import Path
import time
import urllib.request


def call(port, path, body=None):
    request = urllib.request.Request(f'http://127.0.0.1:{port}/api/v1bfia/node/' + path,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
    result = json.load(urllib.request.urlopen(request, timeout=15))
    if result.get('status', {}).get('code') != 0:
        raise RuntimeError(str(result))
    return result['data']


def main():
    peers = {'alice': (18080, 'bob'), 'bob': (28090, 'alice')}
    listing = 'list/apply?page_num=1&page_size=100'

    def approved(port, peer):
        return any(node.get('nodeId') == peer for node in call(port, 'list/approved'))

    report = {owner: {'peer': peer, 'status': 'existing'}
              for owner, (port, peer) in peers.items() if approved(port, peer)}
    if len(report) < len(peers):
        for owner, (port, peer) in peers.items():
            if any(record.get('nodeId') == peer for record in call(port, listing)['records']):
                raise RuntimeError('Existing cooperation record needs review; it will not be overwritten: ' + owner)
            if not any(node.get('nodeId') == peer for node in call(port, 'list/configured')):
                raise RuntimeError('Signed BFIA cooperation is not configured: ' + owner)
        expires_at = int(time.time()) + 30 * 86400
        if call(18080, 'contract/apply', {'node_id': 'bob', 'expired_time': expires_at}) is not True:
            raise RuntimeError('Bob did not acknowledge the cooperation request')
        alice_ids = {r['contractId'] for r in call(18080, listing)['records']
                     if r.get('nodeId') == 'bob' and r.get('status') == 'UNAPPROVED'}
        incoming = [r for r in call(28090, listing)['records']
                    if r['contractId'] in alice_ids and r.get('nodeId') == 'alice'
                    and r.get('canConfirm') is True]
        if len(incoming) != 1:
            raise RuntimeError('Cannot identify the same pending contract on Alice and Bob')
        contract = incoming[0]['contractId']
        if call(28090, 'contract/confirm', {'contract_id': contract, 'status': 'APPROVED'}) is not True:
            raise RuntimeError('Alice did not acknowledge the Bob approval')
        for owner, (port, peer) in peers.items():
            if not approved(port, peer):
                raise RuntimeError('Confirmed partner missing from directory: ' + owner)
            report[owner] = {'peer': peer, 'contract': contract, 'expires_at': expires_at, 'status': 'initialized'}
    out = Path('/var/log/ppci/acceptance-platform-20260912/bfia-partners.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
