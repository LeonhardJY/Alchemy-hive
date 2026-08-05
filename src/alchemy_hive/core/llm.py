"""OpenAI-compatible LLM 客户端：distill 与 blindtest 共用。

统一负责：模型配置校验、请求组装、超时、对瞬时错误的有限重试、
JSON 模式（response_format）支持与兼容回退、非字符串响应归一化。
"""
import json
import time

import httpx


class LLMError(RuntimeError):
    """LLM 调用失败：缺少模型配置或网络/响应异常。"""


class _UnsupportedJSONMode(LLMError):
    """供应商拒绝 response_format（HTTP 400/422），需去掉 json_mode 重试。"""


_LABELS = {"base_url": "base_url", "api_key": "API key", "model": "model"}


def _raise_config_error(config: dict) -> None:
    model = config.get("model") or {}
    missing = [k for k in ("base_url", "api_key", "model") if not model.get(k)]
    if missing:
        labels = "、".join(_LABELS[k] for k in missing)
        raise LLMError(f"未配置模型 {labels}，请先配置 [model] 段相应字段。")


def chat_completion(
    config: dict,
    messages: list[dict],
    *,
    temperature: float = 0.7,
    json_mode: bool = False,
    timeout: float = 60,
    max_retries: int = 2,
    backoff: float = 0.4,
) -> str:
    """调 OpenAI-compatible /chat/completions，返回首个 choice 的文本内容。

    配置缺失立即抛 LLMError（不发请求）；对连接/超时/5xx 做有限重试；
    4xx（认证/参数错误）与响应解析错误不重试，直接抛 LLMError。
    json_mode 被供应商拒绝（400/422）时自动去掉 response_format 重试一次。
    """
    _raise_config_error(config)
    model = config["model"]
    url = f"{model['base_url'].rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {model['api_key']}"}

    def request(use_json_mode: bool) -> str:
        payload = {
            "model": model["model"],
            "messages": messages,
            "temperature": temperature,
        }
        if use_json_mode:
            payload["response_format"] = {"type": "json_object"}
        last_error: BaseException | None = None
        for attempt in range(max_retries + 1):
            try:
                resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                # DeepSeek 等推理模型部分响应 content 为 null → 空串；数字等非字符串 → str() 归一化
                if not isinstance(content, str):
                    content = "" if content is None else str(content)
                return content.strip()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response is not None else 0
                if use_json_mode and status in (400, 422):
                    raise _UnsupportedJSONMode() from e
                if status < 500:  # 4xx 重试无意义，报清错误让用户知道
                    raise LLMError(f"LLM 调用失败（HTTP {status}），请检查 base_url/api_key/model") from e
                last_error = e
            except httpx.HTTPError as e:
                last_error = e  # 连接/超时等瞬时错误：可重试
            except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
                raise LLMError("LLM 调用失败：响应无法解析") from e
            if attempt < max_retries:
                time.sleep(backoff)
        raise LLMError("LLM 调用失败，请检查配置和网络") from last_error

    try:
        return request(json_mode)
    except _UnsupportedJSONMode:
        # 供应商不支持 response_format：去掉 json_mode 再试一次
        return request(False)
