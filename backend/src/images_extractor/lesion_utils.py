#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb 28 20:51:37 2026

@author: moli
"""

from typing import Optional, Dict, Any, List

import numpy as np
from scipy import ndimage

# =========================================================
# Analyse multi-lésions
# =========================================================


def best_slice_index(mask_3d: np.ndarray) -> Optional[int]:
    """
    Retourne l'index z où l'aire segmentée est maximale.
    """
    areas = (mask_3d > 0).sum(axis=(1, 2))
    if areas.max() == 0:
        return None
    return int(np.argmax(areas))


def extract_connected_lesions(seg_vol: np.ndarray) -> List[np.ndarray]:
    """
    Détecte toutes les composantes connexes 3D.
    Retourne une liste de masques booléens triés par taille décroissante.
    """
    mask = seg_vol > 0
    if not np.any(mask):
        return []

    structure = np.ones((3, 3, 3), dtype=np.uint8)
    labeled, num = ndimage.label(mask, structure=structure)

    if num == 0:
        return []

    counts = np.bincount(labeled.ravel())
    counts[0] = 0

    labels_sorted = np.argsort(counts)[::-1]
    labels_sorted = [lab for lab in labels_sorted if lab != 0 and counts[lab] > 0]

    lesions = []
    for lab in labels_sorted:
        lesions.append(labeled == lab)

    return lesions


def compute_ellipsoid_sizes_from_mask(
    mask_3d: np.ndarray, dx_mm: float, dy_mm: float, dz_mm: float
) -> Optional[Dict[str, Any]]:
    """
    Calcule les tailles X,Y,Z en cm pour une lésion isolée,
    par approximation ellipsoïdale 3D.
    """
    inds = np.argwhere(mask_3d)
    if inds.shape[0] < 3:
        return None

    z_mm = inds[:, 0] * dz_mm
    y_mm = inds[:, 1] * dy_mm
    x_mm = inds[:, 2] * dx_mm

    pts = np.column_stack([x_mm, y_mm, z_mm])

    center = pts.mean(axis=0)
    pts_centered = pts - center

    cov = np.cov(pts_centered, rowvar=False)

    evals, evecs = np.linalg.eigh(cov)
    order = np.argsort(evals)[::-1]
    evals = np.maximum(evals[order], 0.0)
    evecs = evecs[:, order]

    lengths_mm = 2.0 * np.sqrt(5.0 * evals)

    return {
        "center_mm": center,
        "eigenvalues": evals,
        "eigenvectors": evecs,
        "size_x_cm": float(lengths_mm[0] / 10.0),
        "size_y_cm": float(lengths_mm[1] / 10.0),
        "size_z_cm": float(lengths_mm[2] / 10.0),
        "n_voxels": int(mask_3d.sum()),
    }


def build_lesions_info(
    seg_vol: np.ndarray, dx_mm: float, dy_mm: float, dz_mm: float
) -> List[Dict[str, Any]]:
    """
    Construit les infos de chaque lésion connexe.
    Chaque lésion possède :
    - mask
    - seg_volume
    - slice_index
    - tailles X,Y,Z
    """
    lesion_masks = extract_connected_lesions(seg_vol)

    lesions_info = []
    for i, lesion_mask in enumerate(lesion_masks, start=1):
        geom = compute_ellipsoid_sizes_from_mask(
            lesion_mask,
            dx_mm=dx_mm,
            dy_mm=dy_mm,
            dz_mm=dz_mm,
        )
        if geom is None:
            continue

        k = best_slice_index(lesion_mask.astype(np.uint8))
        if k is None:
            continue

        lesion_mask_uint8 = lesion_mask.astype(np.uint8)

        lesions_info.append(
            {
                "lesion_id": i,
                "mask": lesion_mask_uint8,
                "seg_volume": lesion_mask_uint8,
                "slice_index": int(k),
                "size_x_cm": float(geom["size_x_cm"]),
                "size_y_cm": float(geom["size_y_cm"]),
                "size_z_cm": float(geom["size_z_cm"]),
                "center_mm": geom["center_mm"],
                "n_voxels": int(geom["n_voxels"]),
            }
        )

    return lesions_info


def build_lesions_info_from_aligned_segments(
    seg_by_segment: Dict[int, np.ndarray], dx_mm: float, dy_mm: float, dz_mm: float
) -> List[Dict[str, Any]]:
    """
    Extrait les lésions à partir de chaque segment aligné sur le CT.
    Cela évite de fusionner artificiellement plusieurs segments.
    """
    all_lesions = []

    for seg_num in sorted(seg_by_segment.keys()):
        seg_vol = seg_by_segment[seg_num]
        lesions = build_lesions_info(seg_vol, dx_mm=dx_mm, dy_mm=dy_mm, dz_mm=dz_mm)

        for lesion in lesions:
            lesion["segment_number"] = int(seg_num)
            all_lesions.append(lesion)

    all_lesions.sort(key=lambda d: d["n_voxels"], reverse=True)

    for i, lesion in enumerate(all_lesions, start=1):
        lesion["lesion_id"] = i

    return all_lesions
