"""
Fonction generating the report
"""

import os
import io
import base64
import json
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

import pydicom
import numpy as np
import pandas
from openai import OpenAI
from pydantic import BaseModel, Field, ConfigDict
from PIL import Image

from ..metadata_extractor.metadata_extractor import *

PATH_TO_CLINICAL_DATA = os.path.join(
    os.path.dirname(__file__), "protected-clinical-data.csv"
)


class Hypothesis(BaseModel):
    """A single radiological hypothesis with a truth value."""

    model_config = ConfigDict(extra="forbid")
    statement: str = Field(
        description="The hypothesis statement, e.g. 'Nodule is malignant'"
    )
    image_id: int = Field(
        description="The index of the image slice this hypothesis pertains to, 0 by default"
    )


class RadiologyReport(BaseModel):
    """
    Structured radiology report produced by the VLM via OpenRouter structured outputs.

    Usage with pydantic-ai:
        result = await agent.run(prompt, result_type=RadiologyReport)
        report: RadiologyReport = result.data

    Usage with raw OpenAI client (this module):
        report = create_report(image, metadata, api_key)
        # report is a RadiologyReport instance
    """

    model_config = ConfigDict(extra="forbid")
    background: str = Field(
        description=(
            "Clinical background and description of the imaging findings: "
            "modality, anatomical region, notable structures, and any abnormalities observed."
        )
    )
    hypotheses: list[Hypothesis] = Field(
        description="List of radiological hypotheses evaluated against the image findings."
    )


class ReportStatement(BaseModel):
    """A single radiological finding stated as a self-contained clinical fact."""

    model_config = ConfigDict(extra="forbid")
    text: str = Field(
        description=(
            "One precise clinical statement describing a finding: location, current size, "
            "previous size in parentheses if available, and evolution "
            "(e.g. 'unchanged', 'increased', 'decreased'). No lesion IDs."
        )
    )
    slice_index: int | None = Field(
        default=None,
        description=(
            "The exact 0-based CT slice index (taken from the `slice_index` field in the "
            "provided lesion metrics) where this finding is best visualised. "
            "Must match one of the slice_index values from the metrics exactly. "
            "Set to null only if the finding is not tied to a specific lesion slice."
        ),
    )


class StructuredReport(BaseModel):
    """
    Final structured CT report returned to the frontend.
    Produced by the report-writing LLM using OpenAI structured outputs
    so no post-hoc parsing is needed.
    """

    model_config = ConfigDict(extra="forbid")
    reasons_for_study: str = Field(
        description=(
            "One or two telegraphic sentences stating the clinical indication "
            "for this CT examination (e.g. patient condition, oncological context, "
            "treatment stage being evaluated)."
        )
    )
    study_technique: str = Field(
        description=(
            "Brief description of the acquisition protocol: body regions covered, "
            "contrast administration, and reference to the previous exam date if available."
        )
    )
    statements: list[ReportStatement] = Field(
        description=(
            "Exhaustive list of individual radiological findings. Each item is one "
            "self-contained clinical statement about a lesion or relevant structure. "
            "Use precise medical terminology. Be telegraphic and objective. "
            "Do NOT hallucinate findings not present in the input data."
        )
    )
    conclusion: str = Field(
        description=(
            "Definitive RECIST 1.1 diagnostic category (PR, SD, PD, or N/A for first exam) "
            "strictly based on the provided RECIST status, with a one-sentence justification."
        )
    )


VLM_PROMPT = """
Our patient just went through his CT exam.

For each lesion, you are provided a slice of a CT scan where the area of the lesion is maximal.
The red channel corresponds to the segmentation of lesions (do not mention this fact in the report).

Output a diagnostic with multiple plausible hypothesis for this scan.
Be specific about the locations where you identified lesions.

Here are further information about the patient and the exam he/she just went through:
<metadata>
<metrics>
{metrics}
</metrics>
<patient>
{patient_metadata}
</patient>
<series>
{series_metadata}
</series>
</metadata>
"""

