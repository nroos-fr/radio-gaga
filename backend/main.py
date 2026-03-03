"""
Radio-Gaga Backend — FastAPI application.

Exposes endpoints for retrieving patient DICOM metadata
and generating radiology reports with segmentation masks.
"""

import glob
import json
import os
import urllib.parse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
from src.metadata_extractor.metadata_extractor import *
from src.pipeline import (
    get_lesions as _get_lesions,
    generate_report as _generate_report,
)

app = FastAPI(
    title="Radio-Gaga Backend",
    description="Medical imaging backend for Hackathon Unboxed 2026",
    version="0.1.0",
)

# ── CORS — allow the Vite dev server (and any origin) to call us ─────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Data directories ─────────────────────────────────────────────────────────
# DATA_DIR  → served statically at /data/* (Cornerstone WADO-URI root)
# STUDIES_DIR → patient/study folder hierarchy used by all API endpoints
DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "../data")
)
STUDIES_DIR = os.path.join(DATA_DIR, "studies")

# Map of short key → DICOM folder name inside each study
SERIES_FOLDERS = {
    "torax": "CT CEV torax",
    "abdomen": "CT CEV abdomen",
    "columna": "CT SAG COLUMNA 3mm",
}


# ── Request / Response models ────────────────────────────────────────────────


class DatasetRequest(BaseModel):
    dataset_path: str


class PatientRequest(BaseModel):
    patient_path: str


class PatientDataResponse(BaseModel):
    patient: dict
    studies: list[dict]


class ReportAndMaskResponse(BaseModel):
    report: str
    mask_path: str | None


# ── Health check endpoint ────────────────────────────────────────────────────


@app.get("/api/health")
def health_check():
    """Return a simple status response to confirm the server is running."""
    return {"status": "ok"}


# ── Patient / study listing endpoint ─────────────────────────────────────────


@app.get("/api/patients")
def list_patients():
    """
    Return studies grouped by patient folder.
    STUDIES_DIR layout:  <patient_dir>/<study_dir>/<series_dir>/*.dcm
    Shape: { patients: [ { patient_id, patient_name, patient_sex, patient_age,
                            studies: [ { study_id, study_name } ] } ] }
    """
    grouped: dict[str, dict] = {}
    for patient_dir in sorted(Path(STUDIES_DIR).iterdir()):
        if not patient_dir.is_dir():
            continue
        pid = patient_dir.name
        try:
            meta = extract_patient_metadata(patient_dir)
        except Exception:
            meta = {}

        grouped[pid] = {
            "patient_id": pid,
            "patient_name": meta.get("PatientName", ""),
            "patient_sex": meta.get("PatientSex", ""),
            "patient_age": meta.get("PatientAge"),
            "studies": [],
        }
        raw_studies = []
        for study_dir in sorted(patient_dir.iterdir()):
            if not study_dir.is_dir():
                continue
            # Read StudyDate from the first DICOM file found in this study folder
            study_date_raw = ""
            dcm_files = glob.glob(
                os.path.join(str(study_dir), "**", "*.dcm"), recursive=True
            )
            if dcm_files:
                try:
                    import pydicom

                    ds = pydicom.dcmread(sorted(dcm_files)[0], stop_before_pixels=True)
                    study_date_raw = str(
                        getattr(ds, "StudyDate", "") or getattr(ds, "ContentDate", "")
                    )
                except Exception:
                    pass
            # Format as DD/MM/YYYY for display
            if study_date_raw and len(study_date_raw) == 8:
                study_date_fmt = (
                    f"{study_date_raw[6:8]}/{study_date_raw[4:6]}/{study_date_raw[:4]}"
                )
            else:
                study_date_fmt = ""
            raw_studies.append(
                {
                    "study_id": f"{patient_dir.name}/{study_dir.name}",
                    "study_name": study_dir.name,
                    "study_date_raw": study_date_raw,
                    "study_date_fmt": study_date_fmt,
                }
            )
        # Sort studies by date ascending (unknown dates go to the end)
        grouped[pid]["studies"] = sorted(
            raw_studies, key=lambda s: s["study_date_raw"] or "99999999"
        )

    return {"patients": list(grouped.values())}


# ── Series listing endpoint ───────────────────────────────────────────────────


@app.get("/api/series/{study_path:path}")
def get_series_files(study_path: str):
    """
    Return sorted DICOM file URLs grouped by series key
    (torax / abdomen / columna) for the requested study.
    study_path = "<patient_dir>/<study_dir>"  (URL-encoded by the client)
    Each URL is root-relative: /data/studies/<patient>/<study>/.../CT000001.dcm
    """
    study_dir = Path(STUDIES_DIR) / study_path
    if not study_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Study not found: {study_path}")

    result: dict[str, list[str]] = {}
    for key, folder_name in SERIES_FOLDERS.items():
        pattern = os.path.join(str(study_dir), "**", folder_name, "*.dcm")
        files = sorted(glob.glob(pattern, recursive=True))
        result[key] = [
            "/data/"
            + urllib.parse.quote(os.path.relpath(f, DATA_DIR).replace(os.sep, "/"))
            for f in files
        ]
    return result


