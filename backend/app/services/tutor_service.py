"""教学引擎。

讲课（流式，锚定原文）、配图、反问、判断掌握度、纠正补讲、平行再测、制卡。
"""
from __future__ import annotations

from typing import AsyncIterator

from ..core.llm import LLMError, get_llm
from ..models.schemas import AnswerResult, MemoryCardOut

LECTURE_SYSTEM = """你是一位苏格拉底式的 AI 私教老师，最擅长把复杂知识讲得「通俗易懂、逻辑清楚、容易记住」。

讲解要求：
1. 用大白话解释，先讲「是什么」，再讲「为什么」，最后讲「怎么用」。
2. 逻辑层层递进，善用类比和生活中的例子帮助理解。
3. 突出「必须记住」的核心要点，用加粗标出。
4. 使用 Markdown 结构（小标题、列表），但不要堆砌术语。
5. 只讲解当前这个知识点，不要跑题。
6. 结尾不要提问（提问由系统单独完成）。
7. 讲解必须严格基于下面【原文摘录】的内容，不得编造摘录里没有的结论。
8. 如果摘录不足以讲清，宁可说「资料此处未展开」，不要用常识补。"""

DIAGRAM_PROMPT = """请为下面这个知识点画一张 Mermaid 图，帮助理解，可以是流程图、架构图、关系图或对比图，选最合适的一种。

只返回 mermaid 代码（不要 ```mermaid 包裹，不要任何解释文字）。

知识点：{title}

讲解内容：
{content}"""

QUESTION_PROMPT = """基于下面刚讲完的知识点，提出一个能检验用户是否真正理解的【开放提取题】。

要求：
1. 不要问死记硬背的题，要问「需要理解才能答对」的题。
2. 必须让学生用自己的话讲出来 / 对比 / 说明怎么用，禁止纯选择题。
3. 问题要具体、可回答，不空泛。
4. 只返回一个问题（一句或两句话）。

知识点：{title}

讲解内容：
{content}"""

JUDGE_SYSTEM = """你是一位耐心的 AI 老师，负责判断学生对一个知识点的掌握程度。

请根据学生的回答，判断其掌握程度，并给出反馈：
- mastered（已掌握）：回答正确、理解到位
- partial（部分掌握）：答对一部分，或有遗漏、理解偏差
- not_mastered（未掌握）：答错、跑题、或明显没理解

要求：
1. verdict 只能是 mastered / partial / not_mastered 之一。
2. feedback 是给学生的话，语气亲切但具体，先指出对在哪、错在哪，禁止空洞鼓励。
3. explanation 只在未掌握或部分掌握时填写，用于点出关键缺口；已掌握时留空。
4. gap 用一句话指出学生理解错或漏掉的具体点；已掌握时留空。

返回 JSON：
{"verdict": "mastered", "feedback": "...", "explanation": "...", "gap": "..."}"""

RETEACH_SYSTEM = """你是耐心私教。学生刚才答错了，你需要【换一个类比、换一种顺序】再讲一遍，针对他的错误缺口补讲，禁止复述第一遍原文。
只讲当前知识点，结尾不要提问。全文控制在 300 字以内。
必须基于【原文摘录】，不得编造摘录里没有的结论。"""

RETEST_SYSTEM = """基于这个知识点，再出一道与已问过的题【不等价措辞、同一考查目标】的开放提取题。
禁止与下面任何一道题重复。不要选择题。只返回一个问题本身，不要解释。"""

CHAPTER_QUIZ_SYSTEM = """你是课程收口考官。根据给出的知识点列表出 3–5 道开放提取题。
硬性要求：
1. 每题只考一个点，必须标明 lesson_id。
2. 至少覆盖本章 2 个不同知识点。
3. 如果提供了「旧点」，至少混入 1 道旧点题（interleaving）。
4. 禁止选择题，必须让学生讲出来 / 对比 / 说明怎么用。
5. 题干不要泄露标准答案。
返回 JSON：{"questions":[{"lesson_id":"...","question":"..."}]}"""

PRETEST_SYSTEM = """基于这个知识点的标题、摘要和原文摘录，出一道诊断前测题。
如果学生能用自己的话答对，就可以跳过初讲。不要选择题。只返回一个问题。
返回 JSON：{"question":"..."}"""

CARD_SYSTEM = """把下面这个知识点做成 3–8 张「主动提取」卡片。宁少勿滥。
允许类型：
- concept：用一句话定义 X
- cloze：填空，补出关键步骤/名词
- compare：A 与 B 在某维度的差别
- apply：遇到情境 S 该用哪一步、为什么
- figure：看着这张图说出 X（需要图时）
硬性要求：
1. 每张卡只考一个提取目标，不得把整段讲解塞成一张。
2. 每张卡尽量给 source_ref（能指回原文的一句或短语）；给不出时也可以留空，系统会自动补锚点。
3. 答案（back）要短、标准、可自评对错。
返回 JSON：{"cards":[{"card_type":"...","front":"...","back":"...","source_ref":"..."}]}"""


