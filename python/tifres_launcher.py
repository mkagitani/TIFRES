"""Noninteractive boundary around unchanged TIFRES legacy functions (Python 3.10+).

All numerical work is delegated to the original named function. Products are
staged so a failure/Stop cannot corrupt a pre-existing product. See docs/step3.md.
"""
import argparse
import ast
import builtins
import contextlib
import csv
import importlib.util
import inspect
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import types
import uuid
from tifres_publication import Publication, CancelledError
from tifres_dependencies import relative, under, contract, raw_matches
from tifres_provenance import snapshot, save_records

STEPS = ('mkSpFrames4f', 'mkFibFit4c', 'mkFibSpec4d', 'mkWavMap4d', 'mkWcalSpec4d')
PACKAGES = ('numpy', 'scipy', 'pandas', 'matplotlib', 'astropy')
PATH_FIELDS = ('FILENAME', 'ORIGIN', 'DARKFRAME', 'WLFLAT', 'WLFLAT2', 'SKYFLAT', 'WAVMAP')
METADATA = ('CCDTEMP', 'EXPTIME', 'EXPSTART', 'EXPSTOP', 'NFILES', 'EXPMID', 'FMSTD')


def dsnos(values):
    tokens = [s for value in values for s in re.split(r'[,\s]+', value.strip()) if s]
    if not tokens or any(not re.fullmatch(r'[0-9]+', s) for s in tokens):
        raise ValueError('DSNO must be one or more decimal integer identifiers.')
    result = [int(s) for s in tokens]  # never parse identifiers through float
    if len(set(result)) != len(result):
        raise ValueError('Duplicate DSNO arguments.')
    return result


def defaults(script_dir, step):
    tree = ast.parse((Path(script_dir) / (step + '.py')).read_text(encoding='utf-8-sig'))
    function = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == step), None)
    if function is None or not function.args.args or function.args.args[0].arg != 'dsno':
        raise ValueError(f'Missing callable {step}(dsno, ...).')
    return {a.arg: ast.literal_eval(v) for a, v in zip(function.args.args[-len(function.args.defaults):], function.args.defaults)}


def options(script_dir, step, text, overwrite):
    original = defaults(script_dir, step)
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError(f'Duplicate option: {key}')
            result[key] = value
        return result
    supplied = json.loads(text, object_pairs_hook=unique_pairs)
    if not isinstance(supplied, dict): raise ValueError('Options must be a JSON object.')
    for key, value in supplied.items():
        if key not in original: raise ValueError(f'Unknown option: {key}')
        if type(value) is not type(original[key]): raise ValueError(f'Invalid type for {key}.')
        if isinstance(value, float) and not math.isfinite(value): raise ValueError(f'{key} must be finite.')
    effective = original | supplied
    for key in ('nxFig', 'nyFig', 'finterval', 'fibintwid'):
        if key in effective and effective[key] <= 0: raise ValueError(f'{key} must be positive.')
    if 'fiberCoefDegree' in effective and effective['fiberCoefDegree'] < 0:
        raise ValueError('fiberCoefDegree must be nonnegative.')
    # These are execution-policy overrides, not changes to legacy defaults.
    if 'flgPause' in effective: effective['flgPause'] = False
    if 'overwrite' in effective: effective['overwrite'] = overwrite
    return effective


def read_table(path):
    with open(path, encoding='utf-8-sig', newline='') as stream:
        records = list(csv.reader(stream))
    if not records or not records[0] or len(set(records[0])) != len(records[0]):
        raise ValueError('CSV header is empty or contains duplicate columns.')
    columns, records = records[0], records[1:]
    if any(len(r) != len(columns) for r in records): raise ValueError('CSV row width does not match schema.')
    if 'DSNO' not in columns: raise ValueError('CSV requires DSNO.')
    return columns, [dict(zip(columns, r)) for r in records]


