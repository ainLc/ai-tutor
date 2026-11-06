"""合上书答辩：隔夜提取证明，题面不展示原文。"""
from __future__ import annotations

from ..core.llm import LLMError, get_llm
from . import tutor_service

DEFENSE_SYSTEM = """你是合上书答辩考官。学生已经理解过关，现在要在不看资料的情况下用自己的话提取。

硬性要求：
1. 出 6 道开放提取题，覆盖不同知识点，禁止选择题、判断题。
2. 每题必须标明 lesson_id，题干不要泄露标准答案，也不要引用原文句子。
3. source_ref 必须从该知识点给出的原文摘录里逐字截取一句（不超过 80 字），用于事后核验；题面里不要出现这句话。
4. 问法要像答辩：对比、因果、适用边界、怎么用，不要名词解释背诵。

返回 JSON：
{"questions":[{"lesson_id":"...","question":"...","source_ref":"..."}]}"""


def _brief(lessons: list[dict]) -> str:
    lines = []
    for l in lessons[:16]:
        excerpts = l.get("source_excerpts") or []
        bits = []
        for item in excerpts[:2]:
            if isinstance(item, dict):
                bits.append((item.get("excerpt") or "")[:120])
            else:
                bits.append(str(item)[:120])
        loc = " | ".join([b for b in bits if b]) or (l.get("summary") or "")[:120]
        lines.append(
            f"- lesson_id={l.get('id')} 标题={l.get('title','')} 摘要={(l.get('summary') or '')[:80]}\n  摘录：{loc}"
        )
    return "\n".join(lines)


async def generate_defense_questions(lessons: list[dict]) -> list[dict]:
    """从已理解知识点出合上书题。失败则降级为标题提取题。"""
    llm = get_llm()
    by_id = {l.get("id"): l for l in lessons if l.get("id")}
    data: dict = {}
    try:
        data = await llm.chat_json(
            [
                {"role": "system", "content": DEFENSE_SYSTEM},
                {"role": "user", "content": f"已理解知识点：\n{_brief(lessons)}"},
            ]
        )
    except LLMError:
        data = {}

    out = []
    seen = set()
    for q in data.get("questions") or []:
        lid = (q.get("lesson_id") or "").strip()
        text = (q.get("question") or "").strip()
        if not lid or lid not in by_id or not text or lid in seen:
            continue
        lesson = by_id[lid]
        source_ref = (q.get("source_ref") or "").strip() or tutor_service._source_fallback(lesson)
        out.append({"lesson_id": lid, "question": text, "source_ref": source_ref[:200]})
        seen.add(lid)
        if len(out) >= 6:
            break

    if len(out) >= 4:
        return out[:6]

    fallback = []
    for l in lessons[:6]:
        title = l.get("title") or "这个知识点"
        fallback.append(
            {
                "lesson_id": l.get("id"),
                "question": f"请合上资料，用自己的话讲清「{title}」：它解决什么问题、关键对比是什么、什么情况下会用错。",
                "source_ref": tutor_service._source_fallback(l),
            }
        )
    return fallback
