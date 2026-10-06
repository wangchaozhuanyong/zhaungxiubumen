"""Exact header locks for the read-only staged index; no production activation."""
from pathlib import Path

from .native_cms_admission import require, validate_manifest

TASK_ID = "fc-20260927-cms-native-admission-contract-v1"
CANDIDATE_VERSION = "native-control-staged-admission-v2"
CAPABILITY_HEAD = "868837d3c1caad502127c5d35019bcdc4c504eb6"


def validate_staged_native_manifest(root: Path, manifest: dict) -> list[dict]:
    require(manifest.get("task_id") == TASK_ID, "Exact staged task differs")
    require(manifest.get("candidate_version") == CANDIDATE_VERSION,
            "Exact staged candidate version differs")
    require(manifest.get("native_capability_head") == CAPABILITY_HEAD,
            "Exact native capability Head differs")
    return validate_manifest(root, manifest)
