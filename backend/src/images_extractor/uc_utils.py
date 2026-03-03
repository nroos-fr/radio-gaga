#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb 28 20:49:11 2026

@author: moli
"""

from pathlib import Path
import pydicom
from typing import Dict, Any, List, Tuple


import numpy as np

# =========================================================
# Chargement CT
# =========================================================


def load_ct_series_info(ct_dir: Path) -> Dict[str, Any]:
    """
    Charge les métadonnées utiles d'une série CT.
    Trie les slices par position z si possible.
    """
    files = sorted(ct_dir.glob("*.dcm"))
    if not files:
        raise FileNotFoundError(f"Aucun .dcm trouvé dans {ct_dir}")

    ds0 = pydicom.dcmread(files[0], stop_before_pixels=True)

    pixel_spacing = ds0.get("PixelSpacing", None)
    if pixel_spacing is None:
        raise ValueError(f"PixelSpacing absent dans {files[0]}")

    dy_mm = float(pixel_spacing[0])
    dx_mm = float(pixel_spacing[1])

    slices = []
    for f in files:
        ds = pydicom.dcmread(f, stop_before_pixels=True)

        uid = ds.get("SOPInstanceUID", None)
        uid = str(uid) if uid is not None else None

        ipp = ds.get("ImagePositionPatient", None)
        z = float(ipp[2]) if ipp is not None else None

        instance_number = int(ds.get("InstanceNumber", 0))

        slices.append(
            {
                "path": f,
                "uid": uid,
                "z": z,
                "instance_number": instance_number,
            }
        )

    if all(s["z"] is not None for s in slices):
        slices.sort(key=lambda s: s["z"])
        z_sorted = np.array([s["z"] for s in slices], dtype=float)
        if len(z_sorted) >= 2:
            dz_mm = float(np.median(np.abs(np.diff(z_sorted))))
        else:
            dz_mm = float(ds0.get("SliceThickness", 1.0))
    else:
        slices.sort(key=lambda s: s["instance_number"])
        dz_mm = float(ds0.get("SliceThickness", 1.0))

    ordered_files = [s["path"] for s in slices]
    ordered_uids = [s["uid"] for s in slices if s["uid"] is not None]

    uid_to_file = {}
    uid_to_z = {}
    uid_to_index = {}

    for idx, s in enumerate(slices):
        if s["uid"] is not None:
            uid_to_file[s["uid"]] = s["path"]
            uid_to_index[s["uid"]] = idx
            if s["z"] is not None:
                uid_to_z[s["uid"]] = s["z"]

    return {
        "files": ordered_files,
        "ordered_files": ordered_files,
        "ordered_uids": ordered_uids,
        "uid_to_file": uid_to_file,
        "uid_to_z": uid_to_z,
        "uid_to_index": uid_to_index,
        "dx_mm": dx_mm,
        "dy_mm": dy_mm,
        "dz_mm": dz_mm,
        "study_date": ds0.get("StudyDate", None),
        "series_description": ds0.get("SeriesDescription", ct_dir.name),
    }


def load_ct_slice_hu(path: Path) -> np.ndarray:
    """
    Charge une slice CT et la convertit en HU.
    """
    ds = pydicom.dcmread(path)
    img = ds.pixel_array.astype(np.float32)

    slope = float(ds.get("RescaleSlope", 1.0))
    intercept = float(ds.get("RescaleIntercept", 0.0))
    img = img * slope + intercept

    return img


def load_ct_volume_sorted(ct_info: Dict[str, Any]) -> Tuple[np.ndarray, List[Path]]:
    """
    Charge le volume CT dans l'ordre trié utilisé pour uid_to_index.
    """
    ct_paths = ct_info["ordered_files"]
    ct_slices = [load_ct_slice_hu(Path(p)) for p in ct_paths]
    ct_vol = np.stack(ct_slices, axis=0)
    return ct_vol, ct_paths
