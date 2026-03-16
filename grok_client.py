"""
Grok API 异步客户端

通过 xAI Responses API 调用 Grok 进行真正的联网搜索
重要：使用 /v1/responses 端点而非 /v1/chat/completions
因为只有 Responses API 才支持 web_search 工具实现真正的联网搜索
"""

import asyncio
import json
import re
import time
from typing import Any

import aiohttp

# 默认系统提示词（要求返回 JSON 格式，LLM Tool 和 Skill 使用）
DEFAULT_JSON_SYSTEM_PROMPT = (
    "You are a web research assistant. Use live web search/browsing when answering. "
    "Return ONLY a single JSON object with keys: "
    "content (string), sources (array of objects with url/title/snippet when possible). "
    "Keep content concise and evidence-backed. "
    "IMPORTANT: Do NOT use Markdown formatting in the content field - use plain text only."
)


def normalize_api_key(api_key: str) -> str:
    """过滤占位符 API Key"""
    api_key = api_key.strip()
    if not api_key:
        return ""
    placeholder = {"YOUR_API_KEY", "API_KEY", "CHANGE_ME", "REPLACE_ME"}
    if api_key.upper() in placeholder:
        return ""
    return api_key


def normalize_base_url(base_url: str) -> str:
    """规范化 Base URL，移除尾部 / 和 /v1"""
    base_url = base_url.strip().rstrip("/")
    if base_url.endswith("/v1"):
        return base_url[: -len("/v1")]
    return base_url


def _normalize_base_url_value(base_url: str) -> str:
    """过滤占位符 Base URL"""
    base_url = base_url.strip()
    if not base_url:
        return ""
    placeholder = {
        "HTTPS://YOUR-GROK-ENDPOINT.EXAMPLE",
        "YOUR_BASE_URL",
        "BASE_URL",
        "CHANGE_ME",
        "REPLACE_ME",
    }
    if base_url.upper() in placeholder:
        return ""
    return base_url


def _coerce_json_object(text: str) -> dict[str, Any] | None:
    """尝试将字符串解析为 JSON 对象"""
    text = text.strip()
    if not text:
        return None
    if text.startswith("{") and text.endswith("}"):
        try:
            value = json.loads(text)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _extract_urls(text: str) -> list[str]:
    """从文本中提取 URL"""
    urls = re.findall(r"https?://[^\s)\]}>\"']+", text)
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        url = url.rstrip(".,;:!?'\"")
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def parse_json_config(value: str) -> tuple[dict[str, Any], str | None]:
    """解析 JSON 配置字符串

    Returns:
        (parsed_dict, error_message): 解析结果和错误信息，无错误时 error_message 为 None
    """
    if not value or not value.strip():
        return {}, None
    try:
        parsed = json.loads(value)
        return (parsed if isinstance(parsed, dict) else {}, None)
    except json.JSONDecodeError as e:
        return {}, f"JSON 配置解析失败: {e}"


