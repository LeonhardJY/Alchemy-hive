"""pytest 全局配置：cwd 隔离。

所有测试不得依赖"从项目根运行"——示例文件路径一律基于 Path(__file__) 解析，
而非相对 cwd 的 "examples/chat.txt"。
"""
import sys
from pathlib import Path

import pytest

# 兜底：即使包未做 editable install，也能让测试导入 weflow_agent（配合 src 布局则需 src 入 path）。
sys.path.insert(0, str(Path(__file__).parent.parent))

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture
def examples_dir():
    """指向仓库 examples/ 目录，供需要真实聊天样本的测试使用。"""
    return EXAMPLES
