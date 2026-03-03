#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb 28 20:50:30 2026

@author: moli
"""

from typing import Optional, Dict, Any

import numpy as np

# =========================================================
# Reconstruction correcte du SEG
# =========================================================


def get_seg_frame_referenced_uid(seg_ds, frame_index: int) -> Optional[str]:
    """
    Retourne le SOPInstanceUID CT référencé par une frame SEG.
    """
    try:
        pffg = seg_ds.PerFrameFunctionalGroupsSequence[frame_index]
    except Exception:
        return None

    try:
        deriv_seq = getattr(pffg, "DerivationImageSequence", None)
        if deriv_seq and len(deriv_seq) > 0:
            src_seq = getattr(deriv_seq[0], "SourceImageSequence", None)
            if src_seq and len(src_seq) > 0:
                uid = getattr(src_seq[0], "ReferencedSOPInstanceUID", None)
                if uid is not None:
                    return str(uid)
    except Exception:
        pass

    return None


def get_seg_frame_segment_number(seg_ds, frame_index: int) -> int:
    """
    Retourne le numéro de segment référencé par une frame SEG.
    """
    try:
        pffg = seg_ds.PerFrameFunctionalGroupsSequence[frame_index]
        seg_id_seq = getattr(pffg, "SegmentIdentificationSequence", None)
        if seg_id_seq and len(seg_id_seq) > 0:
            seg_num = getattr(seg_id_seq[0], "ReferencedSegmentNumber", None)
            if seg_num is not None:
                return int(seg_num)
    except Exception:
        pass

    return 1


def build_dense_seg_volumes_from_seg(seg_ds, ct_info: Dict[str, Any]):
    """
    Reconstruit des volumes SEG denses alignés sur les slices CT.

    Retourne :
    - union_vol : union de tous les segments, shape = (n_ct, H, W)
    - seg_by_segment : dict {segment_number: volume_dense}
    - missed_frames : liste des frames SEG non mappées
    """
    arr = seg_ds.pixel_array.astype(np.uint8)

    if arr.ndim == 2:
        arr = arr[np.newaxis, ...]

    if arr.ndim != 3:
        raise ValueError(f"SEG inattendu, shape pixel_array = {arr.shape}")

    n_ct = len(ct_info["ordered_files"])
    h, w = arr.shape[1], arr.shape[2]

    union_vol = np.zeros((n_ct, h, w), dtype=np.uint8)
    seg_by_segment = {}
    missed_frames = []

    for i in range(arr.shape[0]):
        ref_uid = get_seg_frame_referenced_uid(seg_ds, i)
        if ref_uid is None or ref_uid not in ct_info["uid_to_index"]:
            missed_frames.append(i)
            continue

        z_idx = ct_info["uid_to_index"][ref_uid]
        seg_num = get_seg_frame_segment_number(seg_ds, i)
        frame_mask = (arr[i] > 0).astype(np.uint8)

        if seg_num not in seg_by_segment:
            seg_by_segment[seg_num] = np.zeros((n_ct, h, w), dtype=np.uint8)

        seg_by_segment[seg_num][z_idx] = np.maximum(
            seg_by_segment[seg_num][z_idx], frame_mask
        )
        union_vol[z_idx] = np.maximum(union_vol[z_idx], frame_mask)

    if np.count_nonzero(union_vol) == 0:
        raise ValueError(
            "Impossible de reconstruire le SEG sur le CT. "
            "Les frames SEG ne pointent pas correctement vers les SOPInstanceUID du CT."
        )

    return union_vol, seg_by_segment, missed_frames
