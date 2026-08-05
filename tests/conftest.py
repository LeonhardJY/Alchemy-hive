"""pytest 全局配置：cwd 隔离。

所有测试不得依赖"从项目根运行"——示例文件路径一律基于 Path(__file__) 解析，
而非相对 cwd 的 "examples/chat.txt"。
"""
import sys
from pathlib import Path

import pytest

# 兜底：即使包未做 editable install，也能让测试导入 alchemy_hive（src 布局需把 src/ 入 path）。
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture
def examples_dir():
    """指向仓库 examples/ 目录，供需要真实聊天样本的测试使用。"""
    return EXAMPLES
