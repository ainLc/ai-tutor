"""LLM 适配层。

统一封装大模型调用，业务代码只依赖本模块，不感知具体供应商。

能力：
- chat(messages)            -> str               非流式对话
- chat_stream(messages)     -> AsyncIterator     流式输出（逐段 yield）
- chat_json(messages)       -> dict              结构化输出（要求 JSON + 解析 + 有限重试）

设计对应课程「第 03 课结构化输出」：JSON 只是起点，程序还要解析、
校验并在预算内修复；传输失败与输出失败分别处理。
"""
from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar
from typing import AsyncIterator

import httpx

from .config import settings

log = logging.getLogger("ai-tutor.llm")


class LLMError(Exception):
    """LLM 调用失败。"""


class LLMNotConfigured(LLMError):
    """未配置 API key。"""


def _json_variants(text: str) -> list[str]:
    """生成几种常见「几乎是 JSON」的修复变体。"""
    variants = [text]
    # 中文引号
    cn = (
        text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    )
    variants.append(cn)
    # 尾逗号 {"a":1,} / [1,]
    variants.append(re.sub(r",\s*([}\]])", r"\1", text))
    variants.append(re.sub(r",\s*([}\]])", r"\1", cn))
    # 纯单引号 Python 字典
    if '"' not in text and "'" in text:
        variants.append(text.replace("'", '"'))
    # JS / Python 风格：未加引号的键、单引号字符串、True/None
    repaired = _repair_jsish(cn)
    variants.append(repaired)
    variants.append(re.sub(r",\s*([}\]])", r"\1", repaired))
    variants.append(_close_truncated_json(repaired))
    variants.append(_close_truncated_json(re.sub(r",\s*([}\]])", r"\1", repaired)))
    # 去重且保序
    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _repair_jsish(text: str) -> str:
    """把 JS/Python 风格对象尽量修成 JSON：未加引号的键、单引号、True/False/None。"""
    out: list[str] = []
    i = 0
    n = len(text)
    in_str = False
    quote = ""
    esc = False

    def skip_ws(j: int) -> int:
        while j < n and text[j] in " \t\n\r":
            j += 1
        return j

    def maybe_quote_key(j: int) -> int:
        """若当前位置是未加引号的键，写入 "key" 并返回新下标；否则原样返回。"""
        if j >= n or not (text[j].isalpha() or text[j] == "_"):
            return j
        k = j
        while k < n and (text[k].isalnum() or text[k] == "_"):
            k += 1
        key = text[j:k]
        ws = skip_ws(k)
        if ws < n and text[ws] == ":":
            out.append(f'"{key}"')
            out.append(text[k:ws])
            return ws
        return j

    while i < n:
        c = text[i]
        if in_str:
            if esc:
                out.append(c)
                esc = False
                i += 1
                continue
            if c == "\\":
                out.append(c)
                esc = True
                i += 1
                continue
            if c == quote:
                in_str = False
                out.append('"')
                i += 1
                continue
            if quote == "'" and c == '"':
                out.append('\\"')
                i += 1
                continue
            out.append(c)
            i += 1
            continue

        if c in "\"'":
            in_str = True
            quote = c
            out.append('"')
            i += 1
            continue

        if c in "{[":
            out.append(c)
            i += 1
            j = skip_ws(i)
            out.append(text[i:j])
            i = j
            if c == "{":
                i = maybe_quote_key(i)
            continue

        if c == ",":
            out.append(c)
            i += 1
            j = skip_ws(i)
            out.append(text[i:j])
            i = j
            i = maybe_quote_key(i)
            continue

        if c == ":":
            out.append(c)
            i += 1
            j = skip_ws(i)
            out.append(text[i:j])
            i = j
            if i < n and (text[i].isalpha() or text[i] == "_"):
                k = i
                while k < n and (text[k].isalnum() or text[k] in "_-."):
                    k += 1
                word = text[i:k]
                mapping = {
                    "True": "true",
                    "False": "false",
                    "None": "null",
                    "true": "true",
                    "false": "false",
                    "null": "null",
                }
                out.append(mapping.get(word, json.dumps(word, ensure_ascii=False)))
                i = k
            continue

        # Python 字面量（数组元素等）
        if c.isalpha() or c == "_":
            k = i
            while k < n and (text[k].isalnum() or text[k] == "_"):
                k += 1
            word = text[i:k]
            mapping = {"True": "true", "False": "false", "None": "null"}
            out.append(mapping.get(word, word))
            i = k
            continue

        out.append(c)
        i += 1
    return "".join(out)


