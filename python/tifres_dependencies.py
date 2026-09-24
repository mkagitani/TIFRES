"""The five legacy callables' file contract; no imports or execution of legacy code."""
from dataclasses import dataclass, field
from pathlib import Path
import re

STEPS = ('mkSpFrames4f', 'mkFibFit4c', 'mkFibSpec4d', 'mkWavMap4d', 'mkWcalSpec4d')
LABELS = ('SpFrames', 'Fiber Fit', 'Fiber Spec', 'Wavelength Map', 'Wavelength Calibration')
# Only scientific options/CSV fields belong in freshness signatures. Plot/pause/
# overwrite options and columns written as reduction metadata are deliberately absent.
OPTION_FIELDS = {STEPS[0]: (), STEPS[1]: ('finterval',), STEPS[2]: ('fibintwid',),
                 STEPS[3]: ('fibintwid', 'flgNoWLflat', 'fiberCoefDegree'),
                 STEPS[4]: ('fibintwid', 'flgNoWLflat')}
CSV_FIELDS = {STEPS[0]: ('FILENAME', 'ORIGIN', 'DARKFRAME'),
              STEPS[1]: ('FILENAME', 'DARKFRAME', 'FIBX0', 'FIBX1', 'FIBXWID', 'NFIBXY', 'IFIBIACT'),
              STEPS[2]: ('FILENAME', 'DARKFRAME', 'WLFLAT'),
              STEPS[3]: ('FILENAME', 'WLFLAT', 'PIXWAV1', 'CALWAV1', 'WAVSTEP1', 'CALWAVS', 'PIXWAVS', 'PIXDWAVS'),
              STEPS[4]: ('FILENAME', 'WLFLAT', 'WAVMAP', 'SKYFLAT', 'WAVSHIFT')}


def relative(value):
    value = value.replace('\\', '/')
    path = Path(value)
    if not value or path.anchor or value.startswith('/') or '..' in path.parts or ':' in value:
        raise ValueError(f'CSV file paths must be relative to their configured root: {value!r}')
    if '.tifres-runs' in path.parts:
        raise ValueError('Staged outputs cannot be used as published products.')
    return path


def under(root, rel):
    root = Path(root).resolve()
    path = (root / rel).resolve()
    if not path.is_relative_to(root): raise ValueError(f'Path escapes configured directory: {path}')
    return path


def raw_matches(row, raw):
    pattern = under(raw, relative(row.get('ORIGIN', '')))
    expr = re.sub(r'{(.*?)}', lambda m: '(' + '|'.join(m.group(1).split(',')) + ')', pattern.name)
    expr = re.sub(r'\*', r'.*', re.sub(r'\?', r'.', expr))
    return sorted((p for p in pattern.parent.iterdir() if re.match(expr, p.name)), key=lambda p: (p.stat().st_mtime_ns, p.name)) if pattern.parent.is_dir() else []


@dataclass
class Input:
    path: Path
    role: str
    producer: str | None  # Expected callable, resolved against CSV FILENAME, not suffix guesses.
    base: str | None
    kind: str
    root: str = 'fits'


@dataclass
class Contract:
    products: dict = field(default_factory=dict)  # relative path -> structural contract
    inputs: list = field(default_factory=list)


def contract(step, row, opts):
    result = Contract()
    def value(key):
        if not row.get(key, '').strip(): raise ValueError(f'DSNO {row["DSNO"]}: required CSV field {key} is empty.')
        return str(relative(row[key]))
    name = value('FILENAME')
    if not name.endswith('.fits'): raise ValueError('FILENAME must end with .fits.')
    width = opts.get('fibintwid', 5)
    def add(base, role, producer, kind, suffix=None):
        path = base.replace('.fits', suffix) if suffix else base
        result.inputs.append(Input(relative(path), role, producer, base, kind))
    if step == STEPS[0]:
        result.products = {relative(name): 'frame', relative(str(Path(name).with_suffix('')) + '.m.fits'): 'frame'}
        if row.get('DARKFRAME', '').strip(): add(value('DARKFRAME'), 'DARKFRAME', STEPS[0], 'frame')
    elif step in STEPS[1:3]:
        add(name, 'FILENAME', STEPS[0], 'frame')
        add(value('DARKFRAME'), 'DARKFRAME', STEPS[0], 'frame')
        if step == STEPS[1]: result.products = {relative(name.replace('.fits', '.fib.fits')): 'trace'}
        else:
            add(value('WLFLAT'), 'WLFLAT → fiber trace', STEPS[1], 'trace', '.fib.fits')
            result.products = {relative(name.replace('.fits', f'.w{width}fsp.fits')): 'spectrum'}
    else:
        add(name, 'FILENAME → fiber spectrum', STEPS[2], 'spectrum', f'.w{width}fsp.fits')
        if row.get('WLFLAT', '').strip() and not opts.get('flgNoWLflat', False):
            add(value('WLFLAT'), 'WLFLAT → fiber spectrum', STEPS[2], 'spectrum', f'.w{width}fsp.fits')
        if step == STEPS[3]:
            cal = float(row.get('CALWAV1', ''))
            band = next((f'{a}-{b}' for a,b in ((548,568),(586,596),(625,635),(760,780)) if a <= cal <= b), None)
            if band is None: raise ValueError('CALWAV1 is outside supported solar-reference bands.')
            result.inputs.append(Input(Path('psg') / f'psgrad{band}.txt', 'solar reference', None, None, 'text', 'scripts'))
            result.products = {relative(name.replace('.fits', f'.w{width}wmp.fits')): 'map'}
        elif step == STEPS[4]:
            add(name, 'FILENAME (required by legacy)', STEPS[0], 'frame')
            ref = value('WAVMAP')
            # Reverse the EXACT producer expression, resolved later by comparing
            # every CSV FILENAME.replace('.fits', '.wmp.fits') to this reference.
            result.inputs.append(Input(relative(ref.replace('.wmp.fits', f'.w{width}wmp.fits')),
                                       'WAVMAP', STEPS[3], ref, 'map'))
            result.products = {relative(name.replace('.fits', f'.w{width}wc.fits')): 'calibrated',
                               relative(name.replace('.fits', f'.w{width}img.fits')): 'image'}
            if row.get('SKYFLAT', '').strip():
                sky = value('SKYFLAT')
                add(sky, 'SKYFLAT → fiber spectrum', STEPS[2], 'spectrum', f'.w{width}fsp.fits')
                result.products[relative(sky.replace('.fits', f'.w{width}wc.fits'))] = 'calibrated'
        else: raise ValueError(f'Unsupported step: {step}')
    return result


def parameters(step, row, opts):
    fields = list(CSV_FIELDS[step])
    if step in STEPS[3:] and opts.get('flgNoWLflat', False): fields.remove('WLFLAT')
    if step == STEPS[3] and not row.get('PIXWAVS', '').strip(): fields.remove('PIXDWAVS')
    return {'csv': {k: row.get(k, '') for k in fields},
            'options': {k: opts[k] for k in OPTION_FIELDS[step]}}
