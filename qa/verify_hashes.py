from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
expected = json.loads((ROOT / "qa/expected_hashes.json").read_text(encoding="utf-8"))
actual = {}
for name, digest in expected.items():
    path = ROOT / "task" / name
    actual[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual[name] != digest:
        raise SystemExit(f"hash mismatch: {name}")
(ROOT / "evidence").mkdir(exist_ok=True)
(ROOT / "evidence/attachment-hashes.json").write_text(json.dumps(actual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
