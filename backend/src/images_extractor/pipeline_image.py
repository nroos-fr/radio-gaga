#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb 28 20:53:50 2026

@author: moli
"""

from pathlib import Path
from typing import Dict, Any, List

import numpy as np
import pydicom

from .io_utils import (
    find_patient_dir,
    get_study_date_raw,
    find_reference_seg,
    find_ct_series_matching_seg,
    choose_ct_series_by_priority,
    get_number_of_annotated_lesions,
    format_dicom_date,
)

from .uc_utils import (
    load_ct_series_info,
    load_ct_volume_sorted,
)

from .seg_utils import (
    build_dense_seg_volumes_from_seg,
)

from .lesion_utils import (
    build_lesions_info,
    build_lesions_info_from_aligned_segments,
)

from .display_utils import (
    add_consecutive_recist_like_to_results,
    export_results_to_data_dir,
)

# Default dataset root – computed relative to this file so it works on any machine.
# (radio-gaga/backend/src/images_extractor/pipeline_image.py → parents[3] = radio-gaga/)
DATASET_ROOT = Path(__file__).parents[3] / "data" / "studies"


# =========================================================
# Collecte principale
# =========================================================


def collect_positive_findings_with_arrays(
    patient_id: str, dataset_root: Path = DATASET_ROOT
) -> List[Dict[str, Any]]:
    """
    Retourne une liste de dictionnaires, triés chronologiquement.
    Chaque entrée correspond à un examen positif.
    """
    patient_dir = find_patient_dir(patient_id, dataset_root=dataset_root)
    if patient_dir is None:
        raise FileNotFoundError(
            f"Patient '{patient_id}' introuvable dans {dataset_root}"
        )

    results = []

    studies = sorted(
        [p for p in patient_dir.iterdir() if p.is_dir()], key=get_study_date_raw
    )

    for study_dir in studies:
        ref_seg_path = find_reference_seg(study_dir)
        if ref_seg_path is None:
            continue

        seg_ds = pydicom.dcmread(ref_seg_path)
        ct_dir = find_ct_series_matching_seg(study_dir, seg_ds)

        if ct_dir is None:
            ct_dir = choose_ct_series_by_priority(study_dir)

        if ct_dir is None:
            print(f"[WARN] Aucun CT compatible trouvé pour {study_dir.name}")
            continue

        seg_path = ref_seg_path
        seg_origin = "reference"

        ct_info = load_ct_series_info(ct_dir)
        ct_vol, ct_paths = load_ct_volume_sorted(ct_info)

        seg_ds = pydicom.dcmread(seg_path)

        try:
            seg_vol, seg_by_segment, missed_frames = build_dense_seg_volumes_from_seg(
                seg_ds, ct_info
            )
        except Exception as e:
            print(f"[WARN] SEG non alignable pour {study_dir.name}: {e}")
            continue

        if np.count_nonzero(seg_vol) == 0:
            continue

        n_lesions_annotated = get_number_of_annotated_lesions(seg_ds)

        lesions_info = build_lesions_info_from_aligned_segments(
            seg_by_segment,
            dx_mm=ct_info["dx_mm"],
            dy_mm=ct_info["dy_mm"],
            dz_mm=ct_info["dz_mm"],
        )

        if len(lesions_info) == 0:
            lesions_info = build_lesions_info(
                seg_vol,
                dx_mm=ct_info["dx_mm"],
                dy_mm=ct_info["dy_mm"],
                dz_mm=ct_info["dz_mm"],
            )

        if len(lesions_info) == 0:
            continue

        seg_label = "SEG REF"

        study_date_raw = (
            str(ct_info["study_date"]) if ct_info["study_date"] is not None else None
        )
        study_date_fmt = format_dicom_date(ct_info["study_date"])

        results.append(
            {
                "patient_id": patient_id,
                "study_name": study_dir.name,
                "study_date_raw": study_date_raw,
                "study_date_fmt": study_date_fmt,
                "ct_series_name": ct_dir.name,
                "ct_series_path": str(ct_dir),
                "seg_origin": seg_origin,
                "seg_label": seg_label,
                "seg_path": str(seg_path),
                "n_lesions_annotated": int(n_lesions_annotated),
                "slice_index": [lesion["slice_index"] for lesion in lesions_info],
                "lesions": lesions_info,
                "dx_mm": float(ct_info["dx_mm"]),
                "dy_mm": float(ct_info["dy_mm"]),
                "dz_mm": float(ct_info["dz_mm"]),
                "ct_volume": ct_vol,
                "seg_volume": seg_vol,
                "ct_paths": [str(p) for p in ct_paths],
                "seg_frames_missed": missed_frames,
            }
        )

    return results


if __name__ == "__main__":
    patient_id = "PATIENT001"

    results = collect_positive_findings_with_arrays(patient_id)
    print(f"Nombre d'examens positifs trouvés : {len(results)}")
    results = add_consecutive_recist_like_to_results(results)
    export_info = export_results_to_data_dir(results)
    print(export_info)

    # for idx, entry in enumerate(results, start=1):
    #     print(
    #         f"[{idx}] {entry['study_date_fmt']} | {entry['study_name']} | "
    #         f"CT={entry['ct_series_name']} | "
    #         f"lésions détectées={len(entry['lesions'])} | "
    #         f"segments annotés={entry['n_lesions_annotated']} | "
    #         f"frames SEG non mappées={len(entry['seg_frames_missed'])}"
    #     )

    # # Affichage conseillé :
    # # lésion courante remplie + autres lésions en contours
    # show_all_entries_with_context(results)
