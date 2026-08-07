"""本地自检 doctor：检查配置完整性与端点连通性，**不发 LLM 请求、不消耗 token**。

用 GET {base_url}/models 探测连通性（200=密钥有效，401=端点可达需鉴权，均说明网络正常），
避免用户反复试错式调用 API 排查国内网络问题。
"""
from pathlib import Path

import httpx

from .distill import load_config


def run_doctor(config_path: str = ".alchemy-hive/config.toml") -> list[str]:
    lines: list[str] = []
    p = Path(config_path)
    if not p.exists():
        lines.append(f"✗ 未找到配置文件 {config_path}。")
        lines.append("  请先复制 .alchemy-hive/config.toml.example 为 config.toml 并填入模型信息。")
        return lines

    cfg = load_config(config_path) or {}
    model = cfg.get("model") or {}
    missing = [k for k in ("base_url", "api_key", "model") if not model.get(k)]
    if missing:
        lines.append(f"✗ 配置缺失 [model] 字段：{'、'.join(missing)}。请补全。")
    lines.append(f"✓ model：{model.get('model') or '（未填）'}")
    lines.append(f"✓ api_key：{'已设置' if model.get('api_key') else '未设置'}")

    base_url = (model.get("base_url") or "").strip()
    if not base_url:
        lines.append("✗ base_url 未填写，无法探测连通性。")
        return lines
    if not base_url.startswith(("http://", "https://")):
        lines.append(f"✗ base_url 格式不正确：{base_url!r}（应以 http:// 或 https:// 开头）")
        return lines
    lines.append(f"✓ base_url：{base_url}")

    lines.append("→ 探测端点连通性（GET /models，不消耗 token）…")
    lines.extend(_probe_endpoint(base_url))
    return lines


def _probe_endpoint(base_url: str) -> list[str]:
    url = f"{base_url.rstrip('/')}/models"
    try:
        resp = httpx.get(url, timeout=8)
    except httpx.ConnectError:
        return ["✗ 无法连接：端点被墙/需代理/地址错误。国内网络请用 DeepSeek/通义/Kimi/智谱等国内直连模型。"]
    except httpx.TimeoutException:
        return ["✗ 连接超时：网络较慢或被拦截。可稍后重试。"]
    except httpx.HTTPError as e:
        return [f"✗ 请求失败：{e}"]
    if resp.status_code == 200:
        return ["✓ 端点可达且密钥有效（HTTP 200）。网络与鉴权均正常，可以运行 distill。"]
    if resp.status_code == 401:
        return ["✓ 端点可达（HTTP 401=需鉴权，属正常，说明网络连通）。请确认 API key 正确。"]
    return [f"⚠ 端点可达但返回 HTTP {resp.status_code}：请检查 API key / 模型名 / 余额。"]
