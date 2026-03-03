#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb 28 20:52:46 2026

@author: moli
"""

from pathlib import Path
from typing import Dict, Any, List
import json
import re

import numpy as np
import matplotlib.pyplot as plt

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
# Sauvegarde
# =========================================================


def _exam_dirname(exam_index: int) -> str:
    """
    Nom de dossier standard pour un examen.
    """
    return f"exam_{exam_index:04d}"


def _ct_only_filename(exam_index: int, slice_index: int) -> str:
    """
    Nom de fichier pour une tranche CT seule.
    """
    return f"exam_{exam_index:04d}__slice_{slice_index:04d}__ct_only.png"


def _with_seg_filename(exam_index: int, slice_index: int) -> str:
    """
    Nom de fichier pour une tranche CT avec segmentation.
    """
    return f"exam_{exam_index:04d}__slice_{slice_index:04d}__with_seg.png"


def lesion_slice_range(mask_3d: np.ndarray) -> tuple[int | None, int | None]:
    """
    Retourne les indices min et max des slices où la lésion est présente.
    """
    if mask_3d is None or mask_3d.ndim != 3:
        return None, None

    presence = np.any(mask_3d > 0, axis=(1, 2))
    indices = np.where(presence)[0]

    if len(indices) == 0:
        return None, None

    return int(indices[0]), int(indices[-1])


def compute_recist_like_lesion_size_cm(lesion: Dict[str, Any]) -> float | None:
    """
    Taille RECIST-like d'une lésion :
    maximum des trois tailles ellipsoïdales.
    """
    sx = lesion.get("size_x_cm", None)
    sy = lesion.get("size_y_cm", None)
    sz = lesion.get("size_z_cm", None)

    values = [v for v in (sx, sy, sz) if v is not None]

    if len(values) == 0:
        return None

    return float(max(values))


def compute_exam_recist_like_sum_cm(entry: Dict[str, Any]) -> float:
    """
    Somme RECIST-like de l'examen :
    somme des tailles RECIST-like de toutes les lésions.
    """
    total = 0.0

    for lesion in entry.get("lesions", []):
        value = compute_recist_like_lesion_size_cm(lesion)
        if value is not None:
            total += value

    return float(total)


def add_consecutive_recist_like_to_results(
    results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Ajoute dans chaque examen une information RECIST-like
    calculée par comparaison avec l'examen précédent.

    Convention :
    - exam 0 : pas de comparaison précédente -> champs à None
    - exam i : comparaison avec exam i-1

    Champs ajoutés dans chaque entry :
    - exam_recist_like_sum_cm
    - recist_like_prev_sum_cm
    - recist_like_delta_abs_cm
    - recist_like_delta_pct
    - recist_like_category_prev
    """
    if len(results) == 0:
        return results

    exam_sums = [compute_exam_recist_like_sum_cm(entry) for entry in results]

    for i, entry in enumerate(results):
        current_sum = exam_sums[i]
        entry["exam_recist_like_sum_cm"] = current_sum

        if i == 0:
            entry["recist_like_prev_sum_cm"] = None
            entry["recist_like_delta_abs_cm"] = None
            entry["recist_like_delta_pct"] = None
            entry["recist_like_category_prev"] = None
            continue

        previous_sum = exam_sums[i - 1]
        entry["recist_like_prev_sum_cm"] = previous_sum

        delta_abs = current_sum - previous_sum
        entry["recist_like_delta_abs_cm"] = float(delta_abs)

        if previous_sum == 0:
            delta_pct = None
        else:
            delta_pct = float(100.0 * delta_abs / previous_sum)

        entry["recist_like_delta_pct"] = delta_pct

        # Catégorie simple basée sur l'examen précédent
        # Ce n'est PAS RECIST 1.1 strict, seulement un proxy longitudinal
        if delta_pct is None:
            category = None
        elif delta_pct <= -30.0:
            category = "PR-like"
        elif delta_pct >= 20.0:
            category = "PD-like"
        else:
            category = "SD-like"

        entry["recist_like_category_prev"] = category

    return results


