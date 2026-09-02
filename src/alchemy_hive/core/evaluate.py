"""自动评估：用 LLM-as-judge 自动评分蒸馏质量，替代手动盲测。"""
import json
from pathlib import Path

from .models import PersonaDoc
from .llm import chat_completion, LLMError
from .blindtest import ask_agent


# 测试场景模板：从 persona 的 memories/example_replies 提取测试点
_EVAL_SCENARIOS = [
    "打个招呼",
    "对方心情不好时你怎么安慰",
    "约对方吃饭",
    "被问到一个你不知道的事",
    "对方说了一件让你开心的事",
    "吐槽一下今天遇到的烦心事",
    "对方问你在干嘛",
    "认真讨论一个严肃话题",
    "对方说了让你不爽的话",
    "道别",
]


def _extract_memories(doc: PersonaDoc) -> list[str]:
    """从 persona 的 memories 提取触发场景。"""
    triggers = []
    for m in doc.memory:
        if isinstance(m, dict) and m.get("trigger"):
            triggers.append(m["trigger"])
    return triggers[:5]


def _build_eval_prompt(doc: PersonaDoc, scenarios: list[str]) -> list[dict]:
    """构建评估对话：给 persona 一系列测试 prompt。"""
    scenarios_text = "\n".join(f"- {s}" for s in scenarios)
    return [{"role": "user", "content": (
        f"你是{doc.display_name}。请依次回复以下场景，每条回复用 `---` 分隔，"
        f"每条只说 1-2 句：\n\n{scenarios_text}"
    )}]


_JUDGE_PROMPT = """你是一个 AI 人格评估专家。请评估以下 AI 角色扮演的质量。

角色设定（system prompt）：
{system_prompt}

测试场景与回复：
{test_results}

请从以下维度打分（每项 1-10 分），并给出总评：

1. **authenticity**（真实感）：回复是否像一个真人？有没有机械感/套话？
2. **consistency**（一致性）：回复是否与角色设定一致？有没有违反性格规则？
3. **expression**（表达力）：是否使用了设定中的口头禅/说话节奏/例句风格？
4. **emotional_depth**（情感深度）：是否展现了角色的情感层次？

请严格按以下 JSON 格式输出：
{{
  "authenticity": <分数>,
  "consistency": <分数>,
  "expression": <分数>,
  "emotional_depth": <分数>,
  "overall": <总分 0-100>,
  "summary": "<一句话总评>",
  "suggestions": ["<改进建议1>", "<改进建议2>"]
}}"""


def auto_evaluate(persona_path: str | Path, config: dict, n_scenarios: int = 10) -> dict:
    """自动评分：从 persona 提取测试场景 → agent 回复 → judge LLM 评分。

    返回：{score, dimensions, summary, suggestions, test_results}
    """
    doc = PersonaDoc.model_validate(json.loads(Path(persona_path).read_text(encoding="utf-8")))

    # 1. 构建测试场景
    scenarios = list(_EVAL_SCENARIOS[:n_scenarios])
    memory_triggers = _extract_memories(doc)
    for t in memory_triggers:
        if t not in scenarios:
            scenarios.append(t)
    scenarios = scenarios[:n_scenarios]

    # 2. 用 persona 回复测试场景
    test_results: list[dict] = []
    for s in scenarios:
        try:
            reply = ask_agent(
                [{"sender": "对方", "content": s, "timestamp": ""}],
                doc.display_name or doc.name,
                doc.system_prompt,
                config,
            )
            test_results.append({"scenario": s, "reply": reply})
        except Exception:
            test_results.append({"scenario": s, "reply": "(调用失败)"})

    # 3. 用 judge LLM 评分
    results_text = "\n".join(
        f"场景：{r['scenario']}\n回复：{r['reply']}" for r in test_results
    )
    judge_prompt = _JUDGE_PROMPT.format(
        system_prompt=doc.system_prompt[:2000],  # 截断避免超长
        test_results=results_text,
    )
    try:
        raw = chat_completion(
            config,
            [{"role": "user", "content": judge_prompt}],
            temperature=0.3,
            max_retries=1,
            timeout=60,
        )
        # 解析 JSON（可能被 markdown 围栏包裹）
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = json.loads(clean)
    except (LLMError, json.JSONDecodeError, ValueError):
        result = {
            "authenticity": 0,
            "consistency": 0,
            "expression": 0,
            "emotional_depth": 0,
            "overall": 0,
            "summary": "评估调用失败，请检查模型配置",
            "suggestions": [],
        }

    result["test_results"] = test_results

    # 保存评分历史
    _save_eval_history(persona_path, result)

    return result


def _save_eval_history(persona_path: str, result: dict) -> None:
    """保存评分历史到 build/eval_history/{name}.jsonl。"""
    import datetime
    try:
        p = Path(persona_path)
        history_dir = p.parent.parent / "eval_history"
        history_dir.mkdir(parents=True, exist_ok=True)
        history_file = history_dir / f"{p.stem}.jsonl"
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "overall": result.get("overall", 0),
            "authenticity": result.get("authenticity", 0),
            "consistency": result.get("consistency", 0),
            "expression": result.get("expression", 0),
            "emotional_depth": result.get("emotional_depth", 0),
            "summary": result.get("summary", ""),
        }
        with history_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 评分历史保存失败不影响主流程
