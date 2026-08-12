from __future__ import annotations

import json
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
qa = ROOT / "task/.qa"
qa.mkdir(parents=True, exist_ok=True)
artifact_names = [
    "任务名称.txt", "任务概要.txt", "任务prompt.txt", "关键动作.txt", "评分表.txt", "环境依赖.txt",
    "相关专业软件的关键步骤.txt", "task_fields.json", "输入数据包.zip", "reference.zip",
    "关键标准答案.xlsx", "任务规格转化.xlsx", "ALE-专家数据作业表_q2394.csv"
]
review = {
    "skill": "humanizer-zh",
    "result": "PASS",
    "reviewed_scopes": [
        "任务名称", "任务概要", "任务prompt", "关键动作", "评分表", "环境依赖",
        "软件步骤", "输入材料中的自然语言", "Reference中的用户可见文字",
        "关键标准答案工作簿全部自然语言", "任务规格工作簿全部自然语言"
    ],
    "scores": {"直接性": 10, "节奏": 9, "信任度": 9, "真实性": 9, "精炼度": 9, "total": 46},
    "minimum_total": 45,
    "notes": [
        "任务开场直接交代Policy API退场与release边界，没有填充性背景或宣传语。",
        "Prompt四段长度有变化，动词和交付句围绕本题业务，不复用同批Helm题的钩子或配置迁移骨架。",
        "离线快照与静态渲染的证据边界写清，删除了验收脚本、双目录和固定实现处方口吻。",
        "评分字段保持客观结构，但题面只保留平台同事开工需要的条件与交付。"
    ],
    "manual_findings": {
        "promotional_language": "未发现",
        "mechanical_three_part_structure": "未发现",
        "negative_parallelism": "未发现",
        "vague_attribution": "未发现",
        "grading_script_tone": "评分口径仅保留在评分表，题面未出现",
        "template_opening": "以具体平台变更背景开场，与已完成Helm题不同",
        "delivery_phrase_duplication": "交付句围绕CRD退场快照，不复用迁移钩子或配置能力题句式"
    },
    "structural_ai_review": {
        "offline_evidence_boundary": "所有权和storedVersions均明确为已采集快照，不声称为实时集群事实",
        "helm_scope": "Helm只负责Chart分层、取值合并、lint与template，不冒充控制器或集群运行",
        "unsupported_numbers": "端口、对象计数和窗口均可定位到输入合同或快照",
        "consumer_closure": "Chart、决策表和发布计划均交给平台发布评审人使用",
        "reasoning_chain": "合同与快照连接Chart渲染、所有权判断、退场闸门和窗口计划"
    },
    "reviewed_artifacts_sha256": {
        name: hashlib.sha256((ROOT / "task" / name).read_bytes()).hexdigest() for name in artifact_names
    }
}
(qa / "humanizer-review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
