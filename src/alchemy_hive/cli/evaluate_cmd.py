"""evaluate：自动评分蒸馏质量（LLM-as-judge）。"""
import json
from pathlib import Path

import typer

from ..core.evaluate import auto_evaluate
from ..core.safe import safe_filename


def run_evaluate(name: str, workdir: str, config: dict, n: int) -> None:
    """自动评分：从 persona 提取测试场景 → agent 回复 → judge LLM 评分。"""
    safe = safe_filename(name)
    persona_path = Path(workdir) / "persona" / f"{safe}.json"
    if not persona_path.exists():
        raise typer.BadParameter(f"未找到 persona {persona_path}，请先运行 distill")

    typer.echo(f"正在评估 {name} 的 persona 质量（{n} 个测试场景）…\n")
    result = auto_evaluate(str(persona_path), config, n_scenarios=n)

    # 输出报告
    score = result.get("overall", 0)
    color = "green" if score >= 70 else ("yellow" if score >= 40 else "red")
    typer.echo(f"━━━ 评估报告 ━━━")
    typer.echo(f"  总分：{score}/100")
    typer.echo(f"  真实感：{result.get('authenticity', 0)}/10")
    typer.echo(f"  一致性：{result.get('consistency', 0)}/10")
    typer.echo(f"  表达力：{result.get('expression', 0)}/10")
    typer.echo(f"  情感深度：{result.get('emotional_depth', 0)}/10")
    typer.echo(f"  总评：{result.get('summary', '')}")
    if result.get("suggestions"):
        typer.echo(f"\n改进建议：")
        for s in result["suggestions"]:
            typer.echo(f"  - {s}")

    # 输出测试详情
    test_results = result.get("test_results", [])
    if test_results:
        typer.echo(f"\n━━━ 测试详情（{len(test_results)} 个场景）━━━")
        for r in test_results:
            typer.echo(f"\n  场景：{r['scenario']}")
            typer.echo(f"  回复：{r['reply']}")
