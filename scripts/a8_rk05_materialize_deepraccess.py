#!/usr/bin/env python3
"""Materialize the fixed DeepRaccess source and pretrained weights for ID3."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
from datetime import datetime, timezone
import zipfile

ZIP = Path('/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/sources/deepraccess_1a37235_fixed.zip')
ZIP_SHA256 = 'dfcdaefe51af5a02a7a62d7a5263a261984156d4365fed86f007dbe408bf7348'
COMMIT = '1a37235e31e1d5a7d5e2bfb705e3a00f1cdcaa9c'
TOP = f'DeepRaccess-{COMMIT}'
TARGET = Path('/home/codonflow-a8-rk-external/ID3/DeepRaccess')
WEIGHT_ROOT = Path('/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/weights/deepraccess_1a37235')
AUDIT = Path('/home/codonflow-a8-rk/audits/20261118/RK05/deepraccess_materialization.json')
EXPECTED_WEIGHTS = {
    'path/FCN_structured.pth': (38009969, '136be4db9403aaf366eb6bb9790a8f099de22bd0048be02a5a4754c36ce664d2'),
    'path/FCN_uniform.pth': (38009969, 'c05768108cb50d9de9606f2a79825e65f6fe4461163355e77827993dfc24bad6'),
    'path/utils_bertrna.pth': (2068430, 'dea038651f3485688a8d18d69d8db7436a64a432dbe1b8c56588aa4976535fe5'),
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    if TARGET.exists():
        raise FileExistsError(f'refusing to overwrite existing target: {TARGET}')
    if AUDIT.exists():
        raise FileExistsError(f'refusing to overwrite existing audit: {AUDIT}')
    if ZIP.stat().st_size != 97607020 or sha256(ZIP) != ZIP_SHA256:
        raise RuntimeError('DeepRaccess ZIP byte identity mismatch')
    with zipfile.ZipFile(ZIP) as archive:
        if len(archive.infolist()) != 33 or archive.testzip() is not None:
            raise RuntimeError('DeepRaccess ZIP entry-count or CRC mismatch')
        for info in archive.infolist():
            path = PurePosixPath(info.filename)
            if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != TOP:
                raise RuntimeError(f'unsafe or unexpected ZIP member: {info.filename}')
            if stat.S_ISLNK(info.external_attr >> 16):
                raise RuntimeError(f'symlink refused: {info.filename}')
        staging = TARGET.parent / f'.DeepRaccess.materialize.{os.getpid()}'
        staging.mkdir(parents=True, exist_ok=False)
        try:
            archive.extractall(staging)
            extracted = staging / TOP
            files = {}
            for path in sorted(extracted.rglob('*')):
                if path.is_file():
                    files[str(path.relative_to(extracted))] = {
                        'bytes': path.stat().st_size, 'sha256': sha256(path)}
            for relative, (size, digest) in EXPECTED_WEIGHTS.items():
                actual = files.get(relative)
                if actual is None or actual['bytes'] != size or actual['sha256'] != digest:
                    raise RuntimeError(f'pretrained weight mismatch: {relative}')
            for required in ('mymodel.py', 'README.md', 'requirements.txt', 'predict.py'):
                if required not in files:
                    raise FileNotFoundError(f'missing fixed source file: {required}')
            weight_storage = {}
            for relative, (size, digest) in EXPECTED_WEIGHTS.items():
                source_weight = extracted / relative
                stored_weight = WEIGHT_ROOT / relative
                stored_weight.parent.mkdir(parents=True, exist_ok=True)
                if stored_weight.exists():
                    if stored_weight.stat().st_size != size or sha256(stored_weight) != digest:
                        raise RuntimeError(f'conflicting existing stored weight: {stored_weight}')
                else:
                    temporary_weight = stored_weight.with_name(stored_weight.name + f'.part.{os.getpid()}')
                    shutil.copy2(source_weight, temporary_weight)
                    if temporary_weight.stat().st_size != size or sha256(temporary_weight) != digest:
                        raise RuntimeError(f'stored weight copy mismatch: {relative}')
                    os.replace(temporary_weight, stored_weight)
                source_weight.unlink()
                source_weight.symlink_to(stored_weight)
                weight_storage[relative] = str(stored_weight)
            os.replace(extracted, TARGET)
        except Exception:
            # Keep any failed staging directory for diagnosis; never promote it as valid.
            raise
    audit = {
        'schema_version': 'a8-rk05-deepraccess-materialization-v1',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'status': 'PASS_FIXED_SOURCE_AND_WEIGHT_MATERIALIZATION',
        'source': {
            'repository': 'https://github.com/hmdlab/DeepRaccess',
            'commit': COMMIT,
            'zip': str(ZIP), 'zip_bytes': ZIP.stat().st_size, 'zip_sha256': ZIP_SHA256,
            'zip_entries': 33, 'zip_crc_bad_member': None,
            'target': str(TARGET), 'file_count': len(files), 'files': files,
        },
        'pretrained_weights': {relative: files[relative] for relative in EXPECTED_WEIGHTS},
        'weight_storage_root': str(WEIGHT_ROOT),
        'weight_storage': weight_storage,
        'science_flags': {
            'fixed_source_materialized': True,
            'structured_pretrained_weight_verified': True,
            'model_forward_executed': False,
            'id3_quick_test_executed': False,
            'performance_or_sota_claim': False,
        },
    }
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    part = AUDIT.with_name(AUDIT.name + f'.part.{os.getpid()}')
    part.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    os.replace(part, AUDIT)
    print(json.dumps({'status': audit['status'], 'target': str(TARGET), 'file_count': len(files),
                      'structured_weight_sha256': EXPECTED_WEIGHTS['path/FCN_structured.pth'][1]}, sort_keys=True))


if __name__ == '__main__':
    main()