# ── Existing endpoints ────────────────────────────────────────────────────────


@app.post("/get_patients_list")
async def get_patients_list_endpoint(request: DatasetRequest):
    """List all patients found in the dataset directory."""
    try:
        patients = get_patient_list(request.dataset_path)
        return {"patients": patients}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/get_patient_data", response_model=PatientDataResponse)
async def get_patient_data_endpoint(request: PatientRequest):
    """Return patient, study, and series metadata from a DICOM folder."""
    try:
        patient_path = Path(request.patient_path)
        patient = extract_patient_metadata(patient_path)
        studies = []
        for study_dir in patient_path.iterdir():
            if study_dir.is_dir():
                study_metadata = extract_study_metadata(study_dir)
                studies.append(study_metadata)
        return {"patient": patient, "studies": studies}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/get_report_and_mask", response_model=ReportAndMaskResponse)
async def get_report_and_mask_endpoint(request: PatientRequest):
    """Generate a radiology report and segmentation mask for a patient."""
    try:
        result = get_report_and_mask(request.patient_path)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Segmentation contours endpoint ───────────────────────────────────────────


@app.get("/api/seg/{study_path:path}")
def get_segmentation(study_path: str):
    """
    Extract segmentation contour points from DICOM SEG files.
    study_path = "<patient_dir>/<study_dir>"  (URL-encoded by the client)
    Returns contour paths (ordered image pixel coordinates) grouped by series key
    and CT slice index.
    Shape: { torax: { "<ct_idx>": [[[col,row], ...], ...] }, abdomen: ..., columna: ... }
    """
    import cv2
    import pydicom
    import numpy as np

    study_dir = Path(STUDIES_DIR) / study_path
    if not study_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Study not found: {study_path}")

    # Build SOP UID → (series_key, ct_index) map
    uid_to_series_idx: dict[str, tuple[str, int]] = {}
    for key, folder_name in SERIES_FOLDERS.items():
        pattern = os.path.join(str(study_dir), "**", folder_name, "*.dcm")
        ct_files = sorted(glob.glob(pattern, recursive=True))
        for i, ct_path in enumerate(ct_files):
            try:
                ct_ds = pydicom.dcmread(ct_path, stop_before_pixels=True)
                uid_to_series_idx[str(ct_ds.SOPInstanceUID)] = (key, i)
            except Exception:
                pass

    result: dict[str, dict] = {"torax": {}, "abdomen": {}, "columna": {}}

    for seg_path in sorted(study_dir.glob("**/SE*.dcm")):
        try:
            ds = pydicom.dcmread(str(seg_path))
        except Exception:
            continue
        if getattr(ds, "Modality", "") != "SEG":
            continue

        arr = ds.pixel_array  # (n_frames, rows, cols)
        frames = getattr(ds, "PerFrameFunctionalGroupsSequence", [])

        for frame_idx, frame in enumerate(frames):
            try:
                ref_uid = str(
                    frame.DerivationImageSequence[0]
                    .SourceImageSequence[0]
                    .ReferencedSOPInstanceUID
                )
            except Exception:
                continue

            info = uid_to_series_idx.get(ref_uid)
            if info is None:
                continue
            series_key, ct_idx = info

            mask = arr[frame_idx].astype(np.uint8)
            if not mask.any():
                continue

            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_TC89_KCOS
            )
            pts_list = [c.reshape(-1, 2).tolist() for c in contours if len(c) >= 3]
            if pts_list:
                result[series_key][str(ct_idx)] = pts_list

    return {k: (v if v else None) for k, v in result.items()}


# ── Shared helper ─────────────────────────────────────────────────────────────


def _parse_study_path(study_path: str) -> tuple[str, str]:
    """Return (patient_id, study_folder) from a URL study_path segment."""
    patient_folder = study_path.split("/")[0]
    patient_id = patient_folder.split(" ")[0]  # "PATIENT001 PATIENT001" → "PATIENT001"
    parts = study_path.split("/", 1)
    study_folder = parts[1] if len(parts) > 1 else ""
    return patient_id, study_folder


def _get_patient_meta(patient_id: str) -> dict:
    """Return {patient_sex, patient_age} for patient_id, with empty fallbacks."""
    patient_dir = Path(STUDIES_DIR) / patient_id
    # Try the "<id> <id>" directory naming convention used in the studies tree
    if not patient_dir.is_dir():
        for d in Path(STUDIES_DIR).iterdir():
            if d.is_dir() and d.name.startswith(patient_id):
                patient_dir = d
                break
    try:
        meta = extract_patient_metadata(patient_dir)
        return {
            "patient_sex": meta.get("PatientSex", "") or "",
            "patient_age": meta.get("PatientAge"),
        }
    except Exception:
        return {"patient_sex": "", "patient_age": None}


