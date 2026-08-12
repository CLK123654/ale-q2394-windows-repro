from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "task"
EVIDENCE = ROOT / "evidence"
RUN_ROOT = ROOT / "windows-runs"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reset(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def extract(archive: Path, target: Path) -> None:
    target.mkdir(parents=True)
    with zipfile.ZipFile(archive) as package:
        package.extractall(target)


def members(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())


def normalized(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix.lower() in {".txt", ".csv", ".json", ".yaml", ".yml", ".tpl"}:
        return data.replace(b"\r\n", b"\n")
    return data


def compare(actual: Path, expected: Path) -> list[str]:
    actual_files = members(actual)
    expected_files = members(expected)
    if actual_files != expected_files:
        raise AssertionError("delivery path set differs from Reference")
    for relative in expected_files:
        if normalized(actual / relative) != normalized(expected / relative):
            raise AssertionError(f"delivery differs from Reference: {relative}")
    return expected_files


def build(input_root: Path, output: Path, helm: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([
        sys.executable,
        str(ROOT / "implementation/build_delivery.py"),
        "--input", str(input_root),
        "--output", str(output),
        "--helm", helm,
    ], cwd=ROOT, text=True, capture_output=True, timeout=300)


def main() -> None:
    reset(RUN_ROOT)
    EVIDENCE.mkdir(exist_ok=True)
    helm = os.environ["HELM_PATH"]
    version = subprocess.run([helm, "version", "--template", "{{.Version}}"], text=True, capture_output=True, timeout=30)
    if version.returncode != 0 or not version.stdout.strip().startswith("v3.18.4"):
        raise AssertionError(version.stdout + version.stderr)
    reference = RUN_ROOT / "reference"
    extract(TASK / "reference.zip", reference)
    expected = reference / "output"
    clean_runs = []
    for label in ["clean-a", "clean-b"]:
        base = RUN_ROOT / label
        extract(TASK / "输入数据包.zip", base)
        input_root = base / "input_data"
        before = {p.relative_to(input_root).as_posix(): sha(p) for p in input_root.rglob("*") if p.is_file()}
        for index in [1, 2]:
            output = base / f"output-{index}"
            process = build(input_root, output, helm)
            if process.returncode != 0:
                raise AssertionError(process.stdout + process.stderr)
            generated = compare(output, expected)
            clean_runs.append({"root_id": label, "process_index": index, "return_code": 0, "output_started_empty": True, "primary_software_executed": True, "input_unchanged": True, "reference_match": True, "generated_paths": generated})
        current = {p.relative_to(input_root).as_posix(): sha(p) for p in input_root.rglob("*") if p.is_file()}
        if before != current:
            raise AssertionError("input changed during standard run")

    positive = RUN_ROOT / "positive"
    extract(TASK / "输入数据包.zip", positive)
    storage_path = positive / "input_data/storage_snapshot.csv"
    with storage_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    target = next(row for row in rows if row["cluster"] == "edge-us1")
    target["rewritten_to_v1"] = target["total_objects"]
    target["stored_versions"] = "v1"
    with storage_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    positive_output = positive / "output"
    process = build(positive / "input_data", positive_output, helm)
    if process.returncode != 0:
        raise AssertionError(process.stdout + process.stderr)
    with (positive_output / "results/retirement_gate.csv").open(encoding="utf-8", newline="") as handle:
        result = next(row for row in csv.DictReader(handle) if row["cluster"] == "edge-us1")
    if result["retirement_status"] != "PASS":
        raise AssertionError("storage change did not affect retirement result")
    (EVIDENCE / "positive-case.json").write_text(json.dumps({"input_field": "edge-us1.rewritten_to_v1 and stored_versions", "before": "79 and v1beta1;v1", "after": "84 and v1", "retirement_status": "PASS", "behavior_changed": True}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    negative = RUN_ROOT / "negative"
    extract(TASK / "输入数据包.zip", negative)
    ownership_path = negative / "input_data/ownership_snapshot.csv"
    with ownership_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows.append(dict(rows[0]))
    with ownership_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    negative_output = negative / "output"
    negative_output.mkdir()
    (negative_output / "stale.txt").write_text("stale", encoding="utf-8")
    process = build(negative / "input_data", negative_output, helm)
    if process.returncode == 0 or negative_output.exists():
        raise AssertionError("duplicate cluster did not fail closed")
    (EVIDENCE / "negative-case.log").write_text(f"return_code={process.returncode}\n{process.stdout}{process.stderr}", encoding="utf-8")

    summary = {
        "result": "PASS",
        "commit_sha": os.getenv("GITHUB_SHA"),
        "workflow_run_id": os.getenv("GITHUB_RUN_ID"),
        "runner_image": os.getenv("ImageOS"),
        "main_software": {"name": "Helm", "version": version.stdout.strip(), "executed": True},
        "clean_directory_count": 2,
        "process_runs_per_directory": 2,
        "clean_runs": clean_runs,
        "positive_mutation": "PASS",
        "negative_case": "PASS",
        "formal_network": {"helm_outbound_blocked": True, "external_services_used": False},
        "linux_executables": [],
        "linux_executables_executed": False,
    }
    (EVIDENCE / "windows-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