def _close_truncated_json(text: str) -> str:
    """补全被截断的引号 / 括号，尽量抢救半截 JSON。"""
    in_str = False
    quote = ""
    esc = False
    stack: list[str] = []
    for c in text:
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == quote:
                in_str = False
            continue
        if c in "\"'":
            in_str = True
            quote = c
            continue
        if c in "{[":
            stack.append("}" if c == "{" else "]")
        elif c in "}]" and stack and stack[-1] == c:
            stack.pop()
    s = text
    if in_str:
        s += '"' if quote == "'" else quote
    # 去掉截断前的尾逗号
    s = re.sub(r",\s*$", "", s)
    while stack:
        s += stack.pop()
    return s


def _extract_json(text: str) -> dict:
    """从模型输出中稳健地提取 JSON 对象。

    模型常返回 ```json ... ``` 包裹、前后夹带文字、尾逗号、单引号或未加引号的键。
    """
    if not text or not str(text).strip():
        raise ValueError("模型返回为空")
    raw = str(text).strip().lstrip("\ufeff")

    candidates: list[str] = []
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    if fence:
        candidates.append(fence.group(1).strip())
    else:
        fence_open = re.search(r"```(?:json)?\s*(.*)$", raw, re.DOTALL | re.IGNORECASE)
        if fence_open:
            candidates.append(fence_open.group(1).strip())

    candidates.append(raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start : end + 1])
    elif start != -1:
        # 只有开括号、没有闭合：整段从 { 开始都拿去抢救
        candidates.append(raw[start:])

    last_err: Exception | None = None
    seen: set[str] = set()
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        for variant in _json_variants(cand):
            try:
                obj = json.loads(variant)
            except json.JSONDecodeError as e:
                last_err = e
                continue
            if isinstance(obj, dict):
                # 抢救 `{` → `{}` 不算成功，避免把截断当成空对象
                if not obj and not re.fullmatch(r"\{\s*\}", cand.strip()):
                    last_err = ValueError("模型只返回了半截 JSON")
                    continue
                return obj
            last_err = ValueError(f"JSON 根节点不是对象：{type(obj).__name__}")
    preview = raw[:180].replace("\n", "\\n")
    raise last_err or ValueError(f"无法从模型输出中解析 JSON：{preview}")


