#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb 28 20:46:51 2026

@author: moli
"""

from pathlib import Path
import pydicom
from typing import Optional, List

# Default dataset root – computed relative to this file so it works on any machine.
# (radio-gaga/backend/src/images_extractor/io_utils.py → parents[3] = radio-gaga/)
DATASET_ROOT = Path(__file__).parents[3] / "data" / "studies"

# =========================================================
# Outils généraux
# =========================================================


def format_dicom_date(d):
    if d is None:
        return "Date inconnue"
    d = str(d)
    if len(d) == 8 and d.isdigit():
        return f"{d[6:8]}/{d[4:6]}/{d[0:4]}"
    return d


def get_study_date_raw(study_dir: Path) -> str:
    """
    Retourne la date brute DICOM YYYYMMDD d'un examen.
    Sert au tri chronologique.
    """
    for series in study_dir.iterdir():
        if not series.is_dir():
            continue
        dcm_files = sorted(series.glob("*.dcm"))
        if dcm_files:
            try:
                ds = pydicom.dcmread(dcm_files[0], stop_before_pixels=True)
                return str(ds.get("StudyDate", "99999999"))
            except Exception:
                pass
    return "99999999"


def find_patient_dir(
    patient_id: str, dataset_root: Path = DATASET_ROOT
) -> Optional[Path]:
    """
    Retrouve le dossier patient.
    Exemple : PATIENT001 -> PATIENT001 PATIENT001
    """
    patient_id = str(patient_id).strip()

    exact = dataset_root / f"{patient_id} {patient_id}"
    if exact.exists() and exact.is_dir():
        return exact

    for p in dataset_root.iterdir():
        if p.is_dir() and p.name.startswith(patient_id):
            return p

    return None


# =========================================================
# Choix CT / SEG
# =========================================================


def choose_ct_series_by_priority(study_dir: Path) -> Optional[Path]:
    """
    Priorité :
    1) CT lung
    2) CT CEV torax
    """
    series_dirs = [p for p in study_dir.iterdir() if p.is_dir()]

    for p in series_dirs:
        if p.name.lower() == "ct lung":
            return p

    for p in series_dirs:
        if p.name.lower() == "ct cev torax":
            return p

    return None


def find_reference_seg(study_dir: Path) -> Optional[Path]:
    """
    Cherche une SEG de référence dans l'examen.
    """
    for series in study_dir.iterdir():
        if not series.is_dir():
            continue
        if series.name.lower().startswith("seg "):
            dcm_files = sorted(series.glob("*.dcm"))
            if dcm_files:
                return dcm_files[0]
    return None


def get_seg_referenced_uids(seg_ds) -> Optional[List[str]]:
    """
    Retourne la liste des SOPInstanceUID CT référencés par la SEG
    via ReferencedSeriesSequence si disponible.
    """
    try:
        ref_series = seg_ds.ReferencedSeriesSequence[0]
        ref_inst_seq = ref_series.ReferencedInstanceSequence
        return [str(item.ReferencedSOPInstanceUID) for item in ref_inst_seq]
    except Exception:
        return None


def find_ct_series_matching_seg(study_dir: Path, seg_ds) -> Optional[Path]:
    """
    Essaie de retrouver la vraie série CT référencée par la SEG
    en comparant les SOPInstanceUID.
    """
    ref_uids = get_seg_referenced_uids(seg_ds)
    if not ref_uids:
        return None

    ref_uid_set = set(ref_uids)

    for series in study_dir.iterdir():
        if not series.is_dir():
            continue

        lname = series.name.lower()
        if lname.startswith("seg "):
            continue
        if lname.startswith("sr "):
            continue

        dcm_files = sorted(series.glob("*.dcm"))
        if not dcm_files:
            continue

        series_uids = set()
        for f in dcm_files:
            try:
                ds = pydicom.dcmread(f, stop_before_pixels=True)
                uid = ds.get("SOPInstanceUID", None)
                if uid is not None:
                    series_uids.add(str(uid))
            except Exception:
                pass

        if ref_uid_set.issubset(series_uids):
            return series

    return None


def get_number_of_annotated_lesions(seg_ds) -> int:
    """
    Nombre de segments annotés dans le SEG.
    """
    if "SegmentSequence" in seg_ds:
        return len(seg_ds.SegmentSequence)
    return 0