REPORT_PROMPT = """
You are an expert oncological radiologist specializing in tumor response evaluation using RECIST 1.1 criteria.
Write a strictly clinical CT report in English with no conversational filler.

Previous radiology report:
<previous_report>
{previous_report}
</previous_report>

Current lesion metrics:
<metrics>
{current_metrics}
</metrics>

AI pipeline analysis:
<analysis>
- Background: {background}
- Hypotheses: {hypotheses}
</analysis>

RECIST status for this exam: {recist_status}

RULES:
- Use precise medical terminology (adenopathy, condensation, nodule, etc.). Be telegraphic and objective.
- DO NOT hallucinate or invent findings not present in the input data.
- DO NOT include lesion IDs.
- `reasons_for_study`: clinical indication in 1-2 sentences.
- `study_technique`: acquisition protocol, contrast, comparison exam date if known.
- `statements`: MAXIMUM 4 items. Each must be a single, precise, self-contained clinical observation — location, size (previous in parentheses if available), evolution. The `text` field MUST contain the literal string "image <N>" (e.g. "image 98") where <N> is the exact `slice_index` integer from the matching lesion in the metrics. For the `slice_index` field, copy that same integer exactly (do NOT invent or approximate either). Prioritise the most clinically significant findings. Do not pad with trivial or redundant observations.
- `conclusion`: RECIST category + one-sentence justification, strictly from the provided RECIST status.
"""


def map_patient_to_series_to_use(patient_id):
    if patient_id == "PATIENT002":
        return "S3 1.25 mm Pulmon"
    else:
        return "S2 CEV torax"