def make_results_light(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Construit une version légère de results sans les grosses matrices.
    Ajoute aussi l'indice d'examen et les bornes slice_min/slice_max
    de présence de segmentation pour chaque lésion.
    """
    light_results = []

    for exam_index, entry in enumerate(results):
        new_entry = {}

        for key, value in entry.items():
            if key in {"ct_volume", "seg_volume"}:
                new_entry[key] = None
            elif key == "lesions":
                new_lesions = []

                for lesion in value:
                    new_lesion = {}

                    lesion_mask = lesion.get("seg_volume", None)
                    slice_min, slice_max = lesion_slice_range(lesion_mask)

                    for lk, lv in lesion.items():
                        if lk in {"mask", "seg_volume"}:
                            new_lesion[lk] = None
                        elif isinstance(lv, np.ndarray):
                            new_lesion[lk] = lv.tolist()
                        elif isinstance(lv, (np.integer, np.floating)):
                            new_lesion[lk] = lv.item()
                        else:
                            new_lesion[lk] = lv

                    new_lesion["slice_min"] = slice_min
                    new_lesion["slice_max"] = slice_max

                    new_lesions.append(new_lesion)

                new_entry[key] = new_lesions

            elif isinstance(value, np.ndarray):
                new_entry[key] = None
            elif isinstance(value, (np.integer, np.floating)):
                new_entry[key] = value.item()
            else:
                new_entry[key] = value

        new_entry["exam_index"] = exam_index
        light_results.append(new_entry)

    return light_results


def save_results_light_json(results: List[Dict[str, Any]], output_dir: Path) -> Path:
    """
    Sauvegarde une version légère de results en JSON.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    light_results = make_results_light(results)
    json_path = output_dir / "results_light.json"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(light_results, f, indent=2, ensure_ascii=False)

    return json_path


def save_all_slices_without_seg(
    entry: Dict[str, Any], exam_index: int, output_dir: Path
) -> List[Path]:
    """
    Sauvegarde toutes les tranches CT d'un examen sans segmentation.
    """
    exam_dir = output_dir / _exam_dirname(exam_index)
    exam_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    ct_vol = entry["ct_volume"]
    n_slices = ct_vol.shape[0]

    for slice_index in range(n_slices):
        ct_img = ct_vol[slice_index]

        out_path = exam_dir / _ct_only_filename(exam_index, slice_index)

        plt.figure(figsize=(7, 7))
        plt.imshow(ct_img, cmap="gray", vmin=-1000, vmax=400)
        plt.axis("off")
        plt.tight_layout(pad=0)
        plt.savefig(out_path, dpi=150, bbox_inches="tight", pad_inches=0)
        plt.close()

        saved_paths.append(out_path)

    return saved_paths


def slice_has_any_segmentation(entry: Dict[str, Any], slice_index: int) -> bool:
    """
    Indique si au moins une lésion est présente sur la tranche demandée.
    """
    for lesion in entry["lesions"]:
        seg_vol = lesion.get("seg_volume", None)
        if seg_vol is None:
            continue
        if slice_index >= seg_vol.shape[0]:
            continue
        if np.any(seg_vol[slice_index] > 0):
            return True
    return False


def save_slices_with_seg_only_when_needed(
    entry: Dict[str, Any], exam_index: int, output_dir: Path
) -> List[Path]:
    """
    Sauvegarde uniquement les tranches où au moins une segmentation est présente.
    """
    exam_dir = output_dir / _exam_dirname(exam_index)
    exam_dir.mkdir(parents=True, exist_ok=True)

    contour_colors = [
        "red",
        "lime",
        "cyan",
        "yellow",
        "magenta",
        "orange",
        "white",
        "deepskyblue",
    ]
    saved_paths = []

    ct_vol = entry["ct_volume"]
    n_slices = ct_vol.shape[0]

    for slice_index in range(n_slices):
        if not slice_has_any_segmentation(entry, slice_index):
            continue

        ct_img = ct_vol[slice_index]
        out_path = exam_dir / _with_seg_filename(exam_index, slice_index)

        plt.figure(figsize=(7, 7))
        plt.imshow(ct_img, cmap="gray", vmin=-1000, vmax=400)

        for lesion_index, lesion in enumerate(entry["lesions"]):
            seg_vol = lesion.get("seg_volume", None)
            if seg_vol is None:
                continue
            if slice_index >= seg_vol.shape[0]:
                continue

            mask_2d = seg_vol[slice_index] > 0
            if not np.any(mask_2d):
                continue

            color = contour_colors[lesion_index % len(contour_colors)]
            plt.contour(
                mask_2d.astype(float), levels=[0.5], colors=[color], linewidths=1.5
            )

        plt.axis("off")
        plt.tight_layout(pad=0)
        plt.savefig(out_path, dpi=150, bbox_inches="tight", pad_inches=0)
        plt.close()

        saved_paths.append(out_path)

    return saved_paths


def export_results_to_data_dir(
    results: List[Dict[str, Any]], base_dir: Path | None = None
) -> Dict[str, Any]:
    """
    Exporte dans ./data :
    - un JSON léger
    - toutes les tranches CT seules
    - uniquement les tranches avec segmentation pour les images with_seg
    """
    if base_dir is None:
        base_dir = Path.cwd()

    # data_dir = base_dir / "data"
    data_dir = base_dir / "data" / str(results[0]["patient_id"])
    ct_only_dir = data_dir / "images_ct_only"
    with_seg_dir = data_dir / "images_with_seg"

    data_dir.mkdir(parents=True, exist_ok=True)
    ct_only_dir.mkdir(parents=True, exist_ok=True)
    with_seg_dir.mkdir(parents=True, exist_ok=True)

    json_path = save_results_light_json(results, data_dir)

    n_ct_only = 0
    n_with_seg = 0

    for exam_index, entry in enumerate(results):
        n_ct_only += len(save_all_slices_without_seg(entry, exam_index, ct_only_dir))
        n_with_seg += len(
            save_slices_with_seg_only_when_needed(entry, exam_index, with_seg_dir)
        )

    return {
        "data_dir": data_dir,
        "json_path": json_path,
        "images_ct_only_dir": ct_only_dir,
        "images_with_seg_dir": with_seg_dir,
        "n_entries": len(results),
        "n_images_ct_only": n_ct_only,
        "n_images_with_seg": n_with_seg,
    }
