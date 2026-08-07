"""blindtest：盲测对拍（真实回复 vs agent 接话，人工打分）。"""
import json
from pathlib import Path

import typer

from ..core.models import Message
from ..core.blindtest import extract_pairs, ask_agent, rate_pairs
from ..core.safe import safe_filename
from .distill_cmd import _find_parsed

# 打分用模块级 input 引用：便于测试 monkeypatch alchemy_hive.cli.blindtest_cmd.input
input = input


def run_blindtest(name: str, workdir: str, config: dict, n: int) -> None:
    """逐条展示真实回复与 agent 接话，人工打 1-5 分，最后输出平均分。"""
    safe = safe_filename(name)
    parsed_path = _find_parsed(Path(workdir), name)
    if parsed_path is None:
        raise typer.BadParameter(
            f"未找到解析产物 {Path(workdir)/safe}.json 或 {Path(workdir)/'parsed'/safe}.json，请先运行 import"
        )
    msgs = [Message(**m) for m in json.loads(parsed_path.read_text(encoding="utf-8"))]
    persona_path = Path(workdir) / "persona" / f"{safe}.md"
    system_prompt = persona_path.read_text(encoding="utf-8") if persona_path.exists() else f"你是{name}。"

    pairs = extract_pairs(msgs, n=n)
    ratings: dict[int, int] = {}
    for i, pair in enumerate(pairs):
        typer.echo(f"\n--- 片段 {i + 1}/{len(pairs)} ---")
        for m in pair["context"]:
            typer.echo(f"  {m.sender}: {m.content}")
        typer.echo(f"  真实回复: {pair['real_reply'].content}")
        agent_reply = ask_agent(pair["context"], name, system_prompt, config)
        typer.echo(f"  agent 接话: {agent_reply}")
        aborted = False
        while True:
            try:
                score = int(input("相似度评分 (1-5): "))
                if 1 <= score <= 5:
                    ratings[i] = score
                    break
                typer.echo("请输入 1-5 的整数。")
            except ValueError:
                typer.echo("请输入 1-5 的整数。")
            except EOFError:
                # stdin 已关闭（如管道输入不足）：停止打分，避免死循环
                typer.echo("输入流已关闭，终止盲测。")
                aborted = True
                break
        if aborted:
            break

    summary = rate_pairs(pairs, ratings)
    typer.echo(f"\n盲测完成：共 {summary['count']} 条，平均分 {summary['average']}/5")