def select_rows(rows, ids):
    indexed = {}
    for row in rows:
        if not any(row.values()): continue  # retain blank separator records in the table
        value = row['DSNO']
        if not re.fullmatch(r'[0-9]+', value): raise ValueError(f'Invalid CSV DSNO: {value!r}')
        key = int(value)
        if key in indexed: raise ValueError(f'Duplicate CSV DSNO: {value}')
        indexed[key] = row
    missing = set(ids) - indexed.keys()
    if missing: raise ValueError(f'DSNO not present in CSV: {sorted(missing)}')
    return [indexed[i] for i in ids]


def file_plan(step, rows, opts, raw, output, scripts):
    """Shared dependency contract plus execution-only preflight validation."""
    inputs, products, auxiliary = set(), set(), set()
    def number(row, name):
        value = float(row.get(name, ''))
        if not math.isfinite(value): raise ValueError(f'{name} must be finite.')
        return value
    for row in rows:
        plan = contract(step, row, opts)
        products.update(plan.products)
        for item in plan.inputs:
            (auxiliary if item.root == 'scripts' else inputs).add(item.path)
        if step == 'mkSpFrames4f':
            if not row.get('DATATYPE', '').strip(): raise ValueError('DATATYPE is required.')
            matches = raw_matches(row, raw)
            if not matches: raise FileNotFoundError(f'No raw CCD files match {row.get("ORIGIN")}')
            if any(not p.is_file() for p in matches): raise ValueError('Raw pattern matches a directory.')
            for path in matches: under(raw, path.relative_to(Path(raw).resolve()))
            for column in METADATA:
                if column not in row: raise ValueError(f'CSV schema lacks metadata column {column}.')
        elif step == 'mkFibFit4c':
            for column in ('FIBX0', 'FIBX1', 'FIBXWID'): number(row, column)
            if number(row, 'FIBXWID') <= 0: raise ValueError('FIBXWID must be positive.')
            for column in ('NFIBXY', 'IFIBIACT'):
                if column not in row: raise ValueError(f'Missing CSV column {column}.')
                if row[column].strip():
                    values = [int(v.strip()) for v in row[column].split(',')]
                    if column == 'NFIBXY' and (len(values) != 2 or min(values) <= 0): raise ValueError('NFIBXY requires two positive integers.')
        elif step in ('mkWavMap4d', 'mkWcalSpec4d'):
            if 'WLFLAT' not in row: raise ValueError('Missing CSV column WLFLAT.')
            if step == 'mkWavMap4d':
                for column in ('PIXWAV1', 'WAVSTEP1', 'CALWAV1'): number(row, column)
                if number(row, 'WAVSTEP1') == 0: raise ValueError('WAVSTEP1 cannot be zero.')
                lines = [float(v) for v in row.get('CALWAVS', '').split(',')]
                if not all(math.isfinite(v) for v in lines): raise ValueError('CALWAVS must contain finite numbers.')
                if 'PIXWAVS' not in row: raise ValueError('Missing CSV column PIXWAVS.')
                if row['PIXWAVS'].strip():
                    pixels = [float(v) for v in row['PIXWAVS'].split(',')]
                    if len(pixels) != len(lines) or not all(math.isfinite(v) for v in pixels): raise ValueError('PIXWAVS must match CALWAVS.')
                    number(row, 'PIXDWAVS')
            else:
                if 'SKYFLAT' not in row or 'WAVSHIFT' not in row: raise ValueError('CSV requires SKYFLAT and WAVSHIFT columns.')
                if row['WAVSHIFT'].strip(): number(row, 'WAVSHIFT')
                if not row['WLFLAT'].strip(): raise ValueError('mkWcalSpec4d requires a nonempty WLFLAT path even with flgNoWLflat (legacy limitation).')
    for rel in inputs:
        if not under(output, rel).is_file(): raise FileNotFoundError(f'Missing input FITS: {under(output, rel)}')
    for rel in auxiliary:
        if not under(scripts, rel).is_file(): raise FileNotFoundError(f'Missing solar reference: {under(scripts, rel)}')
    if inputs & products: raise ValueError('A product would overwrite an input FITS. Use distinct dataset filenames.')
    return inputs, products, auxiliary