def create_report(
    patient_id: str,
    path_to_dataset: str,
    study_name: str,
    path_to_seg_file: str,
    path_to_image_analysis_results: str,
) -> StructuredReport:
    """

    Args:
    - patient_id: the id of the patient to generate the report for (ex: "PATIENT001")
    - path_to_dataset: the path to the dataset folder containing all patients' data
    - study_name: the name of the study to generate the report for (ex: "STUDY0002 TC TRAX TC ABDOMEN TC PELVIS")
    - path_to_seg_file: the path to the segmentation file for the study to generate the report for
    - path_to_image_analysis_results: the path to the json file containing the results of the image analysis for all studies (output of thibault's pipeline)
    - series: the name of the series to generate the report for (ex: "CT CEV torax")

    Returns:
    - report: the generated radiology report as a StructuredReport instance
    """
    # ── API client setup ──────────────────────────────────────────────────────
    api_key = (
        ...
    )  # to be set from env variable in actual usage, hardcoded here for testing
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    study_id = study_name.split(" ")[0]

    # ── Read analysis JSON early (gives series name + recist_status) ─────────
    with open(path_to_image_analysis_results, "r") as f:
        metric_results = json.load(f)
    study_results = metric_results[-1]  # fallback to last entry
    for r in metric_results:
        if r["study_name"].split(" ")[0] == study_id:
            study_results = r
            break
    # Use the actual series folder name recorded by the pipeline (not a hardcoded mapping)
    series = study_results.get("ct_series_name", "CT CEV torax")
    recist_status = (
        study_results.get("recist_like_category_prev") or "N/A (first examination)"
    )

    # ── Build paths ───────────────────────────────────────────────────────────
    patient_path = os.path.join(path_to_dataset, f"{patient_id} {patient_id}")
    study_path = os.path.join(patient_path, study_name)
    series_folder = os.path.join(study_path, series)

    # ── Load CT volume ────────────────────────────────────────────────────────
    ct_image_files = sorted(
        [
            os.path.join(series_folder, f)
            for f in os.listdir(series_folder)
            if f.endswith(".dcm")
        ]
    )
    ct_volume = np.stack([pydicom.dcmread(f).pixel_array for f in ct_image_files])

    # ── Load segmentation volume ──────────────────────────────────────────────
    # Raw SEG pixel_array may have fewer frames than CT slices (only segmented frames).
    # If it is not already a dense (n_ct, H, W) array, fall back to zeros so
    # slice indexing in the lesion loop below never raises IndexError.
    seg_raw = pydicom.dcmread(path_to_seg_file).pixel_array
    n_ct = ct_volume.shape[0]
    if seg_raw.ndim == 3 and seg_raw.shape[0] == n_ct:
        segmentation_volume = seg_raw
    else:
        segmentation_volume = np.zeros(ct_volume.shape, dtype=np.uint8)

    # extraction des données pour chaque lésion
    lesions_to_analyse = {}
    lesion_metrics = [
        "size_x_cm",
        "size_y_cm",
        "size_z_cm",
        "volume_cm3",
        "slice_index",
    ]
    for lesion_data in study_results["lesions"]:
        lesions_to_analyse[lesion_data["lesion_id"]] = {
            "size_x_cm": round(lesion_data["size_x_cm"], 2),
            "size_y_cm": round(lesion_data["size_y_cm"], 2),
            "size_z_cm": round(lesion_data["size_z_cm"], 2),
            "volume_cm3": round(
                lesion_data["size_x_cm"]
                * lesion_data["size_y_cm"]
                * lesion_data["size_z_cm"],
                2,
            ),
            "slice_index": lesion_data["slice_index"],
        }
        slice_index = lesion_data["slice_index"]

        ct_slice = ct_volume[slice_index]
        # Safe access: dense segmentation_volume aligns with CT, but fall back to zeros
        if slice_index < segmentation_volume.shape[0]:
            segmentation_slice = segmentation_volume[slice_index]
        else:
            segmentation_slice = np.zeros_like(ct_slice)

        # formatage des images
        # Normalize CT to [0, 255] uint8
        ct = ct_slice.astype(np.float32)
        ct = ct - ct.min()
        ct = (ct / ct.max() * 255).astype(np.uint8)

        # Normalize segmentation mask to [0, 255] uint8
        seg = segmentation_slice.astype(np.float32)
        if seg.max() > 0:
            seg = (seg / seg.max() * 255).astype(np.uint8)
        else:
            seg = seg.astype(np.uint8)

        # Build RGB overlay: red channel = segmentation, green+blue = CT
        image_rgb = np.stack(
            [
                np.clip(ct.astype(np.uint16) + seg.astype(np.uint16), 0, 255).astype(
                    np.uint8
                ),  # R
                ct,  # G
                ct,  # B
            ],
            axis=-1,
        )
        pil_image = Image.fromarray(image_rgb, mode="RGB")
        buffered = io.BytesIO()
        pil_image.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()

        lesions_to_analyse[lesion_data["lesion_id"]]["image"] = img_base64
    current_lesion_metrics = {  # métriques pour les lésions de l'étude courante
        f"Lesion_id_{lesion_id}": {
            metric_name: lesion_data[metric_name] for metric_name in lesion_metrics
        }
        for lesion_id, lesion_data in lesions_to_analyse.items()
    }

    # Extract relevant metadata
    all_patient_metadata = extract_patient_metadata(patient_path)
    patient_metadata = {
        "PatientSex": all_patient_metadata["PatientSex"],
        "PatientAge": all_patient_metadata["PatientAge"],
        "PatientComments": all_patient_metadata["PatientComments"],
    }
    all_series_metadata = extract_series_metadata(series_folder)
    series_metadata = {
        "SeriesDescription": all_series_metadata["SeriesDescription"],
        "BodyPartExamined": all_series_metadata["BodyPartExamined"],
    }

    formatted_vlm_prompt = VLM_PROMPT.format(
        metrics=json.dumps(current_lesion_metrics, ensure_ascii=False),
        patient_metadata=json.dumps(patient_metadata, ensure_ascii=False),
        series_metadata=json.dumps(series_metadata, ensure_ascii=False),
    )

    def _call_vlm(model_name: str):
        local_client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
        try:
            response = local_client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": formatted_vlm_prompt,
                            }
                        ]
                        + [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{lesion_data['image']}"
                                },
                            }
                            for lesion_data in lesions_to_analyse.values()
                        ],
                    }
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "RadiologyReport",
                        "strict": True,
                        "schema": RadiologyReport.model_json_schema(),
                    },
                },
            )
            raw = RadiologyReport.model_validate_json(
                response.choices[0].message.content
            )
            return model_name, raw, None
        except Exception as exc:
            return model_name, None, exc

    vlm_models = [
        "google/gemini-3-flash-preview",
        "anthropic/claude-sonnet-4.6",
        "openai/gpt-5.2",
    ]

    max_workers = min(len(vlm_models), 4)

    models_responses = {}
    with ThreadPoolExecutor(
        max_workers=max_workers, thread_name_prefix="vlm"
    ) as executor:
        future_by_model = {
            executor.submit(_call_vlm, model): model for model in vlm_models
        }
        for future in as_completed(future_by_model):
            model_name, raw, error = future.result()
            if error is not None:
                warnings.warn(f"VLM {model_name} failed: {error}")
                continue
            if raw is None:
                warnings.warn(f"VLM {model_name} returned an empty response")
                continue
            models_responses[model_name] = raw

    # ── Extract previous report from clinical data (file may not be available) ─
    previous_study_report = {}
    most_recent_previous_study_date_raw = None
    try:
        clinical_data = pandas.read_csv(PATH_TO_CLINICAL_DATA)
        relevant_clinical_data = clinical_data[
            (clinical_data["PatientID"] == patient_id)
            & (clinical_data["AccessionNumber"].astype(str) != str(study_id))
        ]
        for _, row in relevant_clinical_data.iterrows():
            previous_study_id = row["AccessionNumber"]
            previous_study_report = row["Clinical information data (Pseudo reports)"]

            # recherche de la date de la study
            for previous_study_results in metric_results:
                if str(previous_study_results["study_name"].split(" ")[0]) == str(
                    study_id
                ):
                    break

            if int(previous_study_results["study_date_raw"]) >= int(
                study_results["study_date_raw"]
            ):
                print(
                    f"Skipping study {previous_study_id} as it is not anterior to the current study"
                )
                continue  # on ne garde que les rapports des études antérieures

            if most_recent_previous_study_date_raw is not None and int(
                previous_study_results["study_date_raw"]
            ) > int(most_recent_previous_study_date_raw):
                continue

            previous_study_report = {
                "Date": previous_study_results["study_date_fmt"],
                "Lesions": {
                    f"Lesion_id_{tmp_lesion_data['lesion_id']}": {
                        "size_x_cm": round(tmp_lesion_data["size_x_cm"], 2),
                        "size_y_cm": round(tmp_lesion_data["size_y_cm"], 2),
                        "size_z_cm": round(tmp_lesion_data["size_z_cm"], 2),
                        "volume_cm3": round(
                            tmp_lesion_data["size_x_cm"]
                            * tmp_lesion_data["size_y_cm"]
                            * tmp_lesion_data["size_z_cm"],
                            2,
                        ),
                    }
                    for tmp_lesion_data in previous_study_results["lesions"]
                },
                "Report": previous_study_report,
            }
    except Exception:
        pass  # clinical data file unavailable – proceed without previous report

    # formatage des analyses par les VLM
    background_to_concat = []
    for model_i, response in enumerate(models_responses.values()):
        background_to_concat.append(f"Background by model {model_i + 1}:")
        background_to_concat.append(f"\t{response.background}")
    concatenated_backgrounds = "\n".join(background_to_concat)

    hyp_to_concat = []
    for model_i, response in enumerate(models_responses.values()):
        hyp_to_concat.append(f"Hypothesis by model {model_i + 1}:")
        for i_hyp, hyp in enumerate(response.hypotheses):
            hyp_to_concat.append(f"\t{i_hyp + 1}: {hyp.statement}")
    concatenated_hyp = "\n".join(hyp_to_concat)

    formatted_report_prompt = REPORT_PROMPT.format(
        previous_report=json.dumps(previous_study_report, ensure_ascii=False),
        background=concatenated_backgrounds,
        hypotheses=concatenated_hyp,
        current_metrics=json.dumps(current_lesion_metrics, ensure_ascii=False),
        recist_status=recist_status,
    )

    report_response = client.chat.completions.create(
        model="google/gemini-3-flash-preview",
        messages=[
            {
                "role": "user",
                "content": formatted_report_prompt,
            }
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "StructuredReport",
                "strict": True,
                "schema": StructuredReport.model_json_schema(),
            },
        },
        extra_body={
            "reasoning": {
                "effort": "none"  # see https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
            }
        },
        temperature=0,
    )

    raw_content = report_response.choices[0].message.content or ""
    return StructuredReport.model_validate_json(raw_content)
