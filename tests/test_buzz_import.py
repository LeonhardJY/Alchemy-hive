"""buzz 导入助手：打开导出文件夹 + 复制完整路径到剪贴板。"""
import pytest

from alchemy_hive.buzz.importing import import_to_buzz


def test_import_to_buzz_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        import_to_buzz("小明", str(tmp_path))


def test_import_to_buzz_opens_folder_and_copies(monkeypatch, tmp_path):
    import alchemy_hive.buzz.importing as imp

    (tmp_path / "export").mkdir(parents=True)
    (tmp_path / "export" / "小明.agent.json").write_text("{}", encoding="utf-8")
    opened: list[str] = []
    copied: list[str] = []
    monkeypatch.setattr(imp, "_open_folder", lambda p: opened.append(str(p)) or True)
    monkeypatch.setattr(imp, "_copy_to_clipboard", lambda t: copied.append(t) or True)

    logs = import_to_buzz("小明", str(tmp_path))
    assert opened and opened[0].endswith("export")
    assert copied and "小明.agent.json" in copied[0]
    assert any("剪贴板" in l for l in logs)
    assert all(l.startswith("[buzz]") for l in logs)
