"""Pipeline — full image analysis and report generation pipeline."""

import json
from pathlib import Path

from .images_extractor.pipeline_image import collect_positive_findings_with_arrays
from .images_extractor.display_utils import (
    add_consecutive_recist_like_to_results,
    export_results_to_data_dir,
)
from .report_generator.report_generator import create_report

# Paths derived from this file's location:
#   backend/src/pipeline.py
#   parents[0] = src/   parents[1] = backend/   parents[2] = radio-gaga/
_REPO_ROOT = Path(__file__).parents[2]
_DATA_DIR = _REPO_ROOT / "data"
_STUDIES_DIR = _DATA_DIR / "studies"


def _ensure_light_json(patient_id: str) -> Path:
    """
    Run steps 1-3 of the pipeline (collect → RECIST → export) if the
    cached results_light.json does not yet exist, then return its path.
    """
    json_path = _DATA_DIR / patient_id / "results_light.json"
    if not json_path.exists():
        results = collect_positive_findings_with_arrays(patient_id, _STUDIES_DIR)
        if not results:
            raise ValueError(f"No positive findings for patient {patient_id}")
        results = add_consecutive_recist_like_to_results(results)
        export_info = export_results_to_data_dir(results, base_dir=_REPO_ROOT)
        json_path = export_info["json_path"]
    return json_path


def get_lesions(patient_id: str, study_name: str) -> dict:
    """
    Run lesion detection for one study (steps 1-3) and return lesion metadata.
    Report generation is NOT performed here.

    Returns a dict with keys:
      status, exam_index, lesions, slice_count, images_base_url
    """
    json_path = _ensure_light_json(patient_id)

    with open(json_path) as f:
        light_results = json.load(f)

    study_entry = next(
        (r for r in light_results if r["study_name"] == study_name),
        light_results[-1],
    )

    return {
        "status": "ok",
        "exam_index": study_entry.get("exam_index", 0),
        "lesions": study_entry.get("lesions", []),
        "slice_count": len(study_entry.get("ct_paths", [])),
        "images_base_url": f"/data/{patient_id}",
    }


def generate_report(patient_id: str, study_name: str) -> dict:
    """
    Generate the VLM radiology report for one study (step 4).
    Assumes lesion detection (steps 1-3) has already run.

    Returns a dict with keys:
      status, report (StructuredReport as dict)
    """
    json_path = _ensure_light_json(patient_id)

    with open(json_path) as f:
        light_results = json.load(f)

    study_entry = next(
        (r for r in light_results if r["study_name"] == study_name),
        light_results[-1],
    )

    structured_report = create_report(
        patient_id=patient_id,
        path_to_dataset=str(_STUDIES_DIR),
        study_name=study_entry["study_name"],
        path_to_seg_file=study_entry["seg_path"],
        path_to_image_analysis_results=str(json_path),
    )

    return {
        "status": "ok",
        "report": structured_report.model_dump(),
    }
