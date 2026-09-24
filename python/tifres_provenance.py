"""Content identities stored beside run recovery metadata, never inside FITS files."""
import hashlib
import json
import os
from pathlib import Path
from tifres_dependencies import contract, parameters, raw_matches, under, STEPS


def identity(path):
    path = Path(path)
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): digest.update(block)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f'File changed during inspection: {path}')
    return {'sha256': digest.hexdigest(), 'size': after.st_size}


def snapshot(step, row, opts, raw, output, scripts, fingerprint=identity):
    plan = contract(step, row, opts)
    paths = [under(scripts if i.root == 'scripts' else output, i.path) for i in plan.inputs]
    if step == STEPS[0]:
        matches = raw_matches(row, raw)
        if not matches: raise FileNotFoundError(f'No raw inputs for DSNO {row["DSNO"]}: {row.get("ORIGIN")}')
        paths.extend(matches)
    return {'dsno': str(int(row['DSNO'])), 'step': step,
            'parameters': parameters(step, row, opts),
            'source': fingerprint(Path(scripts) / (step + '.py')),
            'inputs': {str(p.resolve()): fingerprint(p) for p in paths}}


def save_records(stage, records, plans):
    """Called only after verified products publish; recovery Completed is also required."""
    for record, plan in zip(records, plans):
        record['outputs'] = {str(p): identity(Path(stage) / p) for p in plan.products}
    path = Path(stage) / 'provenance.json'
    temp = path.with_suffix('.json.tmp')
    with temp.open('w', encoding='utf-8') as stream:
        json.dump({'version': 1, 'records': records}, stream, indent=2)
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, path)