@contextlib.contextmanager
def exclusive_lock(path):
    """OS lock is released even if the process is killed; no stale-lock deletion."""
    with open(path, 'a+b') as stream:
        stream.seek(0, 2)
        if stream.tell() == 0: stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as ex:
            raise RuntimeError(f'Another reduction is using {path}') from ex
        try: yield
        finally:
            stream.seek(0)
            if os.name == 'nt': msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def configure(scripts, csv_path, raw, stage, png_directory=None):
    cfg = load_module('cfg', Path(scripts) / 'cfg.py')
    png_root = Path(png_directory).expanduser().resolve() if png_directory else Path(getattr(cfg, 'png_path', Path(scripts) / 'png')).resolve()
    png_root.mkdir(parents=True, exist_ok=True)
    cfg.png_path = str(png_root) + os.sep
    cfg.fileCsv = str(csv_path)
    cfg.original_path = str(Path(raw).resolve()) + os.sep
    cfg.fits_path = str(stage) + os.sep
    cfg.current_dir = str(stage) + os.sep
    cfg.pythonide = 'tifres-noninteractive'
    cfg.flgWpos = False
    return cfg


def write_table(path, columns, rows):
    with open(path, 'w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader(); writer.writerows(rows)
        stream.flush(); os.fsync(stream.fileno())


class ExactDsno(int):
    def __format__(self, spec):
        return str(self) if spec == '.0f' else super().__format__(spec)


@contextlib.contextmanager
def adapters(csv_path, columns, rows, selected_ids):
    """Only process-local I/O and display adapters; no numerical replacements."""
    import pandas as pd
    import matplotlib
    matplotlib.use('Agg', force=True)
    import matplotlib.pyplot as plt
    from astropy.io import fits
    old_read, old_write = pd.read_csv, pd.DataFrame.to_csv
    old_input, old_use, old_show, old_pause = builtins.input, matplotlib.use, plt.show, plt.pause
    old_open = fits.open
    snapshots = {}
    failures = []
    def read(path, *args, **kwargs):
        frame = old_read(path, *args, **kwargs)
        if Path(path).resolve() == Path(csv_path).resolve():
            if len(frame) != len(rows): raise ValueError('Legacy CSV reader changed row count.')
            frame['DSNO'] = pd.Series([ExactDsno(r['DSNO']) if r['DSNO'] else None for r in rows], dtype=object)
            for column in PATH_FIELDS:
                if column in frame:
                    frame[column] = frame[column].map(lambda v: v.replace('\\', '/') if isinstance(v, str) else v)
            snapshots[id(frame)] = frame.copy(deep=True)
        return frame
    def write(frame, path=None, *args, **kwargs):
        if path is None or Path(path).resolve() != Path(csv_path).resolve():
            raise RuntimeError('Unexpected legacy CSV destination.')
        baseline = snapshots.get(id(frame))
        if baseline is None or list(frame.columns) != columns or len(frame) != len(rows):
            raise ValueError('Legacy processing changed the CSV schema or row count.')
        merged = [dict(r) for r in rows]
        for index, row in enumerate(rows):
            for column in columns:
                before, after = baseline.iloc[index][column], frame.iloc[index][column]
                same = (pd.isna(before) and pd.isna(after)) or (not pd.isna(before) and not pd.isna(after) and before == after)
                if not same:
                    if column not in METADATA or not row['DSNO'] or int(row['DSNO']) not in selected_ids:
                        raise ValueError(f'Unexpected legacy CSV change: row {index}, {column}')
                    merged[index][column] = '' if pd.isna(after) else str(after)
        write_table(csv_path, columns, merged)
    def no_input(prompt=''):
        failures.append(f'Legacy requested console input: {prompt}')
        raise RuntimeError(failures[-1])
    def checked_open(*args, **kwargs):
        try: return old_open(*args, **kwargs)
        except Exception as ex:
            failures.append(f'FITS read failed: {ex}')
            raise
    pd.read_csv, pd.DataFrame.to_csv = read, write
    builtins.input = no_input
    matplotlib.use = lambda *a, **k: None  # prevent legacy Qt5Agg overriding Agg
    plt.show = lambda *a, **k: None
    plt.pause = lambda *a, **k: None
    fits.open = checked_open
    try:
        yield
        if failures: raise RuntimeError('\n'.join(failures))
    finally:
        pd.read_csv, pd.DataFrame.to_csv = old_read, old_write
        builtins.input, matplotlib.use, plt.show, plt.pause = old_input, old_use, old_show, old_pause
        fits.open = old_open
        plt.close('all')


def execute(args):
    scripts, csv_path, raw, output = (Path(v).expanduser().resolve() for v in (args.script_dir, args.csv, args.raw_dir, args.fits_dir))
    for path in (scripts, raw, output):
        if not path.is_dir(): raise FileNotFoundError(f'Directory does not exist: {path}')
    for path in (csv_path, scripts / 'cfg.py', scripts / (args.step + '.py')):
        if not path.is_file(): raise FileNotFoundError(f'File does not exist: {path}')
    ids = dsnos(args.dsno)
    opts = options(scripts, args.step, args.options_json, args.overwrite)
    original = csv_path.read_bytes()
    columns, rows = read_table(csv_path)
    selected = select_rows(rows, ids)
    inputs, products, auxiliary = file_plan(args.step, selected, opts, raw, output, scripts)
    published_products = products
    if getattr(args, 'quick_look', False):
        from tifres_quicklook import owned_products, STEPS as QUICK_STEPS
        if args.step not in QUICK_STEPS: raise ValueError('Quick Look cannot generate calibrations.')
        published_products = set().union(*(set(owned_products(args.step, row, opts)) for row in selected))
        for other in rows:
            if other not in selected and any(other.get('FILENAME') == row.get('FILENAME') for row in selected):
                raise ValueError('Quick Look FILENAME belongs to another dataset.')
        # Revalidate all calibration contracts at the publication boundary.
        for row in selected:
            for item in contract(args.step, row, opts).inputs:
                if not item.role.startswith('FILENAME') and item.path in published_products:
                    raise ValueError('Quick Look would replace a calibration input.')
    for rel in published_products:
        target = under(output, rel)
        if target.exists() and not args.overwrite: raise FileExistsError(f'Product exists; enable overwrite explicitly: {target}')
    missing = [p for p in PACKAGES if importlib.util.find_spec(p) is None]
    if missing: raise RuntimeError('Missing Python packages: ' + ', '.join(missing))
    print(json.dumps(dict(dsno=[str(i) for i in ids], step=args.step, effective_options=opts,
                          outputs=[str(p) for p in sorted(published_products)])), flush=True)
    if args.check_only: return
    with exclusive_lock(output / '.tifres-reduction.lock'), exclusive_lock(csv_path.with_name(csv_path.name + '.reduction.lock')):
        # Recheck inside lock; another process might have finished during preflight.
        if csv_path.read_bytes() != original: raise RuntimeError('CSV changed during preflight; run again.')
        for rel in published_products:
            if under(output, rel).exists() and not args.overwrite: raise FileExistsError(f'Product exists: {rel}')
        run_id = args.run_id or uuid.uuid4().hex
        if not re.fullmatch(r'[a-fA-F0-9]{32}', run_id): raise ValueError('Invalid run ID.')
        stage = output / '.tifres-runs' / run_id
        stage.mkdir(parents=True)
        print(f'Staging directory (retained on failure/cancellation): {stage}', flush=True)
        with Publication(stage, output, published_products, args.overwrite) as publication:
            records = [snapshot(args.step, row, opts, raw, output, scripts) for row in selected]
            plans = [contract(args.step, row, opts) for row in selected]
            for rel in inputs:
                target = stage / rel; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(under(output, rel), target)
            for rel in auxiliary:
                target = stage / rel; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(under(scripts, rel), target)
            work_csv = stage / 'dataset.csv'
            work_csv.write_bytes(original)
            (stage / 'source.csv').write_bytes(original)
            cfg = configure(scripts, work_csv, raw, stage, args.png_dir)
            print(f'PNG directory: {cfg.png_path}', flush=True)
            sys.path.insert(0, str(scripts))
            with adapters(work_csv, columns, rows, set(ids)):
                module = load_module(args.step, scripts / (args.step + '.py'))
                # Legacy uses __file__ for PNG labels and a Windows-only backup path.
                module.__file__ = str(stage / (args.step + '.py'))
                if hasattr(module, 'shutil'):
                    proxy = types.SimpleNamespace(**{n: getattr(shutil, n) for n in dir(shutil)})
                    def backup_copy(source, destination, *a, **kw):
                        destination = Path(str(destination).replace('\\', '/'))
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        return shutil.copy2(source, destination, *a, **kw)
                    proxy.copy2 = backup_copy
                    module.shutil = proxy
                # Fail if a selected function quietly returns without producing every product.
                getattr(module, args.step)([ExactDsno(i) for i in ids], **opts)
            from astropy.io import fits
            for rel in products:
                if not (stage / rel).is_file(): raise RuntimeError(f'Legacy function did not produce {rel}')
                with fits.open(stage / rel) as hdus: hdus.verify('exception')
            updated_columns, updated_rows = read_table(work_csv)
            if updated_columns != columns or len(updated_rows) != len(rows): raise ValueError('CSV schema changed.')
            if csv_path.read_bytes() != original: raise RuntimeError('CSV changed during reduction. Products retained in staging; reopen CSV and retry.')
            if records != [snapshot(args.step, row, opts, raw, output, scripts) for row in selected]:
                raise RuntimeError('Required inputs or processing source changed during reduction; outputs retained in staging.')
            publication.publish()
            if updated_rows != rows:
                from datetime import datetime, timezone
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                backup = csv_path.with_name(csv_path.name + '.' + stamp + '.bak')
                with open(backup, 'xb') as stream: stream.write(original)
                temp = csv_path.with_name(csv_path.name + '.' + uuid.uuid4().hex + '.tmp')
                write_table(temp, columns, updated_rows)
                if csv_path.read_bytes() != original: raise RuntimeError('CSV changed before commit; updated CSV retained in staging.')
                publication.check_cancel()
                os.replace(temp, csv_path)
                print(f'CSV metadata saved; backup: {backup}', flush=True)
            publication.check_cancel()
            if getattr(args, 'quick_look', False):
                for plan in plans:
                    plan.products = {p: k for p, k in plan.products.items() if p in published_products}
            save_records(stage, records, plans)
            publication.check_cancel()
            print('Reduction completed successfully.', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--step', required=True, choices=STEPS)
    parser.add_argument('--dsno', nargs='+', required=True)
    for name in ('script-dir', 'csv', 'raw-dir', 'fits-dir'): parser.add_argument('--' + name, required=True)
    parser.add_argument('--options-json', default='{}')
    parser.add_argument('--overwrite', action='store_true', help='Explicit permission to replace existing FITS products.')
    parser.add_argument('--quick-look', action='store_true', help='Publish only the selected science dataset products; protect calibration side products.')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--png-dir', default=None, help='PNG root; defaults to the original cfg.png_path or script directory/png.')
    parser.add_argument('--run-id', default=None)
    try:
        execute(parser.parse_args(argv))
        return 0
    except CancelledError as ex:
        print(f'CANCELLED: {ex}', file=sys.stderr, flush=True)
        return 130
    except Exception as ex:
        print(f'ERROR: {type(ex).__name__}: {ex}', file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    raise SystemExit(main())