def _excerpt_text(lesson: dict) -> str:
    excerpts = lesson.get("source_excerpts") or []
    lines = []
    for item in excerpts:
        if isinstance(item, dict):
            text = (item.get("excerpt") or "").strip()
            loc = (item.get("loc") or "").strip()
            if text:
                lines.append(f"（{loc}）{text}" if loc else text)
        elif item:
            lines.append(str(item).strip())
    return "\n\n".join(lines)


def _has_excerpts(lesson: dict) -> bool:
    return bool(_excerpt_text(lesson).strip())


async def stream_lecture(lesson: dict) -> AsyncIterator[dict]:
    """流式讲课：正文（流式）→ 配图 → 反问。"""
    llm = get_llm()
    title = lesson.get("title", "")
    excerpts = _excerpt_text(lesson)
    if not excerpts:
        excerpts = lesson.get("summary") or "（本知识点缺少原文摘录，请谨慎讲解，标明不确定处。）"

    messages = [
        {"role": "system", "content": LECTURE_SYSTEM},
        {
            "role": "user",
            "content": (
                f"请讲解这个知识点：{title}\n\n"
                f"参考摘要：{lesson.get('summary', '')}\n\n"
                f"【原文摘录】\n{excerpts}\n\n"
                "开始讲解。"
            ),
        },
    ]
    content_parts: list[str] = []
    try:
        async for delta in llm.chat_stream(messages):
            content_parts.append(delta)
            yield {"type": "text", "content": delta}
    except LLMError as e:
        yield {"type": "error", "content": f"讲课失败：{e}"}
        return

    content = "".join(content_parts)

    try:
        extras = await llm.chat_json(
            [
                {"role": "system", "content": "你是一位绘图助手，根据讲解内容生成 Mermaid 图，并出一道开放提取题。"},
                {
                    "role": "user",
                    "content": (
                        DIAGRAM_PROMPT.format(title=title, content=content)
                        + "\n\n"
                        + QUESTION_PROMPT.format(title=title, content=content)
                        + "\n\n"
                        + '请严格按 {"diagram": "...", "question": "..."} 格式返回 JSON。'
                    ),
                },
            ]
        )
    except LLMError as e:
        yield {"type": "error", "content": f"生成配图/提问失败：{e}"}
        return

    diagram = extras.get("diagram", "").strip()
    question = extras.get("question", "").strip()

    if diagram:
        yield {"type": "diagram", "content": diagram}
    if question:
        yield {"type": "question", "content": question}
    yield {"type": "done", "content": ""}


async def stream_reteach(lesson: dict, wrong_answer: str, gap: str) -> AsyncIterator[dict]:
    """纠正性再教学：换类比/顺序，针对缺口补讲。"""
    llm = get_llm()
    excerpts = _excerpt_text(lesson) or (lesson.get("summary") or "")
    first = (lesson.get("content") or "")[:1200]
    messages = [
        {"role": "system", "content": RETEACH_SYSTEM},
        {
            "role": "user",
            "content": (
                f"知识点：{lesson.get('title', '')}\n\n"
                f"【原文摘录】\n{excerpts}\n\n"
                f"第一遍讲解要点：\n{first}\n\n"
                f"学生错误回答：{wrong_answer}\n"
                f"判题指出的缺口：{gap or '理解不到位'}\n\n"
                "请换角度补讲。"
            ),
        },
    ]
    try:
        async for delta in llm.chat_stream(messages):
            yield {"type": "text", "content": delta}
    except LLMError as e:
        yield {"type": "error", "content": f"补讲失败：{e}"}
        return
    yield {"type": "done", "content": ""}


async def judge_answer(lesson: dict, answer: str) -> AnswerResult:
    """判断用户回答的掌握程度。"""
    llm = get_llm()
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {
            "role": "user",
            "content": (
                f"知识点：{lesson.get('title', '')}\n\n"
                f"讲解要点：{(lesson.get('content') or '')[:1500]}\n\n"
                f"原文摘录：{_excerpt_text(lesson)[:800]}\n\n"
                f"学生回答：{answer}\n\n"
                "请判断掌握程度并给出反馈。"
            ),
        },
    ]
    try:
        data = await llm.chat_json(messages)
    except LLMError as e:
        return AnswerResult(
            verdict="partial",
            feedback=f"抱歉，判断你的回答时出了点问题：{e}",
            explanation="",
            next=False,
            gap="系统未能完成判断",
            retest_required=True,
        )

    verdict = data.get("verdict", "partial")
    if verdict not in ("mastered", "partial", "not_mastered"):
        verdict = "partial"
    mastered = verdict == "mastered"
    return AnswerResult(
        verdict=verdict,
        feedback=data.get("feedback", ""),
        explanation=data.get("explanation", ""),
        next=mastered,
        gap="" if mastered else (data.get("gap") or ""),
        retest_required=not mastered,
    )


