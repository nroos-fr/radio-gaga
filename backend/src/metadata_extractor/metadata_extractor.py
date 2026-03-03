import os
from pathlib import Path

import pydicom


def convert_date_string_to_datetime(date_string: str):
    """
    Convertit une chaîne de caractères au format DICOM (YYYYMMDD) en objet datetime.

    Parameters
    ----------
    date_string : str
        Chaîne de caractères représentant une date au format DICOM (ex: "19850315").

    Returns
    -------
    datetime.datetime
        Objet datetime correspondant à la date fournie.

    Raises
    ------
    ValueError
        Si la chaîne de caractères n'est pas au format attendu.
    """
    from datetime import datetime

    try:
        return datetime.strptime(date_string, "%Y%m%d")
    except ValueError as e:
        raise ValueError(
            f"Date string '{date_string}' is not in the expected DICOM format YYYYMMDD."
        ) from e


def get_patient_list(dataset_path: str | Path):
    """
    Parcourt le dossier du dataset et retourne une liste d'ID de patients (dossiers contenant des études).

    Parameters
    ----------
    dataset_path : str | Path
        Chemin vers le dossier racine du dataset DICOM.

    Returns
    -------
    list[dict]
        Liste de dictionnaires, chacun contenant les métadonnées d'un patient.
    """
    dataset_path = Path(dataset_path)
    if not dataset_path.is_dir():
        raise ValueError(f"Le chemin {dataset_path} n'est pas un dossier valide.")

    patients = []
    for patient_dir in dataset_path.iterdir():
        if patient_dir.is_dir():
            try:
                metadata = extract_patient_metadata(patient_dir)
                patients.append(metadata["PatientID"])
            except ValueError as e:
                print(f"[WARN] {e} Skipping {patient_dir}.")

    return patients


def extract_patient_metadata(
    patient_path: str | Path,
):
    """
    Renvoie un dictionnaire de métadonnées extraites d'un dossier correspondant
    à un Patient (ie contient des études).

    Parameters
    ----------
    patient_path : str | Path
        Chemin vers le dossier du patient DICOM.
    Returns
    -------
    dict[str, str]
        Dictionnaire contenant les métadonnées extraites à propose du patient. Détails:
        - PatientName: str
        - PatientID: str
        - PatientSex: str
        - PatientAge: int | None (en années, None si non disponible)
        - PatientComments: str
    """
    patient_path = Path(patient_path)
    if not patient_path.is_dir():
        raise ValueError(f"Le chemin {patient_path} n'est pas un dossier valide.")

    # Trouver un fichier DICOM dans le dossier du patient
    dicom_files = list(patient_path.glob("**/*.dcm"))
    if not dicom_files:
        raise ValueError(f"Aucun fichier DICOM trouvé dans {patient_path}.")

    # Lire les métadonnées du premier fichier DICOM trouvé
    dicom_file = dicom_files[0]
    ds = pydicom.dcmread(dicom_file, stop_before_pixels=True)

    # Extraire les métadonnées pertinentes
    metadata = {
        "PatientName": str(getattr(ds, "PatientName", "")),
        "PatientID": str(getattr(ds, "PatientID", "")),
        "PatientSex": str(getattr(ds, "PatientSex", "")),
        "PatientAge": getattr(ds, "PatientAge", ""),
        "PatientComments": str(getattr(ds, "PatientComments", "")),
    }

    # post traitement
    metadata["PatientAge"] = (
        int(metadata["PatientAge"][:-1]) if metadata["PatientAge"] else None
    )

    return metadata