def _load_mock_entry(study_folder: str) -> dict:
    """Load and return the mock results_light.json entry for study_folder."""
    results_path = os.path.join(DATA_DIR, "mock_data", "results_light.json")
    try:
        with open(results_path) as f:
            all_results = json.load(f)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Could not read results_light.json: {exc}"
        )
    entry = next((r for r in all_results if r["study_name"] == study_folder), None)
    if entry is None:
        raise HTTPException(
            status_code=404, detail=f"No mock data for study: {study_folder}"
        )
    return entry


# ── Lesion detection endpoint ─────────────────────────────────────────────────


@app.post("/api/lesions/{study_path:path}")
async def detect_lesions(study_path: str):
    """
    Run lesion detection for a study and return lesion metadata + slice info.
    Does NOT generate the report — call /api/report/{study_path} separately.

    study_path = "<patient_dir>/<study_dir>"  (URL-encoded by the client)

    Response shape:
      { status, exam_index, lesions, n_lesions, slice_count, images_base_url }
    """
    patient_id, study_folder = _parse_study_path(study_path)

    patient_meta = _get_patient_meta(patient_id)

    # ── Attempt real pipeline ─────────────────────────────────────────────────
    try:
        result = _get_lesions(patient_id, study_folder)
        if result.get("status") == "ok":
            return {
                "status": "ok",
                "exam_index": result.get("exam_index", 0),
                "lesions": result.get("lesions", []),
                "n_lesions": len(result.get("lesions", [])),
                "slice_count": result.get("slice_count", 0),
                "images_base_url": result.get("images_base_url", f"/data/{patient_id}"),
                **patient_meta,
            }
    except Exception as exc:
        print(f"[lesions] Pipeline error for {patient_id}/{study_folder}: {exc}")

    # ── Mock fallback ─────────────────────────────────────────────────────────
    if patient_id != "PATIENT001":
        return {
            "status": "skipped",
            "message": "No analysis available for this patient.",
        }

    entry = _load_mock_entry(study_folder)
    lesions = entry["lesions"]
    return {
        "status": "ok",
        "exam_index": entry["exam_index"],
        "lesions": lesions,
        "n_lesions": entry["n_lesions_annotated"],
        "slice_count": len(entry["ct_paths"]),
        "images_base_url": "/data/mock_data",
        **patient_meta,
    }


# ── Report generation endpoint ────────────────────────────────────────────────


@app.post("/api/report/{study_path:path}")
async def generate_report(study_path: str):
    """
    Generate the VLM radiology report for a study.
    Lesion detection (/api/lesions) should have been called first.

    study_path = "<patient_dir>/<study_dir>"  (URL-encoded by the client)

    Response shape:
      { status, report_source, report: { reasons_for_study, study_technique,
                                         statements, conclusion } }
    """
    patient_id, study_folder = _parse_study_path(study_path)

    # ── Attempt real VLM report ───────────────────────────────────────────────
    try:
        result = _generate_report(patient_id, study_folder)
        if result.get("status") == "ok":
            return {
                "status": "ok",
                "report_source": "ai",
                "report": result["report"],
            }
    except Exception as exc:
        print(f"[report] Pipeline error for {patient_id}/{study_folder}: {exc}")

    # ── Mock fallback ─────────────────────────────────────────────────────────
    if patient_id != "PATIENT001":
        return {"status": "skipped", "message": "No report available for this patient."}

    entry = _load_mock_entry(study_folder)
    lesions = entry["lesions"]
    n = len(lesions)
    largest = max(lesions, key=lambda l: l["size_x_cm"])

    mock_report = {
        "reasons_for_study": (
            f"Oncological follow-up in patient with pulmonary nodule{'s' if n > 1 else ''}. "
            f"CT performed on {entry['study_date_fmt']}."
        ),
        "study_technique": (
            f"Thoracic CT ({entry['ct_series_name']}) performed after IV contrast administration."
        ),
        "statements": [
            {
                "text": (
                    f"Pulmonary nodule in {entry['ct_series_name']}: "
                    f"{l['size_x_cm']:.1f}\u00d7{l['size_y_cm']:.1f}\u00d7{l['size_z_cm']:.1f} cm "
                    f"(image {l['slice_index']})."
                )
            }
            for l in lesions
        ],
        "conclusion": (
            f"{'Multiple' if n > 1 else 'Solitary'} pulmonary nodule{'s' if n > 1 else ''} identified. "
            f"Largest lesion {largest['size_x_cm']:.1f}\u00d7{largest['size_y_cm']:.1f} cm "
            f"at slice {largest['slice_index']}. RECIST assessment pending prior exam comparison."
        ),
    }

    return {
        "status": "ok",
        "report_source": "template",
        "report": mock_report,
    }


# ── Static DICOM file server — must be mounted LAST ──────────────────────────
# Serves data/ at /data/* so Cornerstone loads DICOM via:
#   wadouri:/data/studies/<patient>/<study>/CT CEV torax/CT000001.dcm
app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")


# ── Run with: uvicorn main:app --reload ──────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
