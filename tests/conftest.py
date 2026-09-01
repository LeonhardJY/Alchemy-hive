"""pytest 全局配置：cwd 隔离 + 共享 mock fixtures。

所有测试不得依赖"从项目根运行"——示例文件路径一律基于 Path(__file__) 解析，
而非相对 cwd 的 "examples/chat.txt"。
"""
import json as _json
import sys
from pathlib import Path

import httpx
import pytest

# 兜底：即使包未做 editable install，也能让测试导入 alchemy_hive（src 布局需把 src/ 入 path）。
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture
def examples_dir():
    """指向仓库 examples/ 目录，供需要真实聊天样本的测试使用。"""
    return EXAMPLES


# ---- 共享 LLM mock ----

# 默认的分析阶段返回值（json_mode=True 时）
_DEFAULT_ANALYSIS = {
    "display_name": "小明",
    "relationship": "好朋友",
    "expression_rules": ["一次只说一句话"],
    "memories": [{"slug": "core", "body": "一起在食堂研究菜单"}],
}

# 默认的 build 阶段返回值（json_mode=False 时）
_DEFAULT_BUILD_MD = "你是小明。\n一次只说一句话。"


class FakeResp:
    """模拟 httpx.Response，用于 mock httpx.post。"""

    def __init__(self, content: str, status_code: int = 200):
        self._content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code}",
                request=httpx.Request("POST", "http://x/chat/completions"),
                response=None,
            )

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class ErrorResp:
    """模拟返回特定 HTTP 状态码的响应。"""

    def __init__(self, status_code: int):
        self.status_code = status_code

    def raise_for_status(self):
        raise httpx.HTTPStatusError(
            f"{self.status_code}",
            request=httpx.Request("POST", "http://x/chat/completions"),
            response=None,
        )


def make_fake_post(analysis: dict | None = None, build_md: str = _DEFAULT_BUILD_MD):
    """创建一个 mock httpx.post 工厂函数。

    - json_mode=True（分析阶段）→ 返回 analysis JSON
    - json_mode=False（撰写阶段）→ 返回 build_md 文本
    - 返回捕获的请求参数，供测试断言

    用法：
        captured = {}
        monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", make_fake_post(captured=captured))
    """
    captured: dict = {}

    def fake_post(*a, **k):
        captured.update(k)
        captured["url"] = a[0]
        body = k.get("json") or {}
        if body.get("response_format"):
            content = _json.dumps(analysis or _DEFAULT_ANALYSIS, ensure_ascii=False)
        else:
            content = build_md
        return FakeResp(content)

    fake_post.captured = captured
    return fake_post


def make_error_post(error: Exception):
    """创建一个总是抛出指定异常的 mock httpx.post。"""

    def fake_post(*a, **k):
        raise error

    return fake_post


@pytest.fixture
def mock_llm(monkeypatch):
    """标准 LLM mock：analyze 返回 JSON，build 返回 MD。返回捕获的请求参数。"""
    captured: dict = {}
    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", make_fake_post(captured=captured))
    # 隔离本机配置
    monkeypatch.setattr("alchemy_hive.gui.actions.load_config", lambda path=None: {})
    return captured


@pytest.fixture
def model_config():
    """标准模型配置（测试用，不发真实请求）。"""
    return {"base_url": "http://x", "api_key": "k", "model": "m"}
