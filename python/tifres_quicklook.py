"""Read-only Quick Look raw/header inspection and exact three-step planning."""
import argparse
import json
import re
from pathlib import Path
from datetime import date
from astropy.io import fits
from tifres_dependencies import contract, raw_matches, relative, under
from tifres_launcher import options, METADATA
from tifres_status import validate_fits

STEPS = ('mkSpFrames4f', 'mkFibSpec4d', 'mkWcalSpec4d')


def owned_products(step, row, opts):
    # SKYFLAT wc is a legacy side product, never a new science dataset's product.
    own = dict(row)
    if step == STEPS[-1]:
        own['SKYFLAT'] = ''
    return contract(step, own, opts).products


def inspect_raw(raw, selected=None, origin=''):
    raw = Path(raw).resolve()
    selected = [Path(p).resolve() for p in (selected or [])]
    for p in selected:
        if not p.is_file() or not p.is_relative_to(raw):
            raise ValueError(f'Raw FITS must be inside configured raw directory: {p}')
    proposal = origin
    if not proposal and selected:
        parents = {p.parent for p in selected}
        if len(parents) != 1:
            raise ValueError('Selected files span directories; enter an explicit ORIGIN.')
        names = [p.name for p in selected]
        if len(names) == 1:
            proposal = selected[0].relative_to(raw).as_posix()
        else:
            stems = [re.fullmatch(r'(.+_)[0-9]+(\.fits)', name, re.I) for name in names]
            if all(stems) and len({(m[1], m[2]) for m in stems}) == 1:
                proposal = (selected[0].parent.relative_to(raw) / (stems[0][1] + '*' + stems[0][2])).as_posix()
            else:
                # Legacy supports brace alternatives. Propose only safe basenames.
                if not all(re.fullmatch(r'[A-Za-z0-9_.-]+', n) for n in names):
                    raise ValueError('Cannot safely express names; enter ORIGIN manually.')
                proposal = (selected[0].parent.relative_to(raw) / ('{' + ','.join(names) + '}')).as_posix()
    if not proposal:
        raise ValueError('Select raw FITS or enter ORIGIN.')
    matches = raw_matches({'ORIGIN': proposal}, raw)
    if not matches:
        raise FileNotFoundError(f'No raw files match ORIGIN: {proposal}')
    metadata, conflicts, headers = {}, [], []
    for p in matches:
        under(raw, p.relative_to(raw))
        validate_fits(p, 'raw')
        with fits.open(p, memmap=False) as hdus:
            headers.append(dict(hdus[0].header))
    def common(key):
        values = [h.get(key) for h in headers]
        if any(v != values[0] for v in values):
            conflicts.append(f'{key} differs between raw files: {values}')
            return None
        return values[0]
    exposure = common('EXPOSURE')
    if exposure is None:
        exposure = common('EXPTIME')
    if exposure is not None:
        metadata['EXPTIME'] = str(exposure)
    temperature = common('CCDTEMP')
    if temperature is not None:
        metadata['CCDTEMP'] = str(temperature)
    datatype = common('DATATYPE')
    if datatype:
        metadata['DATATYPE'] = str(datatype)
    obj = common('OBJECT')
    if obj:
        conflicts.append('Header OBJECT (informational only): ' + str(obj))
    dates = [str(h.get('DATE-OBS', h.get('DATE', '')))[:10] for h in headers]
    observing_date = dates[0] if dates and all(d == dates[0] for d in dates) else ''
    try:
        date.fromisoformat(observing_date)
    except ValueError:
        observing_date = ''
    if len(set(dates)) > 1:
        conflicts.append('Observation dates disagree: ' + ', '.join(dates))
    ambiguous = bool(selected and set(matches) != set(selected))
    if ambiguous:
        conflicts.append('ORIGIN matches a different set from your selection. Review the complete matched list.')
    metadata['NFILES'] = str(len(matches))
    return dict(fingerprint=json.dumps([(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in matches]), origin=proposal, files=[str(p) for p in matches], ambiguous=ambiguous,
                observingDate=observing_date, metadata=metadata, notes=conflicts)


def plan(request):
    row, raw, output, scripts = request['row'], Path(request['raw']), Path(request['fits']), Path(request['scripts'])
    for path in (raw, output, scripts):
        if not path.is_dir():
            raise FileNotFoundError(f'Directory does not exist: {path}')
    for column in METADATA:
        if column not in row:
            raise ValueError(f'CSV schema lacks metadata column {column}')
    if not row.get('WLFLAT', '').strip():
        raise ValueError('WLFLAT is required by the legacy wavelength calibration.')
    if row.get('WAVSHIFT', '').strip():
        import math
        if not math.isfinite(float(row['WAVSHIFT'])):
            raise ValueError('WAVSHIFT must be finite.')
    opts = {step: options(scripts, step, request['options'][step], request.get('force', False)) for step in STEPS}
    if opts[STEPS[1]]['fibintwid'] != opts[STEPS[2]]['fibintwid']:
        raise ValueError('Fiber Spec and Wcal Spec fibintwid must agree.')
    contracts = {step: contract(step, row, opts[step]) for step in STEPS}
    owned = {step: owned_products(step, row, opts[step]) for step in STEPS}
    all_owned = set().union(*(set(p) for p in owned.values()))
    inputs = {i.path for c in contracts.values() for i in c.inputs}
    # A calibration may not be the new science dataset or any of its outputs.
    for c in contracts.values():
        for item in c.inputs:
            if item.role.startswith('FILENAME'):
                continue
            if item.path in all_owned:
                raise ValueError(f'Calibration/output collision: {item.role}: {item.path}')
            path = under(scripts if item.root == 'scripts' else output, item.path)
            try:
                validate_fits(path, item.kind)
            except Exception as ex:
                raise ValueError(f'Required calibration {item.role}: {path}: {ex}') from ex
    result = []
    for step in STEPS:
        products = owned[step]
        existing = [p for p in products if under(output, p).exists()]
        valid = []
        for p in existing:
            try:
                validate_fits(under(output, p), products[p])
                valid.append(p)
            except Exception as ex:
                if not request.get('force'):
                    raise ValueError(f'Invalid existing product {p}; explicitly enable Force to regenerate: {ex}') from ex
        reuse = len(valid) == len(products) and not request.get('force')
        if existing and not reuse and not request.get('force'):
            raise ValueError(f'Incomplete product set for {step}; enable Force to regenerate safely.')
        result.append(dict(step=step, reuse=reuse, outputs=[str(under(output, p)) for p in products]))
    wc = next(p for p,k in owned[STEPS[-1]].items() if k == 'calibrated')
    return dict(steps=result, viewer=str(under(output, wc)),
                calibrations=sorted(str(under(output, i)) for i in inputs - all_owned))


def viewer_product(wc):
    # The documented optional dcb companion is accepted only if it contains exactly
    # the same calibrated samples, wavelengths and original active fiber IDs.
    from tifres_viewer import read_cube
    import numpy as np
    wc = Path(wc)
    cube = wc.with_name(wc.name.replace('wc.fits', 'dcb.fits'))
    if cube != wc and cube.is_file():
        try:
            m, w, d = read_cube(wc)
            cm, cw, cd = read_cube(cube)
            with fits.open(cube) as hdus:
                is_cube = hdus[0].data.ndim == 3
            if is_cube and m['active'] == cm['active'] and np.array_equal(w, cw) and np.array_equal(d, cd, equal_nan=True):
                return dict(path=str(cube.resolve()))
        except Exception:
            pass  # Optional unverified companions never replace the actual wc output.
    return dict(path=str(wc.resolve()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request-json', required=True)
    args = parser.parse_args()
    request = json.loads(args.request_json)
    if request['action'] == 'raw':
        result = inspect_raw(request['raw'], request.get('selected'), request.get('origin', ''))
    elif request['action'] == 'viewer':
        result = viewer_product(request['wc'])
    else:
        result = plan(request)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
