"""Read-only Astropy viewer export. stdout: u32le JSON length, JSON, f64le wavelengths, f64le [fiber,wavelength]."""
import argparse
import json
from pathlib import Path
import struct
import sys
import warnings
import numpy as np
from astropy.io import fits
from astropy import units as u


def read_cube(path):
    path = Path(path)
    with warnings.catch_warnings(record=True) as notices:
        warnings.simplefilter("always")
        with fits.open(path, mode="readonly", memmap=False, checksum=True) as hdus:
            hdus.verify("exception")
            h, data = hdus[0].header, hdus[0].data
            if data is None or data.ndim not in (2, 3):
                raise ValueError("Expected a calibrated primary 2D fiber spectrum or 3D IFU cube.")
            if data.dtype.kind != "f" or data.dtype.itemsize > 8 or data.size * 8 > 1_000_000_000:
                raise ValueError("Require float32/float64 data and at most 1 GB decoded array.")
            if (h.get("NFIBX"), h.get("NFIBY")) != (10, 12):
                raise ValueError("Only documented NFIBX=10, NFIBY=12 mapping is supported.")
            if any(sum(hdu.name == name for hdu in hdus) != 1 for name in ("FIBERS","IFIBERS")):
                raise ValueError("Require exactly one FIBERS and one IFIBERS HDU.")
            fibers, active = hdus["FIBERS"].data, hdus["IFIBERS"].data
            if fibers is None or not np.issubdtype(fibers.dtype, np.integer) or not np.array_equal(fibers, np.arange(120)):
                raise ValueError("FIBERS must preserve original IDs 0..119.")
            if active is None or active.ndim != 1 or not np.issubdtype(active.dtype, np.integer) or len(set(active)) != len(active) or np.any((active < 0) | (active >= 120)):
                raise ValueError("Invalid IFIBERS active-fiber list.")
            if data.ndim == 2:
                if data.shape[0] != 120 or h.get("CTYPE1") != "WAVE" or h.get("CTYPE2") != "FIBERID":
                    raise ValueError("Expected calibrated [120, wavelength] data; an img.fits is not a cube.")
                n = data.shape[1]; axis = 1; source_order = "fiber,wavelength"
                spectra = np.asarray(data, dtype="<f8", order="C")
            else:
                if data.shape[1:] != (12, 10):
                    raise ValueError("3D primary must have NumPy shape [wavelength,12,10].")
                n = data.shape[0]; source_order = "wavelength,y,x"
                if h.get("CTYPE3") == "WAVE":
                    axis = 3
                elif (path.name.endswith("dcb.fits") and h.get("CTYPE1") == "WAVE"
                      and h.get("CTYPE2") == "FIBERID" and all(k in h for k in ("WAVMIN","WAVSTEP","WAVMAX"))):
                    # Documented legacy dcb layout retained the 2D WC header.
                    axis = 1
                else:
                    raise ValueError("3D wavelength axis is ambiguous; require CTYPE3=WAVE or documented legacy dcb header.")
                spectra = np.asarray(data.reshape(n,120).T, dtype="<f8", order="C")
            if n < 2 or n * 120 * 8 > 1_000_000_000:
                raise ValueError("Unsupported wavelength count (2 samples minimum, 1 GB decoded data maximum).")
            vals = [float(h[f"{k}{axis}"]) for k in ("CRVAL","CDELT","CRPIX")]
            if not np.isfinite(vals).all() or vals[1] <= 0:
                raise ValueError("Require a finite, strictly increasing linear wavelength axis.")
            wavelengths = np.asarray(vals[0] + (np.arange(n,dtype=float)+1-vals[2])*vals[1], dtype="<f8")
            if not np.isfinite(wavelengths).all() or not (np.diff(wavelengths)>0).all():
                raise ValueError("Invalid wavelength coordinates.")
            for key, expected in (("WAVMIN",wavelengths[0]),("WAVSTEP",vals[1])):
                if key in h and not np.isclose(float(h[key]),expected,rtol=1e-9,atol=1e-10):
                    raise ValueError(f"Inconsistent {key} and wavelength WCS.")
            if "WAVMAX" in h and not any(np.isclose(float(h["WAVMAX"]),v,rtol=1e-9,atol=1e-10) for v in (wavelengths[-1],wavelengths[-1]+vals[1])):
                raise ValueError("WAVMAX disagrees with calibrated sample bounds.")
            unit = str(h.get(f"CUNIT{axis}", "")).strip()
            if unit and not u.Unit(unit).is_equivalent(u.m):
                raise ValueError("CUNIT must describe a wavelength length unit.")
            meta = dict(version=1, shape=[120,n], cube_shape=[n,12,10], dtype="float64", byte_order="little",
                        order="fiber,wavelength", source_order=source_order, active=active.tolist(),
                        wavelength_unit=unit or "unspecified (CUNIT absent)", intensity_unit=str(h.get("BUNIT","unspecified")),
                        filename=str(path.resolve()), warnings=[] if unit else ["Wavelength unit is absent; coordinates retained without assuming nm or Angstrom."])
        if notices:
            raise ValueError("; ".join(str(w.message) for w in notices))
    return meta, wavelengths, spectra


def export(path, stream):
    meta, wave, data = read_cube(path)
    encoded = json.dumps(meta,allow_nan=False).encode("utf-8")
    stream.write(struct.pack("<I",len(encoded))); stream.write(encoded)
    stream.write(memoryview(wave).cast("B")); stream.write(memoryview(data).cast("B"))
    stream.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    args = parser.parse_args()
    try:
        export(args.path, sys.stdout.buffer)
    except Exception as ex:
        print(f"FITS viewer: {ex}", file=sys.stderr)
        sys.exit(1)
