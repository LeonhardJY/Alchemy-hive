"""Persona 对比：比较两个蒸馏结果的差异。"""
import json
from pathlib import Path

from .models import PersonaDoc


def compare_personas(doc_a: PersonaDoc, doc_b: PersonaDoc) -> dict:
    """对比两个 PersonaDoc 的差异，返回结构化对比结果。

    返回格式：
    {
        "shared_fields": {"field": value},  # 两边相同的字段
        "diff_fields": {"field": {"a": val_a, "b": val_b}},  # 不同的字段
        "memories_only_a": [...],  # 只在 A 中的记忆
        "memories_only_b": [...],  # 只在 B 中的记忆
        "shared_memories": [...],  # 两边都有的记忆（按 slug 匹配）
        "rules_only_a": [...],
        "rules_only_b": [...],
        "phrases_only_a": [...],
        "phrases_only_b": [...],
    }
    """
    result = {
        "shared_fields": {},
        "diff_fields": {},
        "memories_only_a": [],
        "memories_only_b": [],
        "shared_memories": [],
        "rules_only_a": [],
        "rules_only_b": [],
        "phrases_only_a": [],
        "phrases_only_b": [],
    }

    # 对比标量字段
    scalar_fields = [
        "name", "display_name", "relationship", "relationship_context",
        "relationship_arc", "relationship_essence", "rhythm",
        "memory_signature", "manual_profile",
    ]
    for field in scalar_fields:
        val_a = getattr(doc_a, field, "")
        val_b = getattr(doc_b, field, "")
        if val_a == val_b:
            result["shared_fields"][field] = val_a
        else:
            result["diff_fields"][field] = {"a": val_a, "b": val_b}

    # 对比列表字段
    rules_a = set(doc_a.expression_rules or [])
    rules_b = set(doc_b.expression_rules or [])
    result["rules_only_a"] = sorted(rules_a - rules_b)
    result["rules_only_b"] = sorted(rules_b - rules_a)

    phrases_a = set(doc_a.signature_phrases or [])
    phrases_b = set(doc_b.signature_phrases or [])
    result["phrases_only_a"] = sorted(phrases_a - phrases_b)
    result["phrases_only_b"] = sorted(phrases_b - phrases_a)

    # 对比记忆（按 slug 匹配）
    memories_a = {m.get("slug", ""): m for m in (doc_a.memory or []) if isinstance(m, dict)}
    memories_b = {m.get("slug", ""): m for m in (doc_b.memory or []) if isinstance(m, dict)}
    slugs_a = set(memories_a.keys())
    slugs_b = set(memories_b.keys())

    result["memories_only_a"] = [memories_a[s] for s in sorted(slugs_a - slugs_b)]
    result["memories_only_b"] = [memories_b[s] for s in sorted(slugs_b - slugs_a)]
    result["shared_memories"] = [memories_a[s] for s in sorted(slugs_a & slugs_b)]

    return result


def format_comparison(result: dict, name_a: str = "A", name_b: str = "B") -> str:
    """将对比结果格式化为可读文本。"""
    lines = [f"=== Persona 对比：{name_a} vs {name_b} ===\n"]

    if result["shared_fields"]:
        lines.append(f"【相同字段】({len(result['shared_fields'])} 项)")
        for field, val in result["shared_fields"].items():
            if val:
                lines.append(f"  {field}: {str(val)[:60]}")
        lines.append("")

    if result["diff_fields"]:
        lines.append(f"【不同字段】({len(result['diff_fields'])} 项)")
        for field, vals in result["diff_fields"].items():
            a_str = str(vals["a"])[:40] or "（空）"
            b_str = str(vals["b"])[:40] or "（空）"
            lines.append(f"  {field}:")
            lines.append(f"    {name_a}: {a_str}")
            lines.append(f"    {name_b}: {b_str}")
        lines.append("")

    for label, items in [
        ("记忆", "shared_memories"), ("规则", None), ("口头禅", None),
    ]:
        if items:
            # 共享记忆
            shared = result.get("shared_memories", [])
            only_a = result.get(f"memories_only_{name_a.lower()}", result.get("memories_only_a", []))
            only_b = result.get(f"memories_only_{name_b.lower()}", result.get("memories_only_b", []))
            lines.append(f"【{label}】共享 {len(shared)} · {name_a} 独有 {len(only_a)} · {name_b} 独有 {len(only_b)}")
            for m in only_a[:3]:
                lines.append(f"  + {name_a}: {m.get('body', '')[:50]}")
            for m in only_b[:3]:
                lines.append(f"  + {name_b}: {m.get('body', '')[:50]}")
            lines.append("")
            break

    # 规则对比
    rules_a = result.get("rules_only_a", [])
    rules_b = result.get("rules_only_b", [])
    if rules_a or rules_b:
        lines.append(f"【表达规则】{name_a} 独有 {len(rules_a)} · {name_b} 独有 {len(rules_b)}")
        for r in rules_a[:3]:
            lines.append(f"  + {name_a}: {r[:50]}")
        for r in rules_b[:3]:
            lines.append(f"  + {name_b}: {r[:50]}")
        lines.append("")

    # 口头禅对比
    phrases_a = result.get("phrases_only_a", [])
    phrases_b = result.get("phrases_only_b", [])
    if phrases_a or phrases_b:
        lines.append(f"【口头禅】{name_a} 独有 {phrases_a} · {name_b} 独有 {phrases_b}")
        lines.append("")

    return "\n".join(lines)
