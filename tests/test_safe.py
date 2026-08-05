"""safe_filename 单元测试 + 路径穿越端到端防护测试。"""
import json
from pathlib import Path

from alchemy_hive.core.safe import safe_filename
from alchemy_hive.core.models import PersonaDoc


def test_safe_filename_keeps_chinese():
    assert safe_filename("张書源") == "张書源"


def test_safe_filename_blocks_path_traversal():
    out = safe_filename("../outside")
    assert "/" not in out and "\\" not in out
    assert out != "../outside"
    assert ".._outside" == out  # 分隔符替换为下划线，无法越出目录


def test_safe_filename_replaces_internal_slashes():
    assert safe_filename("a/b") == "a_b"
    assert safe_filename("a\\b") == "a_b"
    assert safe_filename("a:b") == "a_b"


def test_safe_filename_empty_and_dot_fallbacks():
    assert safe_filename("") == "unnamed"
    assert safe_filename("  ") == "unnamed"
    assert safe_filename(".") == "unnamed"
    assert safe_filename("..") == "unnamed"
    assert safe_filename("...") == "unnamed"


def test_safe_filename_reserved_device_names():
    assert safe_filename("con") == "_con"
    assert safe_filename("CON") == "_CON"
    assert safe_filename("com1") == "_com1"
    assert safe_filename("lpt9") == "_lpt9"
    assert safe_filename("aux") == "_aux"
    assert safe_filename("console") == "console"  # 非精确保留名不受影响
    assert safe_filename("com10") == "com10"      # 超出 com1-9 范围不受影响


def test_safe_filename_strips_trailing_dots_and_spaces():
    assert safe_filename("name.. ") == "name"
    assert safe_filename("name. ") == "name"
    assert safe_filename("name. .") == "name"  # 尾部的点与空格全部剥掉


def test_safe_filename_control_chars_replaced():
    assert "\x00" not in safe_filename("a\x00b")
    assert safe_filename("a\x1fb") == "a_b"


def test_import_path_traversal_stays_inside_out_dir(tmp_path):
    """端到端：name='../evil' 的解析产物必须落在 out_dir 内，不逃逸到上级目录。"""
    from alchemy_hive.cli.import_cmd import import_chat

    chat = str(Path(__file__).resolve().parent.parent / "examples" / "chat.txt")
    out = tmp_path / "out"
    import_chat(chat, "../evil", str(out))
    # 安全名文件在 out_dir 内
    assert (out / ".._evil.json").exists(), "产物应写入 out_dir 内的安全文件名"
    # 无逃逸：父目录 / 兄弟目录不应出现 evil.json
    assert not (tmp_path / "evil.json").exists(), "../evil.json 不得逃逸到父目录"
    assert not (tmp_path / "out" / ".." / "evil.json").resolve().exists()
    # 子目录解析产物用同一安全名（distill 侧可对上）
    parsed = out / ".._evil.json"
    assert len(json.loads(parsed.read_text(encoding="utf-8"))) > 0


def test_find_parsed_matches_safe_filename(tmp_path):
    """distill 的 _find_parsed 必须用 safe 名查找，否则找不到 import 写入的文件。"""
    from alchemy_hive.cli.distill_cmd import _find_parsed

    safe = safe_filename("../evil")
    (tmp_path / f"{safe}.json").write_text("[]", encoding="utf-8")
    found = _find_parsed(tmp_path, "../evil")
    assert found is not None, "应能找到 safe 名写入的解析产物"
    assert found.name == f"{safe}.json"

    # parsed/ 默认布局同样命中
    (tmp_path / "parsed").mkdir()
    (tmp_path / "parsed" / f"{safe}.json").write_text("[]", encoding="utf-8")
    found2 = _find_parsed(tmp_path, "../evil")
    assert found2 is not None
    assert found2.name == f"{safe}.json"


def test_export_and_snapshot_use_safe_name(tmp_path):
    """export 读 persona/{safe}.json 并写出 export/{safe}.agent.json，全程无越界。

    真实流：name（CLI 参数）可含路径分隔符，但 display_name 来自 LLM 不含分隔符；
    export 用 safe 名读产物、用 safe 名写导出文件名。
    """
    from alchemy_hive.cli.export_cmd import export_buzz

    safe = safe_filename("../evil")
    persona = tmp_path / "persona"
    persona.mkdir()
    doc = PersonaDoc(name="../evil", display_name="张書源", system_prompt="你是张書源。")
    (persona / f"{safe}.json").write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    export_buzz("../evil", str(tmp_path))
    p = tmp_path / "export" / f"{safe}.agent.json"
    assert p.exists(), "导出必须落在 export 目录内"
    assert not (tmp_path.parent / "evil.agent.json").exists()


def test_full_pipeline_path_traversal_safe(tmp_path, monkeypatch):
    """端到端：name='../evil' 走完整 import→distill→export，产物全部落在 workdir 内。"""
    import json as _json

    from typer.testing import CliRunner

    from alchemy_hive.cli.app import app

    def fake_post(*a, **k):
        payload = {
            "display_name": "张書源",
            "relationship": "好朋友",
            "expression_rules": ["一次只说一句话"],
            "system_prompt": "你是张書源。",
        }
        return type(
            "R",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {"choices": [{"message": {"content": _json.dumps(payload, ensure_ascii=False)}}]},
            },
        )()

    monkeypatch.setattr("alchemy_hive.core.distill.httpx.post", fake_post)
    runner = CliRunner()
    out = str(tmp_path)
    cfg = tmp_path / "cfg.toml"
    cfg.write_text("[model]\nbase_url=\"http://x\"\napi_key=\"k\"\nmodel=\"m\"\n", encoding="utf-8")
    chat = str(Path(__file__).resolve().parent.parent / "examples" / "chat.txt")

    r1 = runner.invoke(app, ["import", chat, "--name", "../evil", "--out-dir", out])
    assert r1.exit_code == 0, r1.output
    assert (tmp_path / ".._evil.json").exists()
    assert not (tmp_path.parent / "evil.json").exists()

    r2 = runner.invoke(app, ["distill", "--name", "../evil", "--workdir", out, "--config", str(cfg)])
    assert r2.exit_code == 0, r2.output
    assert (tmp_path / "persona" / ".._evil.md").exists()
    assert (tmp_path / "persona" / ".._evil.json").exists()

    r3 = runner.invoke(app, ["export", "--name", "../evil", "--workdir", out])
    assert r3.exit_code == 0, r3.output
    assert (tmp_path / "export" / ".._evil.agent.json").exists()
    assert not (tmp_path.parent / "evil.agent.json").exists()