async def generate_retest_question(lesson: dict, asked: list[str]) -> str:
    """生成与已问过题目不同的平行再测题。"""
    llm = get_llm()
    asked_block = "\n".join(f"- {q}" for q in asked if q) or "（尚无）"
    try:
        data = await llm.chat_json(
            [
                {"role": "system", "content": RETEST_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"知识点：{lesson.get('title', '')}\n"
                        f"摘要：{lesson.get('summary', '')}\n"
                        f"【原文摘录】\n{_excerpt_text(lesson)[:1200]}\n\n"
                        f"已经问过的题：\n{asked_block}\n\n"
                        '请返回 JSON：{"question":"..."}'
                    ),
                },
            ]
        )
        q = (data.get("question") or "").strip()
        if q and q not in asked:
            return q
    except LLMError:
        pass
    return f"请用自己的话说明「{lesson.get('title', '')}」是什么、为什么重要、以及什么时候用。不要重复你刚才的答案。"


def _source_fallback(lesson: dict) -> str:
    """source_ref 为空时：摘要 → 原文摘录首句 → 标题。"""
    summary = (lesson.get("summary") or "").strip()
    if summary:
        return summary[:200]
    excerpts = _excerpt_text(lesson).strip()
    if excerpts:
        for sep in ("。", "！", "？", "\n"):
            if sep in excerpts:
                first = excerpts.split(sep, 1)[0].strip()
                if first:
                    return first[:200]
        return excerpts[:200]
    return (lesson.get("title") or "").strip()[:200]


async def generate_cards(lesson: dict) -> list[dict]:
    """过关后制卡。source_ref 缺失时用摘要/摘录首句兜底，不因锚点对不上就丢弃。"""
    llm = get_llm()
    excerpts = _excerpt_text(lesson)
    fallback = _source_fallback(lesson)
    try:
        data = await llm.chat_json(
            [
                {"role": "system", "content": CARD_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"知识点：{lesson.get('title', '')}\n"
                        f"摘要：{lesson.get('summary', '')}\n"
                        f"过关题目：{lesson.get('question', '')}\n"
                        f"【原文摘录】\n{excerpts[:2500]}\n"
                    ),
                },
            ]
        )
    except LLMError:
        return []

    out = []
    for card in (data.get("cards") or [])[:8]:
        front = (card.get("front") or "").strip()
        back = (card.get("back") or "").strip()
        if not (front and back):
            continue
        source_ref = (card.get("source_ref") or "").strip() or fallback
        if not source_ref:
            source_ref = front[:200]
        out.append(
            {
                "card_type": card.get("card_type") or "concept",
                "front": front,
                "back": back,
                "source_ref": source_ref,
            }
        )
    return out


async def generate_chapter_quiz(chapter_lessons: list[dict], older: list[dict]) -> list[dict]:
    """本章 3–5 道提取题，尽量穿插旧点。"""
    llm = get_llm()
    def _brief(items: list[dict]) -> str:
        lines = []
        for l in items[:8]:
            lines.append(
                f"- lesson_id={l.get('id')} 标题={l.get('title','')} 摘要={l.get('summary','')[:80]}"
            )
        return "\n".join(lines) or "（无）"

    try:
        data = await llm.chat_json(
            [
                {"role": "system", "content": CHAPTER_QUIZ_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"本章知识点：\n{_brief(chapter_lessons)}\n\n"
                        f"可穿插的旧点：\n{_brief(older)}\n"
                    ),
                },
            ]
        )
    except LLMError:
        data = {}

    allowed = {l.get("id") for l in chapter_lessons + older}
    out = []
    for q in (data.get("questions") or [])[:5]:
        lid = (q.get("lesson_id") or "").strip()
        text = (q.get("question") or "").strip()
        if lid in allowed and text:
            out.append({"lesson_id": lid, "question": text})
    if len(out) >= 3:
        return out

    # 降级：每点一题，最多 5
    fallback = []
    pool = list(chapter_lessons) + list(older[:1])
    for l in pool[:5]:
        title = l.get("title") or "这个知识点"
        fallback.append(
            {
                "lesson_id": l.get("id"),
                "question": f"请用自己的话说明「{title}」是什么、为什么重要、什么时候用。",
            }
        )
    return fallback


async def generate_pretest_question(lesson: dict) -> str:
    llm = get_llm()
    try:
        data = await llm.chat_json(
            [
                {"role": "system", "content": PRETEST_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"知识点：{lesson.get('title','')}\n"
                        f"摘要：{lesson.get('summary','')}\n"
                        f"【原文摘录】\n{_excerpt_text(lesson)[:1200]}"
                    ),
                },
            ]
        )
        q = (data.get("question") or "").strip()
        if q:
            return q
    except LLMError:
        pass
    return f"请先不要看讲解，用自己的话说明你对「{lesson.get('title','')}」已经知道什么。"


def cards_to_out(rows: list[dict]) -> list[MemoryCardOut]:
    return [
        MemoryCardOut(
            id=r.get("id") or "",
            card_type=r.get("card_type") or "concept",
            front=r.get("front") or "",
            back=r.get("back") or "",
            source_ref=r.get("source_ref") or "",
        )
        for r in rows
    ]
