from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "task"
plain_names = ["任务名称.txt", "任务概要.txt", "任务prompt.txt", "关键动作.txt", "评分表.txt", "环境依赖.txt", "相关专业软件的关键步骤.txt"]
texts = [(name, (TASK / name).read_text(encoding="utf-8-sig")) for name in plain_names]
for inspect_name in ["任务规格转化.xlsx.inspect.ndjson", "关键标准答案.xlsx.inspect.ndjson"]:
    values = []
    for line in (TASK / inspect_name).read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        stack = [record]
        while stack:
            item = stack.pop()
            if isinstance(item, str):
                values.append(item)
            elif isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                stack.extend(item.values())
    texts.append((inspect_name, "\n".join(values)))
for archive_name in ["输入数据包.zip", "reference.zip"]:
    with zipfile.ZipFile(TASK / archive_name) as archive:
        for name in archive.namelist():
            if name.lower().endswith((".txt", ".md")):
                texts.append((f"{archive_name}:{name}", archive.read(name).decode("utf-8-sig")))
patterns = {
    "quotes": r"[\"'“”‘’「」『』《》〈〉`]",
    "zh_en_space": r"[\u3400-\u9fff][ \t]+[A-Za-z]|[A-Za-z][ \t]+[\u3400-\u9fff]",
    "zh_num_space": r"[\u3400-\u9fff][ \t]+\d|\d[ \t]+[\u3400-\u9fff]",
    "en_num_space": r"[A-Za-z][ \t]+\d|\d[ \t]+[A-Za-z]",
}
failures = []
for label, text in texts:
    for key, pattern in patterns.items():
        matches = re.findall(pattern, text)
        if matches:
            failures.append({"scope": label, "gate": key, "examples": matches[:5]})
prompt = (TASK / "任务prompt.txt").read_text(encoding="utf-8").rstrip("\n")
if not (350 <= len(prompt) <= 450 and len(prompt.split("\n\n")) == 4):
    failures.append({"scope": "任务prompt.txt", "gate": "prompt_shape", "examples": [len(prompt), len(prompt.split("\n\n"))]})
with zipfile.ZipFile(TASK / "输入数据包.zip") as archive:
    input_files = [name for name in archive.namelist() if not name.endswith("/")]
report = {
    "result": "PASS" if not failures else "FAIL",
    "text_scope_count": len(texts),
    "prompt_character_count": len(prompt),
    "prompt_paragraph_count": len(prompt.split("\n\n")),
    "input_file_count": len(input_files),
    "character_gate_counts": {key: sum(1 for item in failures if item["gate"] == key) for key in patterns},
    "failures": failures,
}
(ROOT / "qa/static-check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
if failures:
    raise SystemExit(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps(report, ensure_ascii=False, indent=2))
