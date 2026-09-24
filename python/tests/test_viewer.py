import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import numpy as np
from astropy.io import fits
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tifres_viewer import read_cube, export


def fixture(path, n=7, cube=True, legacy=False):
    data=np.arange(120*n,dtype=np.float64).reshape(120,n)-12.5
    data[2,2]=np.nan
    data[5,:]=np.nan
    h=fits.Header()
    h["NFIBX"]=10;h["NFIBY"]=12
    axis=3 if cube and not legacy else 1
    for k,v in {f"CTYPE{axis}":"WAVE",f"CRVAL{axis}":500.25,f"CDELT{axis}":.125,f"CRPIX{axis}":1.,f"CUNIT{axis}":"nm",
                "WAVMIN":500.25,"WAVSTEP":.125,"WAVMAX":500.25+n*.125}.items():h[k]=v
    if not cube or legacy:h["CTYPE2"]="FIBERID"
    fits.HDUList([fits.PrimaryHDU(data.T.reshape(n,12,10) if cube else data,h),
                  fits.ImageHDU(np.arange(120,dtype=np.int16),name="FIBERS"),
                  fits.ImageHDU(np.delete(np.arange(120,dtype=np.int16),6),name="IFIBERS")]).writeto(path)
    return data


class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def test_3d_orientation_wavelength_precision(self):
        p=self.root/"cube.fits";data=fixture(p,n=17)
        meta,wave,read=read_cube(p)
        np.testing.assert_equal(read,data)
        np.testing.assert_equal(wave,500.25+np.arange(17)*.125)
        self.assertEqual(meta["cube_shape"],[17,12,10]);self.assertEqual(meta["wavelength_unit"],"nm")
        self.assertNotIn(6,meta["active"]);self.assertTrue(np.isnan(read[5]).all())
        self.assertEqual(read[97,4],data[97,4])
    def test_legacy_dcb_and_wc_agree(self):
        a=self.root/"x.w5dcb.fits";b=self.root/"x.w5wc.fits"
        fixture(a,legacy=True);fixture(b,cube=False)
        np.testing.assert_equal(read_cube(a)[2],read_cube(b)[2])
    def test_binary_protocol_and_readonly(self):
        p=self.root/"cube.fits";fixture(p)
        before=hashlib.sha256(p.read_bytes()).hexdigest()
        stream=io.BytesIO();export(p,stream);wire=stream.getvalue()
        n=struct.unpack("<I",wire[:4])[0];meta=json.loads(wire[4:4+n]);data=np.frombuffer(wire[4+n:],dtype="<f8")
        self.assertEqual(meta["dtype"],"float64");self.assertEqual(meta["order"],"fiber,wavelength")
        self.assertEqual(len(data),7+120*7);self.assertEqual(data[7+3*7+1],9.5)
        self.assertEqual(before,hashlib.sha256(p.read_bytes()).hexdigest())
    def test_missing_invalid_and_img(self):
        with self.assertRaises(FileNotFoundError):read_cube(self.root/"missing.fits")
        p=self.root/"bad.fits";p.write_text("not FITS")
        with self.assertRaises(OSError):read_cube(p)
        p=self.root/"img.fits";fixture(p,cube=False)
        with fits.open(p,mode="update") as h:h[0].data=np.zeros((12,10))
        with self.assertRaisesRegex(ValueError,"not a cube"):read_cube(p)
    def test_absent_and_inconsistent_wavelength(self):
        for name,key,value in [("missing","CRVAL3",None),("descending","CDELT3",-.1),("inconsistent","WAVMIN",10),("nan","CDELT3",0)]:
            p=self.root/(name+".fits");fixture(p)
            with fits.open(p,mode="update") as h:
                if value is None:del h[0].header[key]
                else:h[0].header[key]=value
            with self.assertRaises((KeyError,ValueError)):read_cube(p)
    def test_missing_units_explicit_and_no_renumbering(self):
        p=self.root/"cube.fits";fixture(p)
        with fits.open(p,mode="update") as h:del h[0].header["CUNIT3"]
        meta,_,_=read_cube(p)
        self.assertIn("unspecified",meta["wavelength_unit"]);self.assertTrue(meta["warnings"])
        with fits.open(p,mode="update") as h:h["FIBERS"].data=np.arange(1,121)
        with self.assertRaisesRegex(ValueError,"original IDs"):read_cube(p)
    def test_reference_pixel_and_invalid_units(self):
        p=self.root/"offset.fits";fixture(p)
        with fits.open(p,mode="update") as h:
            h[0].header["CRPIX3"]=2.
            h[0].header["CRVAL3"]=500.375
        np.testing.assert_equal(read_cube(p)[1],500.25+np.arange(7)*.125)
        with fits.open(p,mode="update") as h:h[0].header["CUNIT3"]="Hz"
        with self.assertRaisesRegex(ValueError,"length unit"):read_cube(p)

    def test_inconsistent_maximum_and_duplicate_hdus(self):
        p=self.root/"maximum.fits";fixture(p)
        with fits.open(p,mode="update") as h:h[0].header["WAVMAX"]=900
        with self.assertRaisesRegex(ValueError,"WAVMAX"):read_cube(p)
        q=self.root/"duplicate.fits";fixture(q)
        with fits.open(q,mode="update") as h:h.append(fits.ImageHDU(np.arange(120),name="FIBERS"))
        with self.assertRaisesRegex(ValueError,"exactly one"):read_cube(q)

    def test_cli_binary_and_error_exit(self):
        p=self.root/"cube.fits";fixture(p)
        script=Path(__file__).resolve().parents[1]/"tifres_viewer.py"
        run=subprocess.run([sys.executable,"-B",str(script),str(p)],capture_output=True)
        self.assertEqual(run.returncode,0);self.assertGreater(len(run.stdout),100)
        bad=subprocess.run([sys.executable,"-B",str(script),str(p)+"missing"],capture_output=True)
        self.assertNotEqual(bad.returncode,0);self.assertIn(b"FITS viewer",bad.stderr)
