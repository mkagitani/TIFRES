"""Recoverable publication of already verified products; no scientific processing."""
import json
import os
from pathlib import Path
import shutil


class CancelledError(RuntimeError):
    pass


class Publication:
    def __init__(self, stage, output, products, overwrite):
        self.stage, self.output = Path(stage), Path(output)
        self.products, self.overwrite = sorted(products), overwrite
        self.manifest = self.stage / 'recovery.json'
        self.state = dict(state='Generating', output=str(self.output), overwrite=overwrite,
                          products=[str(p) for p in self.products], published=[], replacing=None,
                          previous_directory=str(self.stage / '.previous'),
                          prepared_directory=str(self.stage / '.prepared'))
        self.save()

    def save(self):
        temp = self.manifest.with_suffix('.json.tmp')
        with temp.open('w', encoding='utf-8') as stream:
            json.dump(self.state, stream, indent=2)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, self.manifest)

    def check_cancel(self):
        marker = os.environ.get('TIFRES_CANCEL_FILE')
        if (self.stage / 'cancel.request').exists() or (marker and Path(marker).exists()):
            raise CancelledError(f'Cancelled; recoverable files: {self.stage}')

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        self.state['state'] = 'Completed' if kind is None else 'Cancelled' if issubclass(kind, CancelledError) else 'Failed'
        if value is not None: self.state['error'] = str(value)
        self.save()
        if kind is not None: print(f'Recovery manifest and retained outputs: {self.manifest}', flush=True)

    def publish(self):
        self.check_cancel()
        self.state['state'] = 'Preparing publication'; self.save()
        # Prepare every complete replacement and preserve every prior product before
        # modifying any destination. Killed copies remain only in the staging tree.
        for rel in self.products:
            self.check_cancel()
            destination = (self.output / rel).resolve()
            if not destination.is_relative_to(self.output.resolve()): raise ValueError('Output escapes configured root.')
            if destination.exists():
                if not self.overwrite: raise FileExistsError(f'Product exists: {destination}')
                previous = self.stage / '.previous' / rel
                previous.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, previous)
            ready = self.stage / '.prepared' / rel
            ready.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.stage / rel, ready)
            with ready.open('r+b') as stream: os.fsync(stream.fileno())
        self.state['state'] = 'Publishing'; self.save()
        print(f'Publishing verified FITS. Recovery manifest: {self.manifest}', flush=True)
        for rel in self.products:
            self.check_cancel()
            destination = self.output / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.state['replacing'] = str(rel); self.save()
            self.check_cancel()
            ready = self.stage / '.prepared' / rel
            if self.overwrite: os.replace(ready, destination)
            else: os.link(ready, destination)  # Atomic no-clobber, including racing writers.
            self.state['published'].append(str(rel)); self.state['replacing'] = None; self.save()
            print(f'Published: {destination}', flush=True)
        self.check_cancel()
