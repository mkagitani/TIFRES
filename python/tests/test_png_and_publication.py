import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tifres_launcher as launcher
from tifres_publication import Publication, CancelledError


class PngAndPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tifres png publication ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_standalone_png_default_and_only_root_changes(self):
        legacy = Path(launcher.__file__).parent / 'legacy'
        cfg = launcher.load_module('standalone_cfg', legacy / 'cfg.py')
        self.assertEqual(Path(cfg.png_path), legacy / 'png')
        baseline = json.loads(Path(__file__).with_name('legacy_png_baseline.json').read_text())
        for step in launcher.STEPS:
            with self.subTest(step=step):
                tree = ast.parse((legacy / (step + '.py')).read_text(encoding='utf-8-sig'))
                # Python 3.12 adds empty type_params to functions/classes. They have
                # no scientific meaning and were absent from the Python 3.10 baseline.
                # Keep nonempty generic parameters in the digest.
                for node in ast.walk(tree):
                    if hasattr(node, 'type_params') and not node.type_params:
                        del node.type_params
                digest = hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest()
                self.assertEqual(digest, baseline[step]['normalized_ast_sha256'], 'Only recorded root substitutions are permitted')
                assignments = [n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                               and any(isinstance(t, ast.Name) and t.id == 'filePng' for t in n.targets)]
                self.assertEqual(len(assignments), baseline[step]['root_replacements'])
                for expression in assignments:
                    env = dict(cfg=cfg, os=os, __file__=str(legacy / (step + '.py')),
                               row=types.SimpleNamespace(DSNO=260914111), strDate='20260914',
                               fileDat='sky.sp.fits', fileWMP='sky.sp.w5wmp.fits', fileDatWC='sky.sp.w5wc.fits',
                               savefile='sky.sp.fits', iFig2=2, j=3, i=4)
                    code = compile(ast.Expression(expression), '<png-path>', 'eval')
                    original = Path(eval(code, env)).relative_to(Path(cfg.png_path))
                    custom = self.root / 'custom png'
                    env['cfg'] = types.SimpleNamespace(png_path=str(custom) + os.sep)
                    result = Path(eval(code, env))
                    self.assertEqual(result.relative_to(custom), original)
                    self.assertEqual(original.parts[0], step)
                    self.assertIn('260914111', str(original))

    def test_png_override_and_legacy_fallback(self):
        scripts = self.root / 'scripts'; scripts.mkdir()
        (scripts / 'cfg.py').write_text('import os\n', encoding='utf-8')
        cfg = launcher.configure(scripts, self.root / 'data.csv', self.root, self.root)
        self.assertEqual(Path(cfg.png_path), scripts / 'png')
        custom = self.root / 'diagnostics'
        cfg = launcher.configure(scripts, self.root / 'data.csv', self.root, self.root, custom)
        self.assertEqual(Path(cfg.png_path), custom)
        self.assertTrue(custom.is_dir())

    def prepared(self):
        output = self.root / 'output'; output.mkdir()
        stage = output / '.tifres-runs' / 'mock'; stage.mkdir(parents=True)
        products = [Path('a.fits'), Path('b.fits')]
        for product in products:
            (stage / product).write_bytes(b'new complete product')
            (output / product).write_bytes(b'previous valid product')
        return stage, output, products

    def test_cancelled_generation_does_not_publish(self):
        stage, output, products = self.prepared()
        with self.assertRaises(CancelledError):
            with Publication(stage, output, products, True) as publication:
                (stage / products[0]).write_bytes(b'partial staged write')
                (stage / 'cancel.request').touch()
                publication.publish()
        for p in products: self.assertEqual((output / p).read_bytes(), b'previous valid product')
        self.assertEqual(json.loads((stage / 'recovery.json').read_text())['state'], 'Cancelled')

    def test_failed_generation_does_not_publish(self):
        stage, output, products = self.prepared()
        with self.assertRaises(RuntimeError):
            with Publication(stage, output, products, True):
                raise RuntimeError('mock failure before verification')
        for p in products: self.assertEqual((output / p).read_bytes(), b'previous valid product')
        self.assertEqual(json.loads((stage / 'recovery.json').read_text())['state'], 'Failed')

    def test_overwrite_off_never_replaces_existing_product(self):
        stage, output, products = self.prepared()
        with self.assertRaises(FileExistsError):
            with Publication(stage, output, products, False) as publication: publication.publish()
        for p in products: self.assertEqual((output / p).read_bytes(), b'previous valid product')

    def test_interrupted_publication_retains_old_and_new_products(self):
        stage, output, products = self.prepared()
        replace = os.replace
        def interrupt(source, destination):
            replace(source, destination)
            if Path(destination) == output / products[0]: (stage / 'cancel.request').touch()
        with self.assertRaises(CancelledError):
            with Publication(stage, output, products, True) as publication:
                with patch('tifres_publication.os.replace', side_effect=interrupt): publication.publish()
        self.assertEqual((output / products[0]).read_bytes(), b'new complete product')
        self.assertEqual((output / products[1]).read_bytes(), b'previous valid product')
        for p in products:
            self.assertEqual((stage / '.previous' / p).read_bytes(), b'previous valid product')
            self.assertEqual((stage / p).read_bytes(), b'new complete product')
        journal = json.loads((stage / 'recovery.json').read_text())
        self.assertEqual(journal['state'], 'Cancelled')
        self.assertEqual(journal['published'], ['a.fits'])

    def test_successful_publication_preserves_recovery_copies(self):
        stage, output, products = self.prepared()
        with Publication(stage, output, products, True) as publication: publication.publish()
        for p in products:
            self.assertEqual((output / p).read_bytes(), b'new complete product')
            self.assertEqual((stage / '.previous' / p).read_bytes(), b'previous valid product')
        self.assertEqual(json.loads((stage / 'recovery.json').read_text())['state'], 'Completed')


if __name__ == '__main__': unittest.main()
