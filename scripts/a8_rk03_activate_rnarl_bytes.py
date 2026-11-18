#!/usr/bin/env python3
"""Activate previously verified RNARL exact byte counts without new network I/O."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

REPO = Path('/home/codonflow-a8-rk')
CONFIG = REPO / 'configs/a8_rk03_sources.json'
REPORT = REPO / 'audits/20261118/RK03/rnarl_official_file_sizes.json'
AUDIT = REPO / 'audits/20261118/RK03/rnarl_expected_bytes_activation.json'


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    if AUDIT.exists():
        raise RuntimeError(f'refusing to overwrite existing audit: {AUDIT}')
    before = sha256(CONFIG)
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    evidence = json.loads(REPORT.read_text(encoding='utf-8'))
    source = next(item for item in config['sources'] if item['source_id'] == 'rnarl_v1')
    records = evidence['files']
    if len(source['files']) != 21 or len(records) != 21:
        raise RuntimeError('expected exactly 21 RNARL config and report files')
    by_id = {item['file_id']: item for item in records}
    if len(by_id) != 21:
        raise RuntimeError('duplicate file_id in byte evidence')
    changes = []
    for spec in source['files']:
        record = by_id[spec['file_id']]
        if record['filename'] != spec['filename'] or record['download_url'] != spec['download_url']:
            raise RuntimeError(f"source identity mismatch: {spec['file_id']}")
        if record['expected_md5'].lower() != spec['expected_md5'].lower():
            raise RuntimeError(f"MD5 identity mismatch: {spec['file_id']}")
        size = int(record['expected_bytes'])
        if size <= 0 or record.get('byte_source') not in {
            'official_head_content_length', 'verified_local_final_md5_matched'
        }:
            raise RuntimeError(f"invalid byte evidence: {spec['file_id']}")
        previous = spec.get('expected_bytes')
        if previous is not None and int(previous) != size:
            raise RuntimeError(f"conflicting existing expected_bytes: {spec['file_id']}")
        spec['expected_bytes'] = size
        changes.append({'file_id': spec['file_id'], 'expected_bytes': size,
                        'previous_expected_bytes': previous, 'byte_source': record['byte_source']})
    part = CONFIG.with_name(CONFIG.name + f'.part.{os.getpid()}')
    part.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(part, CONFIG)
    after = sha256(CONFIG)
    audit = {
        'schema_version': 'a8-rk03-rnarl-byte-activation-v1',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'status': 'PASS',
        'network_io_performed': False,
        'source_report': str(REPORT),
        'source_report_sha256': sha256(REPORT),
        'config_sha256_before': before,
        'config_sha256_after': after,
        'changed_file_count': sum(item['previous_expected_bytes'] is None for item in changes),
        'files': changes,
        'note': 'Exact byte counts were previously obtained from verified local MD5-matched finals or official HEAD HTTP 200 Content-Length; activation lets resumable downloads promote complete parts and detect truncation.',
    }
    part = AUDIT.with_name(AUDIT.name + f'.part.{os.getpid()}')
    part.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(part, AUDIT)
    print(json.dumps({'status': 'PASS', 'changed_file_count': audit['changed_file_count'],
                      'config_sha256_before': before, 'config_sha256_after': after}, sort_keys=True))


if __name__ == '__main__':
    main()
