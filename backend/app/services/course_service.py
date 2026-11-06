"""拆课服务。

把上传的资料拆成「课程 → 章节 → 知识点」，并为每个知识点摘录原文锚点。
超长资料按标题/空行切成 ≤8000 字块逐块拆课，再合并，禁止静默截断假装覆盖全书。
"""
from __future__ import annotations

import io
import logging
import re
import zipfile

from ..core.llm import LLMError, get_llm
from ..models.schemas import ChapterOutline, CourseOutline

log = logging.getLogger("ai-tutor.course")

# 每块喂给模型的上限；总块数硬顶，避免 ZIP 拼出几十段后串行调用把请求拖死
MAX_CHUNK_CHARS = 8000
MAX_CHUNKS = 4
MAX_INPUT_CHARS = MAX_CHUNK_CHARS * MAX_CHUNKS

_SKIP_ZIP_DIRS = {"__macosx", "node_modules", ".git", "dist", ".venv", "venv", ".idea"}
_SKIP_ZIP_FILES = {
    "license", "license.md", "license.txt", "licence", "licence.md",
    "copying", "notice", "changelog", "changelog.md", "changelog.txt",
}
MAX_ZIP_FILES = 30
MAX_ZIP_FILE_BYTES = 300_000

SYSTEM_FIRST = """你是一位资深的课程架构师。把下面这份学习资料拆解成结构清晰的课程大纲。

拆解要求：
1. 给出准确的课程标题 title。
2. 按逻辑分成若干「章节」（本段最多 4 个章节）。
3. 每个章节下拆出若干「知识点」（本段合计最多 8 个知识点）。
4. 知识点标题要具体，不要泛泛而谈。
5. 每个知识点配一句 summary，概括核心结论。
6. excerpts：每个知识点只摘 1 段原文，不超过 80 字，必须原样照抄。
7. loc 标明摘录位置（章节标题或「第 N 段」）。
8. 不要编造资料里没有的内容。

只返回一个合法 JSON 对象（双引号、无代码块、无注释、无尾逗号）：
{"title":"...","chapters":[{"title":"...","lessons":[{"title":"...","summary":"...","excerpts":["..."],"loc":"..."}]}]}
"""

SYSTEM_NEXT = """你是课程架构师。下面是同一份资料的后续片段，请只拆这一段。

本段最多 4 个章节、合计最多 8 个知识点。
每个知识点 excerpts 只摘 1 段原文，不超过 80 字，原样照抄。给出 loc。
不要重复前文导论。本段不必再给整门课总标题。

只返回一个合法 JSON 对象（双引号、无代码块、无注释、无尾逗号）：
{"chapters":[{"title":"...","lessons":[{"title":"...","summary":"...","excerpts":["..."],"loc":"..."}]}]}
"""


def chunk_text(text: str) -> list[str]:
    """优先在 Markdown 标题处切，其次空行，再次句号边界；每块 ≤ 8000 字符。"""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]

    parts = re.split(r"(?=\n#{1,6}\s)", "\n" + text)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        parts = [text]

    chunks: list[str] = []
    buf = ""
    for part in parts:
        if len(part) > MAX_CHUNK_CHARS:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.extend(_split_long(part, MAX_CHUNK_CHARS))
        elif buf and len(buf) + 2 + len(part) > MAX_CHUNK_CHARS:
            chunks.append(buf)
            buf = part
        else:
            buf = f"{buf}\n\n{part}" if buf else part
    if buf:
        chunks.append(buf)
    return chunks


def _split_long(s: str, max_len: int) -> list[str]:
    paras = re.split(r"\n\s*\n", s)
    out: list[str] = []
    buf = ""
    for p in paras:
        p = p.strip()
        if not p:
            continue
        if len(p) > max_len:
            if buf:
                out.append(buf)
                buf = ""
            out.extend(_split_sentences(p, max_len))
        elif buf and len(buf) + 2 + len(p) > max_len:
            out.append(buf)
            buf = p
        else:
            buf = f"{buf}\n\n{p}" if buf else p
    if buf:
        out.append(buf)
    return out or [s[:max_len]]


def _split_sentences(s: str, max_len: int) -> list[str]:
    bits = re.split(r"(?<=[。！？.!?\n])", s)
    out: list[str] = []
    buf = ""
    for b in bits:
        if not b:
            continue
        if buf and len(buf) + len(b) > max_len:
            out.append(buf)
            buf = b
        else:
            buf += b
        while len(buf) > max_len:
            out.append(buf[:max_len])
            buf = buf[max_len:]
    if buf:
        out.append(buf)
    return out


def _merge_chapters(chapters: list[ChapterOutline]) -> list[ChapterOutline]:
    merged: list[ChapterOutline] = []
    for ch in chapters:
        if not ch.lessons:
            continue
        if merged and merged[-1].title.strip() == ch.title.strip():
            merged[-1].lessons.extend(ch.lessons)
        else:
            merged.append(ch)
    return merged