def extract_study_metadata(
    study_path: str | Path,
) -> dict[str, str]:
    """
    Renvoie un dictionnaire de métadonnées extraites d'un dossier correspondant
    à une Study (ie contient des series).

    Parameters
    ----------
    study_path : str | Path
        Chemin vers le dossier de l'étude DICOM.
    Returns
    -------
    dict[str, str]
        Dictionnaire contenant les métadonnées extraites à propose de la study et du patient.
        - StudyDate: datetime | None
        - ModalitiesInStudy: list[str]
        - StudyDescription: str
    """
    study_path = Path(study_path)
    if not study_path.is_dir():
        raise ValueError(f"Le chemin {study_path} n'est pas un dossier valide.")

    # Trouver un fichier DICOM dans le dossier de l'étude
    dicom_files = list(study_path.glob("**/*.dcm"))
    if not dicom_files:
        raise ValueError(f"Aucun fichier DICOM trouvé dans {study_path}.")

    # Lire les métadonnées du premier fichier DICOM trouvé
    dicom_file = dicom_files[0]
    ds = pydicom.dcmread(dicom_file, stop_before_pixels=True)

    # Extraire les métadonnées pertinentes
    metadata = {
        "StudyDate": getattr(ds, "StudyDate", ""),
        "ModalitiesInStudy": [
            str(modality) for modality in getattr(ds, "ModalitiesInStudy", [])
        ],
        "StudyDescription": str(getattr(ds, "StudyDescription", "")),
    }

    # post traitement
    metadata["StudyDate"] = (
        convert_date_string_to_datetime(metadata["StudyDate"])
        if metadata["StudyDate"]
        else None
    )

    return metadata


def extract_series_metadata(
    series_path: str | Path,
) -> dict[str, str]:
    """
    Renvoie un dictionnaire de métadonnées extraites d'un dossier correspondant
    à une Series (ie contient des instances).

    Parameters
    ----------
    series_path : str | Path
        Chemin vers le dossier de la série DICOM.
    Returns
    -------
    dict[str, str]
        Dictionnaire contenant les métadonnées extraites à propose de la série et de l'étude
        - SeriesDescription: str
        - BodyPartExamined: str
        - Modality: str
        - Manufacturer: str
        - SeriesDate: datetime | None
        - SeriesTime: str
    """
    series_path = Path(series_path)
    if not series_path.is_dir():
        raise ValueError(f"Le chemin {series_path} n'est pas un dossier valide.")

    # Trouver un fichier DICOM dans le dossier de la série
    dicom_files = list(series_path.glob("**/*.dcm"))
    if not dicom_files:
        raise ValueError(f"Aucun fichier DICOM trouvé dans {series_path}.")

    # Lire les métadonnées du premier fichier DICOM trouvé
    dicom_file = dicom_files[0]
    ds = pydicom.dcmread(dicom_file, stop_before_pixels=True)

    # Extraire les métadonnées pertinentes
    metadata = {
        "SeriesDescription": str(getattr(ds, "SeriesDescription", "")),
        "BodyPartExamined": str(getattr(ds, "BodyPartExamined", "")),
        "Modality": str(getattr(ds, "Modality", "")),
        "Manufacturer": str(getattr(ds, "Manufacturer", "")),
        "SeriesDate": str(getattr(ds, "SeriesDate", "")),
        "SeriesTime": str(getattr(ds, "SeriesTime", "")),
    }

    # post traitement
    metadata["SeriesDate"] = (
        convert_date_string_to_datetime(metadata["SeriesDate"])
        if metadata["SeriesDate"]
        else None
    )

    return metadata


if __name__ == "__main__":
    # exemple d'utilisation
    PATIENT = "PATIENT001"
    PATH_TO_PATIENT = f"/path/to/dataset/{PATIENT} {PATIENT}/"
    PATH_TO_STUDY = os.path.join(
        PATH_TO_PATIENT, "STUDY0002 TC TRAX TC ABDOMEN TC PELVIS"
    )
    PATH_TO_SERIES = os.path.join(PATH_TO_STUDY, "CT lung")

    print("=== Patient Metadata ===")
    patient_metadata = extract_patient_metadata(PATH_TO_PATIENT)
    for k, v in patient_metadata.items():
        print(f"{k}: {v}, type: {type(v)}")
    print("=== Study Metadata ===")
    study_metadata = extract_study_metadata(PATH_TO_STUDY)
    for k, v in study_metadata.items():
        print(f"{k}: {v}, type: {type(v)}")
    print("=== Series Metadata ===")
    series_metadata = extract_series_metadata(PATH_TO_SERIES)
    for k, v in series_metadata.items():
        print(f"{k}: {v}, type: {type(v)}")