async def grok_search(
    query: str,
    base_url: str,
    api_key: str,
    model: str = "grok-4-fast",
    timeout: float = 60.0,
    enable_thinking: bool = True,
    thinking_budget: int = 32000,
    extra_body: dict | None = None,
    extra_headers: dict | None = None,
    session: aiohttp.ClientSession | None = None,
    system_prompt: str | None = None,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    retryable_status_codes: set[int] | None = None,
    images: list[str] | None = None,
    proxy: str | None = None,
) -> dict[str, Any]:
    """
    调用 Grok API 进行联网搜索（异步）

    使用 xAI Responses API (/v1/responses) 而非 Chat Completions API (/v1/chat/completions)
    因为只有 Responses API 才支持 web_search 工具实现真正的联网搜索

    Args:
        query: 搜索查询内容
        base_url: Grok API 端点
        api_key: API 密钥
        model: 模型名称
        timeout: 超时时间（秒）
        enable_thinking: 是否开启思考模式（已弃用，Grok 4.20+ 通过模型名称区分）
        thinking_budget: 思考 token 预算（已弃用）
        extra_body: 额外请求体参数
        extra_headers: 额外请求头
        session: 可选的 aiohttp.ClientSession，传入时复用，否则创建临时 session
        system_prompt: 自定义系统提示词，为 None 时使用默认提示词
        max_retries: 最大重试次数（默认 3 次）
        retry_delay: 重试间隔时间（秒，默认 1.0）
        retryable_status_codes: 可重试的 HTTP 状态码集合，为 None 时使用默认值
        images: 可选的 base64 编码图片列表，用于构建多模态消息
        proxy: HTTP 代理地址，例如 http://127.0.0.1:7890

    Returns:
        {
            "ok": bool,
            "content": str,      # 综合答案
            "sources": list,     # 来源列表 [{url, title, snippet}]
            "raw": str,          # 原始响应（解析失败时）
            "error": str,        # 错误信息（失败时）
            "elapsed_ms": int,   # 耗时
            "retries": int,      # 重试次数
            "citations": list,   # 引用来源列表（来自 API）
        }
    """
    started = time.time()

    # 验证必要参数
    base_url = _normalize_base_url_value(base_url)
    api_key = normalize_api_key(api_key)

    if not base_url:
        return {
            "ok": False,
            "error": "缺少 base_url 配置，请在插件设置中填写 Grok API 端点",
            "content": "",
            "sources": [],
            "raw": "",
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    if not api_key:
        return {
            "ok": False,
            "error": "缺少 api_key 配置，请在插件设置中填写 API 密钥",
            "content": "",
            "sources": [],
            "raw": "",
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    # 使用 Responses API 端点（而非 chat/completions）
    url = f"{normalize_base_url(base_url)}/v1/responses"

    # 使用自定义提示词或默认提示词
    final_system_prompt = (
        system_prompt if system_prompt is not None else DEFAULT_JSON_SYSTEM_PROMPT
    )

    # 构建用户消息内容
    if images:
        user_content: list[dict[str, Any]] = [{"type": "input_text", "text": query}]
        for img_b64 in images:
            user_content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{img_b64}",
                    "detail": "high",
                }
            )
        user_input = user_content
    else:
        user_input = query

    # 构建 Responses API 请求体
    body: dict[str, Any] = {
        "model": model,
        "input": [
            {"role": "system", "content": final_system_prompt},
            {"role": "user", "content": user_input},
        ],
        # 启用 web_search 工具实现真正的联网搜索
        "tools": [{"type": "web_search"}],
    }

    if extra_body:
        # 保护关键字段不被覆盖
        protected_keys = {"model", "input", "tools", "stream"}
        for key, value in extra_body.items():
            if key not in protected_keys:
                body[key] = value

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if extra_headers:
        # 保护关键请求头不被覆盖
        protected_headers = {"authorization", "content-type"}
        for key, value in extra_headers.items():
            if str(key).lower() not in protected_headers:
                headers[str(key)] = str(value)

    async def _do_request(
        s: aiohttp.ClientSession,
        proxy: str | None = None,
    ) -> dict[str, Any]:
        async with s.post(
            url,
            json=body,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout),
            proxy=proxy,
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                # 友好的错误提示
                error_hints = {
                    400: "请求格式错误，请检查配置",
                    401: "认证失败，请检查 api_key 是否正确",
                    403: "访问被拒绝，请检查 API 权限",
                    404: "API 端点不存在，请检查 base_url 配置（应使用 /v1/responses）",
                    429: "请求过于频繁，请稍后重试",
                    500: "服务器内部错误",
                    502: "网关错误，API 服务可能暂时不可用",
                    503: "服务暂时不可用，请稍后重试",
                }
                hint = error_hints.get(resp.status, "")
                error_msg = f"HTTP {resp.status}"
                if hint:
                    error_msg = f"{error_msg} - {hint}"
                return {
                    "ok": False,
                    "error": error_msg,
                    "content": "",
                    "sources": [],
                    "raw": error_text[:2000] if error_text else "",
                    "elapsed_ms": int((time.time() - started) * 1000),
                }

            # 读取响应内容
            raw_text = await resp.text()

            # 尝试解析 JSON 响应
            try:
                data = json.loads(raw_text)
                return {"ok": True, "data": data}
            except json.JSONDecodeError as e:
                return {
                    "ok": False,
                    "error": "响应解析失败，API 返回了非 JSON 格式的数据",
                    "content": str(e),
                    "sources": [],
                    "raw": raw_text[:2000] if raw_text else "",
                    "elapsed_ms": int((time.time() - started) * 1000),
                }

    # 可重试的错误状态码（默认值）
    if retryable_status_codes is None:
        retryable_status_codes = {429, 500, 502, 503, 504}

    result = None
    last_error = None
    retry_count = 0

    for attempt in range(max_retries + 1):
        try:
            if session is not None:
                result = await _do_request(session, proxy=proxy)
            else:
                async with aiohttp.ClientSession() as temp_session:
                    result = await _do_request(temp_session, proxy=proxy)

            # 检查是否需要重试
            if result.get("ok"):
                # 成功的响应，跳出循环
                break

            # 检查是否为可重试的错误
            error_msg = result.get("error", "")
            should_retry = False

            # HTTP 状态码可重试
            if any(f"HTTP {code}" in error_msg for code in retryable_status_codes):
                should_retry = True

            if should_retry and attempt < max_retries:
                retry_count = attempt + 1
                await asyncio.sleep(retry_delay * (attempt + 1))  # 线性递增退避
                continue

            # 不可重试的错误，直接返回
            break

        except aiohttp.ClientError as e:
            last_error = f"网络请求失败: {e}"
            if attempt < max_retries:
                retry_count = attempt + 1
                await asyncio.sleep(retry_delay * (attempt + 1))
                continue
            return {
                "ok": False,
                "error": last_error,
                "content": "",
                "sources": [],
                "raw": "",
                "elapsed_ms": int((time.time() - started) * 1000),
                "retries": retry_count,
            }
        except TimeoutError:
            last_error = (
                f"请求超时（{timeout}秒），请检查网络或增加 timeout_seconds 配置"
            )
            if attempt < max_retries:
                retry_count = attempt + 1
                await asyncio.sleep(retry_delay * (attempt + 1))
                continue
            return {
                "ok": False,
                "error": last_error,
                "content": "",
                "sources": [],
                "raw": "",
                "elapsed_ms": int((time.time() - started) * 1000),
                "retries": retry_count,
            }

    if result is None:
        return {
            "ok": False,
            "error": last_error or "未知错误",
            "content": "",
            "sources": [],
            "raw": "",
            "elapsed_ms": int((time.time() - started) * 1000),
            "retries": retry_count,
        }

    if not result.get("ok") or "data" not in result:
        result["retries"] = retry_count
        return result
    data = result["data"]

    # 解析 Responses API 响应
    message = ""
    citations: list[dict[str, str]] = []
    usage_info = {}
    parse_error = ""

    try:
        # 检查 API 错误响应
        if "error" in data and isinstance(data.get("error"), (dict, str)):
            error_info = data["error"]
            error_msg = (
                error_info.get("message", str(error_info))
                if isinstance(error_info, dict)
                else str(error_info)
            )
            return {
                "ok": False,
                "error": f"API 返回错误: {error_msg}",
                "content": "",
                "sources": [],
                "raw": json.dumps(data, ensure_ascii=False)[:2000],
                "elapsed_ms": int((time.time() - started) * 1000),
            }

        # Responses API 的响应格式：
        # output 是一个数组，包含 web_search_call、reasoning、message 等元素
        output = data.get("output", [])
        if not output:
            parse_error = "响应缺少 output 字段"
        else:
            # 查找 message 类型的输出（最终回复）
            for item in output:
                if item.get("type") == "message":
                    content_list = item.get("content", [])
                    for content_item in content_list:
                        if content_item.get("type") == "output_text":
                            message = content_item.get("text", "")
                            # 提取引用/注释（citations）
                            annotations = content_item.get("annotations", [])
                            for ann in annotations:
                                if ann.get("type") == "url_citation":
                                    citations.append({
                                        "url": ann.get("url", ""),
                                        "title": ann.get("title", ""),
                                    })
                            break
                    break

            # 提取 usage 信息
            usage = data.get("usage", {})
            if usage:
                usage_info = {
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                }

        if not message:
            parse_error = parse_error or "API 返回了空响应"

    except (KeyError, IndexError, TypeError) as e:
        parse_error = f"响应结构解析失败: {type(e).__name__}: {e}"

    # 响应为空时返回失败
    if not message:
        error_detail = parse_error or "API 返回了空响应"
        return {
            "ok": False,
            "error": f"{error_detail}，请稍后重试",
            "content": "",
            "sources": [],
            "raw": json.dumps(data, ensure_ascii=False)[:2000] if data else "",
            "elapsed_ms": int((time.time() - started) * 1000),
            "retries": retry_count,
        }

    # 尝试解析 JSON 格式的响应
    parsed = _coerce_json_object(message)
    sources: list[dict[str, Any]] = []
    content = ""
    raw = ""

    if parsed is not None:
        content = str(parsed.get("content") or "")
        src = parsed.get("sources")
        if isinstance(src, list):
            for item in src:
                if isinstance(item, dict) and item.get("url"):
                    sources.append(
                        {
                            "url": str(item.get("url")),
                            "title": str(item.get("title") or ""),
                            "snippet": str(item.get("snippet") or ""),
                        }
                    )
        if not sources:
            for url_str in _extract_urls(content):
                sources.append({"url": url_str, "title": "", "snippet": ""})
    else:
        raw = message
        content = message
        for url_str in _extract_urls(message):
            sources.append({"url": url_str, "title": "", "snippet": ""})

    # 如果没有从 JSON 中提取到 sources，使用 API 返回的 citations
    if not sources and citations:
        for cit in citations:
            sources.append({
                "url": cit.get("url", ""),
                "title": cit.get("title", ""),
                "snippet": "",
            })

    return {
        "ok": True,
        "content": content,
        "sources": sources,
        "raw": raw,
        "model": data.get("model") or model,
        "usage": usage_info,
        "elapsed_ms": int((time.time() - started) * 1000),
        "retries": retry_count,
        "citations": citations,
    }