def _skip_zip_path(name: str) -> bool:
    parts = name.replace("\\", "/").split("/")
    if any(p.startswith("..") for p in parts):
        return True
    lowered = [p.lower() for p in parts]
    if any(p in _SKIP_ZIP_DIRS for p in lowered):
        return True
    base = parts[-1].lower()
    if not base or base.startswith("._"):
        return True
    if base in _SKIP_ZIP_FILES:
        return True
    return False


def extract_zip_text(raw: bytes) -> tuple[str, bool]:
    """从 zip 抽出学习正文。过滤系统目录/许可证，限制文件数与总字数。

    返回 (文本, 是否截断)。
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as e:
        raise ValueError("无法打开 ZIP，文件可能已损坏") from e

    md_files: list[zipfile.ZipInfo] = []
    txt_files: list[zipfile.ZipInfo] = []
    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        if name.endswith("/") or info.is_dir():
            continue
        if _skip_zip_path(name):
            continue
        if info.file_size > MAX_ZIP_FILE_BYTES:
            continue
        lower = name.lower()
        if lower.endswith((".md", ".markdown")):
            md_files.append(info)
        elif lower.endswith(".txt"):
            txt_files.append(info)

    candidates = md_files or txt_files
    truncated = len(candidates) > MAX_ZIP_FILES
    picked = candidates[:MAX_ZIP_FILES]
    if not picked:
        raise ValueError("压缩包里没有可用的 Markdown / 文本（已忽略系统文件和许可证）")

    texts: list[str] = []
    total = 0
    for info in picked:
        if total >= MAX_INPUT_CHARS:
            truncated = True
            break
        data = zf.read(info.filename)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("gbk", errors="ignore")
        text = text.strip()
        if not text:
            continue
        room = MAX_INPUT_CHARS - total
        if len(text) > room:
            texts.append(text[:room])
            truncated = True
            break
        texts.append(text)
        total += len(text) + 2  # 计入后续 join 的分隔符

    if not texts:
        raise ValueError("压缩包里的文本文件都是空的")
    joined = "\n\n".join(texts)
    if len(joined) > MAX_INPUT_CHARS:
        joined = joined[:MAX_INPUT_CHARS]
        truncated = True
    return joined, truncated


async def _llm_outline_chunk(chunk: str, is_first: bool) -> dict:
    llm = get_llm()
    system = SYSTEM_FIRST if is_first else SYSTEM_NEXT
    user = f"请把下面的学习资料拆解成课程大纲：\n\n{chunk}"
    try:
        # 本地会修 JS 风格 JSON；仍失败时最多再生成 2 次
        return await llm.chat_json(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            retries=2,
        )
    except LLMError as e:
        raise ValueError(f"拆课失败：{e}") from e


async def parse_outline(content: str) -> CourseOutline:
    """把资料全文解析成课程大纲（校验后的 Pydantic 对象）。"""
    if not content or not content.strip():
        raise ValueError("资料内容为空")

    truncated = len(content) > MAX_INPUT_CHARS
    if truncated:
        content = content[:MAX_INPUT_CHARS]

    chunks = chunk_text(content)
    if not chunks:
        raise ValueError("资料内容为空")
    if len(chunks) > MAX_CHUNKS:
        log.info("parse_outline 截断块数 %s -> %s", len(chunks), MAX_CHUNKS)
        chunks = chunks[:MAX_CHUNKS]
        truncated = True

    log.info("parse_outline chars=%s chunks=%s truncated=%s", len(content), len(chunks), truncated)

    title = ""
    all_chapters: list[ChapterOutline] = []

    for i, chunk in enumerate(chunks):
        try:
            data = await _llm_outline_chunk(chunk, is_first=(i == 0))
        except ValueError:
            if i == 0:
                raise
            continue
        if i == 0:
            title = (data.get("title") or "").strip()
        raw_chapters = data.get("chapters") or []
        for ch in raw_chapters:
            try:
                all_chapters.append(ChapterOutline.model_validate(ch))
            except Exception:
                continue

    if not title:
        title = "未命名课程"
    if truncated:
        title = title if "仅基于部分资料" in title else f"{title}（仅基于部分资料）"
    merged = _merge_chapters(all_chapters)
    if not merged:
        raise ValueError("拆课结果没有任何章节")

    # 丢掉没有摘录的空壳知识点；摘录失败时仍保留（旧模型可能漏字段），但尽量清洗空 title
    cleaned: list[ChapterOutline] = []
    for ch in merged:
        lessons = [l for l in ch.lessons if l.title.strip()]
        if lessons:
            cleaned.append(ChapterOutline(title=ch.title, lessons=lessons))
    if not cleaned:
        raise ValueError("拆课结果没有任何知识点")

    return CourseOutline(title=title, chapters=cleaned)