class LLMClient:
    """OpenAI 兼容的 LLM 客户端。"""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        timeout: float = 180.0,
    ):
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self.temperature = settings.llm_temperature if temperature is None else temperature
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _post(self, payload: dict, stream: bool = False):
        if not self.configured:
            raise LLMNotConfigured("未配置模型 API Key，请到「设置」页填写，或在 backend/.env 中配置。")
        url = f"{self.base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.post(
                url,
                headers=self._headers(),
                json=payload,
            )

    # ---- 非流式 ----
    async def chat(
        self,
        messages: list[dict],
        temperature: float | None = None,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> str:
        text, _finish = await self._chat_complete(
            messages,
            temperature=temperature,
            json_mode=json_mode,
            max_tokens=max_tokens,
        )
        return text

    async def _chat_complete(
        self,
        messages: list[dict],
        temperature: float | None = None,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> tuple[str, str | None]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if max_tokens:
            payload["max_tokens"] = max_tokens
        try:
            resp = await self._post(payload)
        except httpx.HTTPError as e:
            raise LLMError(f"网络请求失败：{e}") from e
        if resp.status_code != 200:
            # 部分兼容接口不支持 response_format，去掉后再试一次
            if json_mode and payload.get("response_format"):
                payload.pop("response_format", None)
                try:
                    resp = await self._post(payload)
                except httpx.HTTPError as e:
                    raise LLMError(f"网络请求失败：{e}") from e
            if resp.status_code != 200:
                raise LLMError(f"LLM 返回 {resp.status_code}：{resp.text[:300]}")
        data = resp.json()
        try:
            choice = data["choices"][0]
            msg = choice.get("message") or {}
            text = msg.get("content") or ""
            if not str(text).strip():
                text = msg.get("reasoning_content") or ""
            finish = choice.get("finish_reason")
            return text, finish
        except (KeyError, IndexError) as e:
            raise LLMError(f"响应格式异常：{data}") from e

    # ---- 流式 ----
    async def chat_stream(
        self, messages: list[dict], temperature: float | None = None
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "stream": True,
        }
        if not self.configured:
            raise LLMNotConfigured("未配置 LLM_API_KEY，请在 backend/.env 中填写。")
        url = f"{self.base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST", url, headers=self._headers(), json=payload
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise LLMError(f"LLM 返回 {resp.status_code}：{body[:300]!r}")
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0]["delta"].get("content", "")
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
                        if delta:
                            yield delta
        except httpx.HTTPError as e:
            raise LLMError(f"网络请求失败：{e}") from e

    # ---- 结构化输出 ----
    async def chat_json(
        self,
        messages: list[dict],
        retries: int = 2,
        temperature: float | None = None,
    ) -> dict:
        """要求模型返回 JSON，解析失败时在预算内重试（输出修复）。

        retries：初始生成失败后，最多再重试的次数。
        """
        last_error: str | None = None
        for attempt in range(retries + 1):
            msgs = list(messages)
            if last_error:
                msgs.append(
                    {
                        "role": "user",
                        "content": (
                            "上一次你返回的内容无法解析为合法 JSON。"
                            f"错误：{last_error}\n"
                            "请只返回一个完整的 JSON 对象：键和字符串必须用双引号，"
                            "例如 {\"title\":\"...\",\"chapters\":[]}。"
                            "不要 markdown 代码块，不要注释，不要尾逗号，不要单引号。"
                            "如果内容太长，请缩短 excerpts（每段不超过 80 字），保证 JSON 完整闭合。"
                        ),
                    }
                )
            # 首次走 json_object；解析仍失败则去掉该约束，避免部分接口返回半截/类 JS 对象
            use_json_mode = attempt == 0
            text = ""
            finish = None
            try:
                text, finish = await self._chat_complete(
                    msgs,
                    temperature=0.2 if temperature is None else temperature,
                    json_mode=use_json_mode,
                    max_tokens=4096,
                )
                return _extract_json(text)
            except (json.JSONDecodeError, ValueError) as e:
                last_error = str(e)
                log.warning(
                    "chat_json parse fail attempt=%s finish=%s err=%s preview=%r",
                    attempt,
                    finish,
                    e,
                    text[:240],
                )
            except LLMError:
                raise
        raise LLMError(f"结构化输出重试 {retries} 次后仍失败：{last_error}")


# 请求级覆盖（设置页保存后，下一次调用立刻走新厂商，无需重启）
_runtime: ContextVar[dict | None] = ContextVar("llm_runtime", default=None)
_env_client: LLMClient | None = None


def set_runtime_llm(cfg: dict | None) -> None:
    """绑定当前请求使用的模型配置。cfg 为 None 则回退 .env。"""
    _runtime.set(cfg)


def get_llm() -> LLMClient:
    rt = _runtime.get()
    if rt and rt.get("api_key"):
        return LLMClient(
            base_url=rt.get("base_url") or None,
            api_key=rt.get("api_key"),
            model=rt.get("model") or None,
            temperature=rt.get("temperature"),
        )
    global _env_client
    if _env_client is None:
        _env_client = LLMClient()
    return _env_client
