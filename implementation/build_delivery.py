from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOLUTION = ROOT / "chart_solution"
EXPECTED = {
    "README.txt",
    "lifecycle_contract.json",
    "ownership_snapshot.csv",
    "storage_snapshot.csv",
    "rollout_windows.csv",
    "starter-crd-chart/Chart.yaml",
    "starter-crd-chart/values.yaml",
    "starter-crd-chart/templates/crd.yaml",
    "starter-controller-chart/Chart.yaml",
    "starter-controller-chart/values.yaml",
    "starter-controller-chart/templates/deployment.yaml",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def bool_value(text: str) -> bool:
    if text not in {"true", "false"}:
        raise ValueError("布尔字段只接受true或false")
    return text == "true"


def helm(helm_bin: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([helm_bin, *args], text=True, capture_output=True, timeout=90)


def scalar(block: str, pattern: str, label: str) -> str:
    match = re.search(pattern, block, re.MULTILINE)
    if not match:
        raise ValueError(f"渲染对象缺少{label}")
    return match.group(1).strip().strip('"')


def parse_documents(text: str, chart: str, mode: str) -> list[dict[str, str]]:
    rows = []
    for block in re.split(r"(?m)^---\s*$", text):
        kind_match = re.search(r"(?m)^kind:\s*(\S+)\s*$", block)
        if not kind_match:
            continue
        kind = kind_match.group(1)
        name = scalar(block, r"(?m)^\s{2}name:\s*([^\s]+)\s*$", "对象名称")
        namespace_match = re.search(r"(?m)^\s{2}namespace:\s*([^\s]+)\s*$", block)
        rows.append({
            "chart": chart,
            "mode": mode,
            "api_version": scalar(block, r"(?m)^apiVersion:\s*(\S+)\s*$", "API版本"),
            "kind": kind,
            "namespace": namespace_match.group(1) if namespace_match else "",
            "name": name,
        })
    return rows


def validate_inputs(input_root: Path) -> tuple[dict, list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    present = {p.relative_to(input_root).as_posix() for p in input_root.rglob("*") if p.is_file()}
    if not EXPECTED.issubset(present):
        raise ValueError("输入文件不完整")
    contract = json.loads((input_root / "lifecycle_contract.json").read_text(encoding="utf-8"))
    ownership = read_csv(input_root / "ownership_snapshot.csv")
    storage = read_csv(input_root / "storage_snapshot.csv")
    windows = read_csv(input_root / "rollout_windows.csv")
    key_sets = []
    for rows in [ownership, storage, windows]:
        keys = [row["cluster"] for row in rows]
        if len(keys) != len(set(keys)):
            raise ValueError("cluster主键重复")
        key_sets.append(set(keys))
    if not key_sets[0] or key_sets[0] != key_sets[1] or key_sets[0] != key_sets[2]:
        raise ValueError("快照cluster集合不一致")
    return contract, ownership, storage, windows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--helm", required=True)
    args = parser.parse_args()
    input_root = Path(args.input).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        shutil.rmtree(output)
    try:
        contract, ownership, storage, windows = validate_inputs(input_root)
        charts = output / "charts"
        rendered = output / "rendered"
        results = output / "results"
        shutil.copytree(SOLUTION, charts)
        rendered.mkdir(parents=True)
        results.mkdir()

        lint_rows = []
        for chart_name in ["policy-crds", "policy-controller"]:
            process = helm(args.helm, ["lint", str(charts / chart_name)])
            if process.returncode != 0:
                raise RuntimeError(process.stdout + process.stderr)
            lint_rows.append({"chart": chart_name, "status": "PASS"})

        profiles = [
            ("policy-crds", "additive", ["--set-string", "lifecycle.mode=additive"]),
            ("policy-crds", "prune", ["--set-string", "lifecycle.mode=prune"]),
            ("policy-controller", "bridge", ["--set-string", "controller.mode=bridge"]),
            ("policy-controller", "steady", ["--set-string", "controller.mode=steady"]),
        ]
        inventory = []
        rendered_text = {}
        for chart_name, mode, values in profiles:
            process = helm(args.helm, ["template", chart_name, str(charts / chart_name), *values])
            if process.returncode != 0:
                raise RuntimeError(process.stdout + process.stderr)
            rendered_text[mode] = process.stdout
            (rendered / f"{mode}.yaml").write_text(process.stdout, encoding="utf-8")
            inventory.extend(parse_documents(process.stdout, chart_name, mode))
        inventory.sort(key=lambda row: (row["chart"], row["mode"], row["kind"], row["name"]))
        write_csv(results / "render_inventory.csv", inventory, ["chart", "mode", "api_version", "kind", "namespace", "name"])

        required = set(contract["required_controller_kinds"])
        forbidden = set(contract["forbidden_controller_kinds"])
        for mode in contract["controller_modes"]:
            kinds = {row["kind"] for row in inventory if row["mode"] == mode}
            if not required.issubset(kinds) or kinds.intersection(forbidden):
                raise ValueError("控制器Chart对象边界不符合合同")
        for mode in contract["crd_modes"]:
            kinds = {row["kind"] for row in inventory if row["mode"] == mode}
            if kinds != {"CustomResourceDefinition"}:
                raise ValueError("CRD Chart对象边界不符合合同")

        additive_versions = re.findall(r"(?m)^\s{4}- name:\s*(v[^\s]+)\s*$", rendered_text["additive"])
        prune_versions = re.findall(r"(?m)^\s{4}- name:\s*(v[^\s]+)\s*$", rendered_text["prune"])
        if set(additive_versions) != set(contract["old_versions"] + [contract["storage_version"]]):
            raise ValueError("additive版本集合不符合合同")
        if prune_versions != [contract["storage_version"]]:
            raise ValueError("prune版本集合不符合合同")
        if rendered_text["additive"].count("storage: true") != 1 or rendered_text["prune"].count("storage: true") != 1:
            raise ValueError("storage版本必须唯一")
        if "helm.sh/resource-policy: keep" not in rendered_text["additive"] or "helm.sh/resource-policy: keep" not in rendered_text["prune"]:
            raise ValueError("CRD缺少卸载保护")
        bridge_read = scalar(rendered_text["bridge"], r"(?m)^\s+value:\s*([^\s]+)\s*$", "bridge读取版本").split(",")
        steady_read = scalar(rendered_text["steady"], r"(?m)^\s+value:\s*([^\s]+)\s*$", "steady读取版本").split(",")
        if set(bridge_read) != set(contract["bridge_read_versions"]) or set(steady_read) != set(contract["steady_read_versions"]):
            raise ValueError("控制器读取版本不符合合同")

        crd_service = {
            "name": scalar(rendered_text["additive"], r"(?m)^\s{10}name:\s*([^\s]+)\s*$", "conversion服务名称"),
            "namespace": scalar(rendered_text["additive"], r"(?m)^\s{10}namespace:\s*([^\s]+)\s*$", "conversion命名空间"),
            "port": scalar(rendered_text["additive"], r"(?m)^\s{10}port:\s*(\d+)\s*$", "conversion端口"),
        }
        controller_service = {
            "name": scalar(rendered_text["bridge"], r"(?ms)^kind:\s*Service\s*.*?^metadata:\s*\n\s{2}name:\s*([^\s]+)\s*$", "控制器服务名称"),
            "namespace": scalar(rendered_text["bridge"], r"(?ms)^kind:\s*Service\s*.*?^metadata:\s*\n(?:.*\n)*?\s{2}namespace:\s*([^\s]+)\s*$", "控制器命名空间"),
            "port": scalar(rendered_text["bridge"], r"(?ms)^kind:\s*Service\s*.*?^\s{6}port:\s*(\d+)\s*$", "控制器服务端口"),
        }
        if crd_service != controller_service or int(crd_service["port"]) != int(contract["conversion_port"]):
            raise ValueError("conversion引用与控制器Service不闭合")

        ownership_rows = []
        ownership_status = {}
        for row in ownership:
            owner_type = row["owner_type"]
            detached = bool_value(row["legacy_release_detached"])
            approved = bool_value(row["adoption_approved"])
            if owner_type == "legacy_helm":
                ready = detached and approved
                reason = "ready_for_adoption" if ready else ("legacy_release_attached" if not detached else "adoption_not_approved")
            elif owner_type == "manual":
                ready = approved
                reason = "ready_for_adoption" if ready else "adoption_not_approved"
            else:
                raise ValueError("未知owner_type")
            status = "READY" if ready else "BLOCK"
            ownership_status[row["cluster"]] = status
            ownership_rows.append({"cluster": row["cluster"], "observed_at": row["observed_at"], "owner_type": owner_type, "action": "ADOPT" if ready else "WAIT", "status": status, "reason": reason, "evidence_type": "SNAPSHOT"})
        write_csv(results / "ownership_decisions.csv", ownership_rows, ["cluster", "observed_at", "owner_type", "action", "status", "reason", "evidence_type"])

        gate_rows = []
        gate_status = {}
        for row in storage:
            total = int(row["total_objects"])
            rewritten = int(row["rewritten_to_v1"])
            failures = int(row["conversion_failures"])
            if total < 0 or rewritten < 0 or rewritten > total or failures < 0:
                raise ValueError("存储快照计数越界")
            stored = {value for value in row["stored_versions"].split(";") if value}
            conditions = [ownership_status[row["cluster"]] == "READY", rewritten == total, failures == 0, stored == {contract["storage_version"]}]
            status = "PASS" if all(conditions) else "HOLD"
            if ownership_status[row["cluster"]] != "READY":
                reason = "ownership_blocked"
            elif rewritten != total:
                reason = "rewrite_incomplete"
            elif failures != 0:
                reason = "conversion_failure"
            elif stored != {contract["storage_version"]}:
                reason = "old_stored_version_present"
            else:
                reason = "retirement_ready"
            gate_status[row["cluster"]] = status
            gate_rows.append({"cluster": row["cluster"], "observed_at": row["observed_at"], "ownership_status": ownership_status[row["cluster"]], "rewrite_complete": str(rewritten == total).lower(), "conversion_failures": failures, "stored_versions": ";".join(sorted(stored)), "retirement_status": status, "reason": reason, "evidence_type": "SNAPSHOT"})
        write_csv(results / "retirement_gate.csv", gate_rows, ["cluster", "observed_at", "ownership_status", "rewrite_complete", "conversion_failures", "stored_versions", "retirement_status", "reason", "evidence_type"])

        window_map = {row["cluster"]: row for row in windows}
        plan_rows = []
        for cluster in sorted(ownership_status):
            window = window_map[cluster]
            approved = bool_value(window["approved"])
            for order, phase in enumerate(contract["phase_order"], start=1):
                if not approved:
                    decision, reason = "HOLD", "window_not_approved"
                elif ownership_status[cluster] != "READY":
                    decision, reason = "HOLD", "ownership_blocked"
                elif gate_status[cluster] != "PASS" and phase in {"prune", "steady"}:
                    decision, reason = "HOLD", "retirement_not_ready"
                else:
                    decision, reason = "APPLY", "within_approved_window"
                plan_rows.append({"cluster": cluster, "phase": phase, "phase_order": order, "decision": decision, "window_id": window["window_id"], "window_start_utc": window["window_start_utc"], "window_end_utc": window["window_end_utc"], "reason": reason, "evidence_type": "SNAPSHOT"})
        write_csv(results / "release_plan.csv", plan_rows, ["cluster", "phase", "phase_order", "decision", "window_id", "window_start_utc", "window_end_utc", "reason", "evidence_type"])
        write_csv(results / "evidence_scope.csv", [
            {"source_file": "ownership_snapshot.csv", "evidence_type": "SNAPSHOT", "used_for": "CRD所有权处理"},
            {"source_file": "storage_snapshot.csv", "evidence_type": "SNAPSHOT", "used_for": "旧存储版本退场判断"},
            {"source_file": "rollout_windows.csv", "evidence_type": "SNAPSHOT", "used_for": "阶段窗口编排"},
            {"source_file": "Helm渲染输出", "evidence_type": "STATIC_RENDER", "used_for": "Chart对象与版本边界"},
        ], ["source_file", "evidence_type", "used_for"])
        write_csv(results / "lint_results.csv", lint_rows, ["chart", "status"])
        (output / "README.txt").write_text(
            "本目录交给策略平台发布评审人安排Policy API版本切换。charts保存两个独立Chart，rendered保存四种配置的Helm清单，results连接渲染对象、所有权处理、版本切换判断和维护窗计划。\n\n"
            "所有权、storedVersions和对象重写数据采用交接材料的采集时间。值班发布人在维护窗前复查这些状态；手续未齐或存储状态变化的集群留在additive与bridge，其他集群按计划进入后续阶段。\n",
            encoding="utf-8",
        )
    except Exception:
        if output.exists():
            shutil.rmtree(output)
        raise


if __name__ == "__main__":
    main()
