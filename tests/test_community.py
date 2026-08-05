from alchemy_hive.core.community import build_community


def test_build_community_lists_agents():
    comm = build_community(["小明", "小红"], "build/export")
    assert comm["channel"] == "#friends"
    assert len(comm["agents"]) == 2
    assert comm["agents"][0]["displayName"] == "小明"
    assert comm["agents"][0]["agentJson"] == "build/export/小明.agent.json"
    assert comm["agents"][0]["subscribe"] == ["#friends"]
    assert "setup_steps" in comm and len(comm["setup_steps"]) >= 3


def test_build_community_triggers():
    comm = build_community(["小明"], "build/export")
    assert "@小明" in comm["agents"][0]["triggers"]


def test_build_community_custom_export_dir_in_setup():
    # 回归：自定义 workdir 时 setup 步骤必须指向实际 export_dir，而非硬编码 build/export
    comm = build_community(["A"], "/tmp/x/export")
    assert "/tmp/x/export" in comm["setup_steps"][0]
    assert "build/export" not in comm["setup_steps"][0]
