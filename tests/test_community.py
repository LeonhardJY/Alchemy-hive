from weflow_agent.core.community import build_community


def test_build_community_lists_agents():
    comm = build_community(["张書源", "张鹏博"], "build/export")
    assert comm["channel"] == "#friends"
    assert len(comm["agents"]) == 2
    assert comm["agents"][0]["displayName"] == "张書源"
    assert comm["agents"][0]["agentJson"] == "build/export/张書源.agent.json"
    assert comm["agents"][0]["subscribe"] == ["#friends"]
    assert "setup_steps" in comm and len(comm["setup_steps"]) >= 3


def test_build_community_triggers():
    comm = build_community(["张書源"], "build/export")
    assert "@张書源" in comm["agents"][0]["triggers"]
