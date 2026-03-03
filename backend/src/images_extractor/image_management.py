#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import numpy as np
import pydicom
import matplotlib.pyplot as plt
from scipy import ndimage

DATASET_ROOT = Path("/home/jovyan/work/dataset")


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


# =========================================================
# Affichages
# =========================================================


def show_entry_lesions_one_after_another(entry: Dict[str, Any]) -> None:
    """
    Affiche les lésions l'une après l'autre.
    Chaque lésion est montrée sur sa propre slice max,
    avec une couleur différente.
    """
    colors = ["Reds", "Greens", "Blues", "YlOrBr", "Purples", "Oranges", "Greys"]

    for i, lesion in enumerate(entry["lesions"]):
        k = lesion["slice_index"]
        ct_img = entry["ct_volume"][k]
        mask = lesion["seg_volume"][k]

        plt.figure(figsize=(7, 7))
        plt.imshow(ct_img, cmap="gray", vmin=-1000, vmax=400)

        alpha = (mask > 0).astype(float) * 0.45
        plt.imshow(mask, cmap=colors[i % len(colors)], alpha=alpha)

        plt.title(
            f"Date examen : {entry['study_date_fmt']}\n"
            f"{entry['study_name']}\n"
            f"CT : {entry['ct_series_name']}\n"
            f"Lésion {lesion['lesion_id']} / {len(entry['lesions'])}\n"
            f"Slice max = {k} | "
            f"X={lesion['size_x_cm']:.2f} cm, "
            f"Y={lesion['size_y_cm']:.2f} cm, "
            f"Z={lesion['size_z_cm']:.2f} cm"
        )
        plt.axis("off")
        plt.show()


def show_entry_all_lesions_on_each_own_slice(entry: Dict[str, Any]) -> None:
    """
    Pour chaque lésion de référence, affiche sa slice max.
    La lésion courante est remplie en rouge.
    Les autres lésions visibles sur la même coupe sont affichées en contours.
    """
    contour_colors = [
        "lime",
        "cyan",
        "yellow",
        "magenta",
        "orange",
        "white",
        "deepskyblue",
    ]

    for i, lesion_ref in enumerate(entry["lesions"]):
        k = lesion_ref["slice_index"]
        ct_img = entry["ct_volume"][k]

        plt.figure(figsize=(7, 7))
        plt.imshow(ct_img, cmap="gray", vmin=-1000, vmax=400)

        for j, lesion in enumerate(entry["lesions"]):
            if k >= lesion["seg_volume"].shape[0]:
                continue

            mask_2d = lesion["seg_volume"][k] > 0
            if not np.any(mask_2d):
                continue

            if j == i:
                overlay = np.ma.masked_where(~mask_2d, mask_2d.astype(float))
                plt.imshow(overlay, cmap="Reds", alpha=0.35)
                plt.contour(
                    mask_2d.astype(float), levels=[0.5], colors=["red"], linewidths=2.5
                )
            else:
                c = contour_colors[j % len(contour_colors)]
                plt.contour(
                    mask_2d.astype(float), levels=[0.5], colors=[c], linewidths=1.8
                )

        txt = " | ".join(
            [
                f"L{lesion['lesion_id']}: slice={lesion['slice_index']}"
                for lesion in entry["lesions"]
            ]
        )

        plt.title(
            f"Date examen : {entry['study_date_fmt']}\n"
            f"{entry['study_name']}\n"
            f"CT : {entry['ct_series_name']} | Lésion de référence = {lesion_ref['lesion_id']}\n"
            f"{txt}",
            fontsize=10,
        )
        plt.axis("off")
        plt.show()


def show_all_entries_lesion_by_lesion(results: List[Dict[str, Any]]) -> None:
    """
    Parcourt tous les examens et affiche toutes les lésions,
    l'une après l'autre.
    """
    for entry in results:
        show_entry_lesions_one_after_another(entry)


def show_all_entries_with_context(results: List[Dict[str, Any]]) -> None:
    """
    Parcourt tous les examens et affiche chaque lésion
    avec les autres lésions visibles sur la même coupe.
    """
    for entry in results:
        show_entry_all_lesions_on_each_own_slice(entry)


# =========================================================
# Utilisation
# =========================================================

if __name__ == "__main__":
    patient_id = "PATIENT001"

    results = collect_positive_findings_with_arrays(patient_id)
    print(f"Nombre d'examens positifs trouvés : {len(results)}")

    for idx, entry in enumerate(results, start=1):
        print(
            f"[{idx}] {entry['study_date_fmt']} | {entry['study_name']} | "
            f"CT={entry['ct_series_name']} | "
            f"lésions détectées={len(entry['lesions'])} | "
            f"segments annotés={entry['n_lesions_annotated']} | "
            f"frames SEG non mappées={len(entry['seg_frames_missed'])}"
        )

    # Affichage conseillé :
    # lésion courante remplie + autres lésions en contours
    show_all_entries_with_context(results)

    # Si tu veux au contraire une figure par lésion seule :
    # show_all_entries_lesion_by_lesion(results)
