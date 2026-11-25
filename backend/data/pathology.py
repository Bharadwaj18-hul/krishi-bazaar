"""
Krishi Bazaar — Plant Pathology Data Loader.
Loads ICAR / CPCRI disease profiles from pathology.json.
"""
import json
from pathlib import Path
from typing import Any, Dict

_DATA_FILE = Path(__file__).resolve().parent / "pathology.json"


def load_pathology_database() -> Dict[str, Dict[str, Any]]:
    """Load the pathology database dictionary from JSON."""
    with open(_DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


PATHOLOGY_DATABASE: Dict[str, Dict[str, Any]] = load_pathology_database()
