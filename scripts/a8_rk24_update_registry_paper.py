#!/usr/bin/env python3
"""Repair the RK24 registry column alignment and append the verified paper record."""
from pathlib import Path
import hashlib
import json

REPO = Path('/home/codonflow-a8-rk')
REGISTRY = REPO / 'experiments/REGISTRY.md'
REPORT = REPO / 'audits/20261121/RK24/paper/rk24_registry_update_v1.json'
EXPECTED_BEFORE = 'fc751e15c64a238414a7540fb390c63da26ebfbb36f89b25bedec823ae539865'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    source = REGISTRY.read_bytes()
    before = digest(source)
    if before != EXPECTED_BEFORE:
        raise SystemExit(f'unexpected registry state: {before}')
    text = source.decode()
    if 'CF-A8-RK24-PAPER' in text:
        raise SystemExit('RK24-PAPER row already exists')
    lines = text.splitlines()
    repaired = 0
    for index, line in enumerate(lines):
        if line.startswith('| CF-A8-RK24 |'):
            parts = [part.strip() for part in line.strip().strip('|').split('|')]
            if len(parts) != 10:
                raise SystemExit(f'unexpected RK24 science row column count: {len(parts)}')
            if not parts[6].startswith('61 train-only single-codon slopes'):
                raise SystemExit('unexpected RK24 science row alignment')
            commits = '`cb0aa0957c1f62afbd37cf1cdc5aaf3d94c24ebd`; `b4c04d2935015386603a5dff8b1f8c9247295b5a`; `a35097243e9b0f2b71786479bd981488ac3ed526`; `cd25fe57a4a5aadba49e278e78b49d3bb1ab5603`'
            parts.insert(6, commits)
            lines[index] = '| ' + ' | '.join(parts) + ' |'
            repaired += 1
    if repaired != 1:
        raise SystemExit(f'expected one RK24 science row, repaired={repaired}')
    paper_parts = [
        'CF-A8-RK24-PAPER',
        '2026-11-21',
        'Boël author-model working-manuscript increment',
        '`a8_rk24_update_paper.py`; `a8_rk24_verify_paper.py`; English section workflow',
        'existing manuscript and frozen science; no new functional evaluation',
        'before SHA256=`168042d268da301057d9214393c25c05904c6a64d60bbb88ff265fc2cf8755b6`; after SHA256=`12949c09f3b4707c87bfdd4486d1ad761762a81264d1b9da6a5df9fbef4d6643`; section SHA256=`f23926a336ecc1502e622e228a3cbf7b04577cb757c63e5695afb69a1505a2bd`',
        'RK24 science `a3509724`; paper closeout follow-up',
        'draft/section/no-citation/Markdown-only workflow; exact two integrations; sixteen evidence rows',
        '699 words; prepare/write pass; status PASS with Lark skipped; missing-dependency and deliver shell failures retained; independent integration 58/58',
        'Section 6.35 plus sixteen evidence rows; limited-scope author baseline supported; References preserved; no Feishu delivery claimed; non-submittable',
        'done_58_of_58_non_submittable',
    ]
    lines.append('| ' + ' | '.join(paper_parts) + ' |')
    updated = ('\n'.join(lines) + '\n').encode()
    REGISTRY.write_bytes(updated)
    science_counts = []
    for line in lines:
        if line.startswith('| CF-A8-RK24'):
            science_counts.append((line.split('|')[1].strip(), len(line.strip().strip('|').split('|'))))
    report = {
        'schema': 'a8-rk24-registry-paper-update-v1',
        'status': 'PASS',
        'before_sha256': before,
        'after_sha256': digest(updated),
        'rk24_science_rows_repaired': repaired,
        'rk24_row_column_counts': science_counts,
        'paper_row_appended': True,
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
