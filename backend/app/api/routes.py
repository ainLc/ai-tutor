"""REST API 路由。

认证、课程、讲课/补讲 SSE、掌握门、记忆卡片、今日复习、个人报告、分享。
"""
from __future__ import annotations

import json
import secrets

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ..core import auth
from ..core.llm import get_llm, set_runtime_llm
from ..core.providers import LLM_PROVIDERS
from ..core.scheduler import review_card as fsrs_review
from ..models import db
from ..models.schemas import (
    AnswerRequest,
    AuthResponse,
    CardReviewRequest,
    ChapterQuizAnswerRequest,
    CircuitOverrideRequest,
    CourseSettingsRequest,
    DefenseAnswerRequest,
    DeleteAccountRequest,
    LlmSettingsRequest,
    LoginRequest,
    PlanSwitchRequest,
    PretestAnswerRequest,
    RegisterRequest,
    ReportRequest,
    ReteachRequest,
    ShareImportRequest,
)
from ..services import course_service, defense_service, tutor_service

router = APIRouter(prefix="/api")


def get_current_user_id(authorization: str = Header(default="")) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "未登录")
    token = authorization[7:].strip()
    payload = auth.decode_token(token)
    if not payload:
        raise HTTPException(401, "登录已过期，请重新登录")
    user_id = payload["sub"]
    _bind_user_llm(user_id)
    return user_id


def _mask_key(key: str) -> str:
    raw = (key or "").strip()
    if not raw:
        return ""
    if len(raw) <= 8:
        return "•" * len(raw)
    return f"{raw[:3]}••••{raw[-4:]}"


def _env_key() -> str:
    from ..core.config import settings as app_settings

    key = (app_settings.llm_api_key or "").strip()
    if key and not key.startswith("sk-your"):
        return key
    return ""


def _bind_user_llm(user_id: str) -> None:
    from ..core.config import settings as app_settings

    row = db.get_llm_settings(user_id)
    key = ((row or {}).get("api_key") or "").strip() or _env_key()
    if row and key:
        set_runtime_llm(
            {
                "base_url": (row.get("base_url") or "").strip() or app_settings.llm_base_url,
                "api_key": key,
                "model": (row.get("model") or "").strip() or app_settings.llm_model,
                "temperature": row.get("temperature"),
            }
        )
    else:
        set_runtime_llm(None)


def _llm_public(user_id: str) -> dict:
    from ..core.config import settings as app_settings

    row = db.get_llm_settings(user_id)
    env_ready = bool(_env_key())
    if row:
        source = "user"
        provider = row.get("provider") or "custom"
        base_url = row.get("base_url") or app_settings.llm_base_url
        model = row.get("model") or app_settings.llm_model
        temperature = float(row.get("temperature") or 0.7)
        has_key = bool((row.get("api_key") or "").strip() or env_ready)
        masked = _mask_key(row.get("api_key") or "") or (_mask_key(_env_key()) if env_ready else "")
        configured = has_key
    else:
        source = "env" if env_ready else "none"
        configured = env_ready
        provider = "deepseek"
        base_url = app_settings.llm_base_url
        model = app_settings.llm_model
        temperature = app_settings.llm_temperature
        masked = _mask_key(_env_key()) if env_ready else ""
        has_key = env_ready
    return {
        "configured": configured,
        "source": source,
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "temperature": temperature,
        "api_key_masked": masked,
        "has_key": has_key,
        "presets": LLM_PROVIDERS,
    }


def _require_lesson_owner(lesson_id: str, user_id: str) -> dict:
    owner = db.lesson_owner(lesson_id)
    if owner is None:
        raise HTTPException(404, "知识点不存在")
    if owner != user_id:
        raise HTTPException(403, "无权访问该知识点")
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        raise HTTPException(404, "知识点不存在")
    return lesson


def _require_card_owner(card_id: str, user_id: str) -> dict:
    card = db.get_card(card_id)
    if not card or card.get("deleted"):
        raise HTTPException(404, "卡片不存在")
    if card.get("user_id") != user_id:
        raise HTTPException(403, "无权操作该卡片")
    return card


@router.get("/health")
async def health():
    return {"status": "ok"}


# ---------- 认证 ----------

@router.post("/auth/register", response_model=AuthResponse)
async def register(req: RegisterRequest):
    existing = db.get_user_by_username(req.username)
    if existing:
        raise HTTPException(400, "用户名已存在")

    user_id = db.create_user(req.username, auth.hash_password(req.password), req.nickname)
    if user_id is None:
        raise HTTPException(400, "用户名已存在")
    db.grant_owner_plan(user_id, req.username)

    token = auth.create_token(user_id, req.username)
    return AuthResponse(token=token, user_id=user_id, username=req.username, nickname=req.nickname)


@router.post("/auth/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    user = db.get_user_by_username(req.username)
    if not user or not auth.verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "用户名或密码错误")
    db.grant_owner_plan(user["id"], user["username"])

    token = auth.create_token(user["id"], user["username"])
    return AuthResponse(
        token=token, user_id=user["id"], username=user["username"], nickname=user.get("nickname", "")
    )


@router.get("/auth/me")
async def me(user_id: str = Depends(get_current_user_id)):
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    return {
        "id": user["id"],
        "username": user["username"],
        "nickname": user.get("nickname", ""),
        "plan": (user.get("plan") or "free"),
        "billing": db.billing_snapshot(user_id),
    }


@router.delete("/auth/me")
async def delete_account(req: DeleteAccountRequest, user_id: str = Depends(get_current_user_id)):
    if (req.confirm or "").strip() != "删除我的账号":
        raise HTTPException(400, "请输入「删除我的账号」以确认")
    db.delete_user(user_id)
    return {"ok": True}


# ---------- 模型设置 ----------

@router.get("/settings/llm")
async def get_llm_settings_api(user_id: str = Depends(get_current_user_id)):
    return _llm_public(user_id)


@router.put("/settings/llm")
async def put_llm_settings_api(
    req: LlmSettingsRequest,
    user_id: str = Depends(get_current_user_id),
):
    if not req.model.strip():
        raise HTTPException(400, "请填写模型名")
    if not req.base_url.strip():
        raise HTTPException(400, "请填写接口地址")
    try:
        temp = float(req.temperature)
    except (TypeError, ValueError):
        raise HTTPException(400, "温度必须是数字")
    if temp < 0 or temp > 2:
        raise HTTPException(400, "温度应在 0–2 之间")
    db.upsert_llm_settings(
        user_id,
        provider=(req.provider or "custom").strip(),
        base_url=req.base_url,
        model=req.model,
        temperature=temp,
        api_key=req.api_key,
    )
    _bind_user_llm(user_id)
    if not get_llm().configured:
        raise HTTPException(400, "还没有 API Key。请填写密钥后再保存。")
    return _llm_public(user_id)


@router.delete("/settings/llm")
async def delete_llm_settings_api(user_id: str = Depends(get_current_user_id)):
    db.clear_llm_settings(user_id)
    set_runtime_llm(None)
    return _llm_public(user_id)


@router.post("/settings/llm/test")
async def test_llm_settings_api(user_id: str = Depends(get_current_user_id)):
    llm = get_llm()
    if not llm.configured:
        raise HTTPException(400, "尚未配置可用的 API Key")
    try:
        text = await llm.chat(
            [{"role": "user", "content": "只回复两个字母：ok"}],
            temperature=0,
            max_tokens=16,
        )
    except Exception as e:
        raise HTTPException(400, f"调用失败：{e}") from e
    return {"ok": True, "model": llm.model, "reply": (text or "").strip()[:80]}


# ---------- 今日 / 报告 ----------

@router.get("/home/today")
async def home_today(user_id: str = Depends(get_current_user_id)):
    return db.today_summary(user_id)


@router.post("/home/circuit-override")
async def circuit_override(
    req: CircuitOverrideRequest,
    user_id: str = Depends(get_current_user_id),
):
    if not req.acknowledge:
        raise HTTPException(400, "请勾选「我知道这会降低 14 日保持率」")
    today = db.today_summary(user_id)
    if not today.get("overloaded"):
        return today
    return db.set_circuit_override(user_id)


@router.get("/billing/me")
async def billing_me(user_id: str = Depends(get_current_user_id)):
    return db.billing_snapshot(user_id)


@router.post("/billing/plan")
async def billing_plan(req: PlanSwitchRequest, user_id: str = Depends(get_current_user_id)):
    return db.set_user_plan(user_id, req.plan)


@router.get("/review/today")
async def review_today(user_id: str = Depends(get_current_user_id)):
    from ..core.scheduler import end_of_local_day_iso

    cards = db.due_cards(user_id, end_of_local_day_iso(), limit=200)
    return {
        "cards": [
            {
                "id": c["id"],
                "front": c["front"],
                "back": c["back"],
                "source_ref": c.get("source_ref") or "",
                "card_type": c.get("card_type") or "concept",
                "lesson_id": c["lesson_id"],
                "lesson_title": c.get("lesson_title") or "",
                "course_id": c.get("course_id") or "",
                "course_title": c.get("course_title") or "",
                "due_at": c.get("due_at") or "",
            }
            for c in cards
        ]
    }


@router.get("/review/stats")
async def review_stats(user_id: str = Depends(get_current_user_id)):
    return db.review_stats(user_id)


@router.get("/dashboard")
async def dashboard(user_id: str = Depends(get_current_user_id)):
    return db.get_dashboard()


# ---------- 课程 ----------

@router.post("/courses/upload")
async def upload_course(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    ok, msg = db.can_create_course(user_id)
    if not ok:
        raise HTTPException(403, msg)
    try:
        extracted = await _read_file(file)
    except ValueError as e:
        raise HTTPException(400, str(e))
    content = extracted.text
    if not content:
        raise HTTPException(400, "无法读取文件内容（支持 md / txt / zip / 文本 PDF）")

    try:
        outline = await course_service.parse_outline(content)
    except ValueError as e:
        raise HTTPException(400, str(e))

    source_name = file.filename or "upload"
    if getattr(extracted, "engine", "") == "ocr":
        source_name = f"{source_name}（OCR）"
        if extracted.warning:
            source_name = f"{source_name} {extracted.warning}"
    if "仅基于部分资料" in outline.title and "部分" not in source_name:
        source_name = f"{source_name}（仅基于前 {course_service.MAX_INPUT_CHARS} 字）"

    course_id = db.create_course(
        title=outline.title,
        source_file=source_name,
        outline=outline.model_dump(),
        user_id=user_id,
        source_hash=db.fingerprint_text(content),
    )
    return db.get_course(course_id)


@router.get("/courses")
async def list_courses(user_id: str = Depends(get_current_user_id)):
    return db.list_courses(user_id)


@router.get("/courses/{course_id}")
async def get_course(course_id: str, user_id: str = Depends(get_current_user_id)):
    course = db.get_course(course_id)
    if not course:
        raise HTTPException(404, "课程不存在")
    if course.get("user_id") and course["user_id"] != user_id:
        raise HTTPException(403, "无权访问该课程")
    return course


@router.patch("/courses/{course_id}/settings")
async def update_course_settings(
    course_id: str,
    req: CourseSettingsRequest,
    user_id: str = Depends(get_current_user_id),
):
    owner = db.course_owner(course_id)
    if owner is None:
        raise HTTPException(404, "课程不存在")
    if owner != user_id:
        raise HTTPException(403, "无权修改该课程")
    try:
        db.update_course_settings(course_id, req.exam_date, req.desired_retention)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return db.get_course(course_id)


def _require_chapter_owner(chapter_id: str, user_id: str) -> dict:
    owner = db.chapter_owner(chapter_id)
    if owner is None:
        raise HTTPException(404, "章节不存在")
    if owner != user_id:
        raise HTTPException(403, "无权访问该章节")
    chapter = db.get_chapter(chapter_id)
    if not chapter:
        raise HTTPException(404, "章节不存在")
    return chapter


@router.get("/chapters/{chapter_id}/quiz")
async def get_chapter_quiz(chapter_id: str, user_id: str = Depends(get_current_user_id)):
    _require_chapter_owner(chapter_id, user_id)
    ready = db.chapter_understood(chapter_id)
    quiz = db.get_latest_quiz(chapter_id, user_id)
    return {"ready": ready, "quiz": quiz}


@router.post("/chapters/{chapter_id}/quiz")
async def create_chapter_quiz(chapter_id: str, user_id: str = Depends(get_current_user_id)):
    chapter = _require_chapter_owner(chapter_id, user_id)
    if not db.chapter_understood(chapter_id):
        raise HTTPException(400, "本章知识点尚未全部理解过关")
    existing = db.get_latest_quiz(chapter_id, user_id)
    if existing and existing.get("status") in ("pending", "in_progress"):
        return existing
    older = db.chapter_older_lessons(chapter_id, user_id)
    questions = await tutor_service.generate_chapter_quiz(chapter["lessons"], older)
    if len(questions) < 3:
        raise HTTPException(400, "本章知识点太少，暂不能收口测验")
    return db.save_chapter_quiz(chapter_id, user_id, questions)


@router.post("/chapters/{chapter_id}/quiz/answer")
async def answer_chapter_quiz(
    chapter_id: str,
    req: ChapterQuizAnswerRequest,
    user_id: str = Depends(get_current_user_id),
):
    _require_chapter_owner(chapter_id, user_id)
    quiz = db.get_latest_quiz(chapter_id, user_id)
    if not quiz:
        raise HTTPException(404, "还没有本章测验")
    questions = quiz.get("questions") or []
    if req.index < 0 or req.index >= len(questions):
        raise HTTPException(400, "题目序号无效")
    item = questions[req.index]
    lesson = db.get_lesson(item["lesson_id"])
    if not lesson:
        raise HTTPException(404, "题目对应的知识点不存在")
    result = await tutor_service.judge_answer(lesson, req.answer)
    results = quiz.get("results") or []
    # 同一题覆盖
    results = [r for r in results if r.get("index") != req.index]
    results.append(
        {
            "index": req.index,
            "lesson_id": item["lesson_id"],
            "verdict": result.verdict,
            "feedback": result.feedback,
            "gap": result.gap,
        }
    )
    if result.verdict != "mastered":
        db.update_understanding(item["lesson_id"], "needs_reteach", last_verdict=result.verdict)

    answered = {r["index"] for r in results}
    all_done = all(i in answered for i in range(len(questions)))
    failed = any(r.get("verdict") != "mastered" for r in results)
    if all_done:
        status = "failed" if failed else "passed"
    else:
        status = "in_progress"
    db.update_quiz_results(quiz["id"], results, status)
    return {
        "verdict": result.verdict,
        "feedback": result.feedback,
        "gap": result.gap,
        "status": status,
        "results": results,
        "rollback": result.verdict != "mastered",
    }


@router.delete("/courses/{course_id}")
async def delete_course(course_id: str, user_id: str = Depends(get_current_user_id)):
    owner = db.course_owner(course_id)
    if owner is None:
        raise HTTPException(404, "课程不存在")
    if owner != user_id:
        raise HTTPException(403, "无权删除该课程")
    db.delete_course(course_id)
    return {"ok": True}


# ---------- 知识点 ----------

@router.get("/lessons/{lesson_id}")
async def get_lesson(lesson_id: str, user_id: str = Depends(get_current_user_id)):
    return _require_lesson_owner(lesson_id, user_id)


@router.get("/lessons/{lesson_id}/stream")
async def stream_lesson(lesson_id: str, user_id: str = Depends(get_current_user_id)):
    lesson = _require_lesson_owner(lesson_id, user_id)
    _deny_new_if_locked(user_id, lesson)

    if lesson.get("content"):
        cached = db.get_lesson_content(lesson_id)

        async def replay():
            yield _sse({"type": "text", "content": cached["content"]})
            if cached.get("diagram"):
                yield _sse({"type": "diagram", "content": cached["diagram"]})
            if cached.get("question"):
                yield _sse({"type": "question", "content": cached["question"]})
            yield _sse({"type": "done", "content": ""})

        return StreamingResponse(replay(), media_type="text/event-stream")

    db.update_understanding(lesson_id, "learning")

    async def generate():
        content_parts: list[str] = []
        diagram = ""
        question = ""
        async for frame in tutor_service.stream_lecture(lesson):
            if frame["type"] == "text":
                content_parts.append(frame["content"])
            elif frame["type"] == "diagram":
                diagram = frame["content"]
            elif frame["type"] == "question":
                question = frame["content"]
            yield _sse(frame)
        db.save_lesson_content(lesson_id, "".join(content_parts), diagram, question)
        if question:
            db.add_asked_question(lesson_id, question)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/lessons/{lesson_id}/answer")
async def answer_lesson(
    lesson_id: str,
    req: AnswerRequest,
    user_id: str = Depends(get_current_user_id),
):
    lesson = _require_lesson_owner(lesson_id, user_id)
    result = await tutor_service.judge_answer(lesson, req.answer)
    attempts = lesson.get("attempts", 0) + 1
    current_q = lesson.get("question") or ""
    if current_q:
        db.add_asked_question(lesson_id, current_q)

    if result.verdict == "mastered":
        db.update_understanding(
            lesson_id, "understood", last_verdict="mastered", attempts=attempts
        )
        raw_cards = await tutor_service.generate_cards({**lesson, "question": current_q})
        db.create_cards(user_id, lesson_id, raw_cards)
        stored = db.list_cards(lesson_id, user_id)
        result.cards = tutor_service.cards_to_out(stored)
        result.next = True
        result.retest_required = False
    else:
        retest_count = int(lesson.get("retest_count") or 0)
        db.update_understanding(
            lesson_id,
            "needs_reteach",
            last_verdict=result.verdict,
            retest_count=retest_count,
            attempts=attempts,
        )
        result.next = False
        result.retest_required = True

    return result.model_dump()


@router.post("/lessons/{lesson_id}/reteach/stream")
async def stream_reteach(
    lesson_id: str,
    req: ReteachRequest,
    user_id: str = Depends(get_current_user_id),
):
    lesson = _require_lesson_owner(lesson_id, user_id)

    async def generate():
        parts: list[str] = []
        async for frame in tutor_service.stream_reteach(lesson, req.answer, req.gap):
            if frame["type"] == "text":
                parts.append(frame["content"])
            yield _sse(frame)
        db.save_reteach_content(lesson_id, "".join(parts))

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/lessons/{lesson_id}/retest")
async def retest_lesson(lesson_id: str, user_id: str = Depends(get_current_user_id)):
    lesson = _require_lesson_owner(lesson_id, user_id)
    asked = db.list_asked_questions(lesson_id)
    question = await tutor_service.generate_retest_question(lesson, asked)
    db.save_lesson_question(lesson_id, question)
    db.add_asked_question(lesson_id, question)
    retest_count = int(lesson.get("retest_count") or 0) + 1
    db.update_understanding(
        lesson_id,
        "needs_reteach",
        last_verdict=lesson.get("last_verdict") or "",
        retest_count=retest_count,
    )
    return {"question": question}


@router.post("/lessons/{lesson_id}/report")
async def report_lesson(
    lesson_id: str,
    req: ReportRequest,
    user_id: str = Depends(get_current_user_id),
):
    _require_lesson_owner(lesson_id, user_id)
    db.add_report(lesson_id, user_id, req.reason, req.note)
    return {"ok": True, "message": "已记录。我们会用这类标记压讲解幻觉。"}


@router.post("/lessons/{lesson_id}/pretest")
async def pretest_lesson(lesson_id: str, user_id: str = Depends(get_current_user_id)):
    lesson = _require_lesson_owner(lesson_id, user_id)
    if lesson.get("understanding") == "understood":
        raise HTTPException(400, "已经理解过关，不必前测")
    _deny_new_if_locked(user_id, lesson)
    question = await tutor_service.generate_pretest_question(lesson)
    db.save_lesson_question(lesson_id, question)
    db.add_asked_question(lesson_id, question)
    db.update_understanding(lesson_id, "learning")
    return {"question": question}


@router.post("/lessons/{lesson_id}/pretest/answer")
async def pretest_answer(
    lesson_id: str,
    req: PretestAnswerRequest,
    user_id: str = Depends(get_current_user_id),
):
    lesson = _require_lesson_owner(lesson_id, user_id)
    result = await tutor_service.judge_answer(lesson, req.answer)
    if result.verdict == "mastered":
        db.update_understanding(lesson_id, "understood", last_verdict="pretest")
        raw_cards = await tutor_service.generate_cards({**lesson, "question": lesson.get("question") or ""})
        db.create_cards(user_id, lesson_id, raw_cards)
        stored = db.list_cards(lesson_id, user_id)
        result.cards = tutor_service.cards_to_out(stored)
        result.next = True
        result.retest_required = False
    else:
        db.update_understanding(lesson_id, "not_started", last_verdict=result.verdict)
        result.next = False
        result.retest_required = False
        result.feedback = (result.feedback or "") + " 前测未过关，请听初讲。"
    return result.model_dump()


@router.post("/lessons/{lesson_id}/cards")
async def create_lesson_cards(lesson_id: str, user_id: str = Depends(get_current_user_id)):
    lesson = _require_lesson_owner(lesson_id, user_id)
    if lesson.get("understanding") != "understood":
        raise HTTPException(400, "尚未理解过关，不能制卡")
    raw = await tutor_service.generate_cards(lesson)
    db.create_cards(user_id, lesson_id, raw)
    return tutor_service.cards_to_out(db.list_cards(lesson_id, user_id))


@router.get("/lessons/{lesson_id}/cards")
async def list_lesson_cards(lesson_id: str, user_id: str = Depends(get_current_user_id)):
    _require_lesson_owner(lesson_id, user_id)
    return tutor_service.cards_to_out(db.list_cards(lesson_id, user_id))


@router.delete("/cards/{card_id}")
async def delete_card(card_id: str, user_id: str = Depends(get_current_user_id)):
    _require_card_owner(card_id, user_id)
    db.soft_delete_card(card_id)
    return {"ok": True}


@router.post("/cards/{card_id}/review")
async def review_one_card(
    card_id: str,
    req: CardReviewRequest,
    user_id: str = Depends(get_current_user_id),
):
    card = _require_card_owner(card_id, user_id)
    rating = (req.rating or "").strip().lower()
    try:
        result = fsrs_review(
            card.get("fsrs_state") or "",
            rating,
            desired_retention=db.card_desired_retention(card_id),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    lapses = int(card.get("lapses") or 0)
    if rating == "again":
        lapses += 1
        # 连续遗忘：把知识点打回「理解回退」欠账
        if lapses >= 2:
            db.update_understanding(card["lesson_id"], "needs_reteach", last_verdict="lapse")

    db.update_card_fsrs(card_id, result["fsrs_state"], result["due_at"], lapses)
    db.add_review_log(
        card_id,
        user_id,
        rating,
        result["elapsed_days"],
        result["scheduled_days"],
    )
    return {
        "due_at": result["due_at"],
        "scheduled_days": result["scheduled_days"],
        "elapsed_days": result["elapsed_days"],
        "lapses": lapses,
        "lesson_id": card["lesson_id"],
        "reteach_available": rating == "again",
    }


# ---------- 合上书答辩 ----------

def _deny_new_if_locked(user_id: str, lesson: dict) -> None:
    if (lesson.get("understanding") or "not_started") != "not_started":
        return
    today = db.today_summary(user_id)
    if today.get("locked_new"):
        raise HTTPException(
            423,
            f"你有 {today.get('due_count') or 0} 张今天不练就会掉，再学新的等于给自己挖坑。请先记忆练习，或在今日页勾选知情后继续。",
        )


def _require_course_owner(course_id: str, user_id: str) -> dict:
    course = db.get_course(course_id)
    if not course:
        raise HTTPException(404, "课程不存在")
    if course.get("user_id") and course["user_id"] != user_id:
        raise HTTPException(403, "无权访问该课程")
    return course


def _defense_client(session: dict) -> dict:
    """题面不回传原文锚点，防止开卷。"""
    questions = []
    for q in session.get("questions") or []:
        questions.append(
            {
                "lesson_id": q.get("lesson_id") or "",
                "question": q.get("question") or "",
                "lesson_title": q.get("lesson_title") or "",
            }
        )
    return {
        "id": session.get("id"),
        "course_id": session.get("course_id"),
        "status": session.get("status"),
        "questions": questions,
        "answers": session.get("answers") or [],
        "created_at": session.get("created_at") or "",
        "finished_at": session.get("finished_at") or "",
    }


@router.get("/courses/{course_id}/defense")
async def get_course_defense(course_id: str, user_id: str = Depends(get_current_user_id)):
    _require_course_owner(course_id, user_id)
    session = db.latest_defense(course_id, user_id)
    understood = db.list_understood_lessons(course_id)
    return {
        "ready": len(understood) >= 3,
        "understood": len(understood),
        "defense": _defense_client(session) if session else None,
    }


@router.post("/courses/{course_id}/defense")
async def create_course_defense(course_id: str, user_id: str = Depends(get_current_user_id)):
    _require_course_owner(course_id, user_id)
    existing = db.latest_defense(course_id, user_id)
    if existing and existing.get("status") in ("pending", "in_progress"):
        return _defense_client(existing)
    lessons = db.list_understood_lessons(course_id)
    if len(lessons) < 3:
        raise HTTPException(400, "至少 3 个知识点已理解后，才能开合上书答辩。")
    questions = await defense_service.generate_defense_questions(lessons)
    titles = {l.get("id"): l.get("title") or "" for l in lessons}
    for q in questions:
        q["lesson_title"] = titles.get(q.get("lesson_id"), "")
    if len(questions) < 4:
        raise HTTPException(400, "这门课可答辩的知识点还不够，请先再过关几块。")
    return _defense_client(db.create_defense(course_id, user_id, questions))


@router.post("/defense/{defense_id}/answer")
async def answer_defense(
    defense_id: str,
    req: DefenseAnswerRequest,
    user_id: str = Depends(get_current_user_id),
):
    session = db.get_defense(defense_id)
    if not session or session.get("user_id") != user_id:
        raise HTTPException(404, "答辩不存在")
    if session.get("status") in ("passed", "failed"):
        raise HTTPException(400, "本场答辩已经结束")
    questions = session.get("questions") or []
    if req.index < 0 or req.index >= len(questions):
        raise HTTPException(400, "题目序号无效")
    item = questions[req.index]
    lesson = db.get_lesson(item.get("lesson_id") or "")
    if not lesson:
        raise HTTPException(404, "题目对应的知识点不存在")
    result = await tutor_service.judge_answer(lesson, req.answer)
    answers = [a for a in (session.get("answers") or []) if a.get("index") != req.index]
    answers.append(
        {
            "index": req.index,
            "answer": (req.answer or "")[:2000],
            "verdict": result.verdict,
            "feedback": result.feedback,
        }
    )
    answered = {a["index"] for a in answers}
    all_done = all(i in answered for i in range(len(questions)))
    if all_done:
        mastered = sum(1 for a in answers if a.get("verdict") == "mastered")
        status = "passed" if mastered >= max(1, round(len(questions) * 0.8)) else "failed"
    else:
        status = "in_progress"
    db.update_defense_answers(defense_id, answers, status)
    session = db.get_defense(defense_id) or session
    return {
        "verdict": result.verdict,
        "feedback": result.feedback,
        "status": status,
        "defense": _defense_client(session),
    }


@router.get("/defense/{defense_id}/certificate")
async def defense_certificate(defense_id: str, user_id: str = Depends(get_current_user_id)):
    session = db.get_defense(defense_id)
    if not session or session.get("user_id") != user_id:
        raise HTTPException(404, "答辩不存在")
    if session.get("status") not in ("passed", "failed"):
        raise HTTPException(400, "答辩尚未结束，不能出具凭证")
    return db.certificate_payload(session, user_id)


# ---------- 分享 ----------

@router.post("/share/import")
async def import_course(req: ShareImportRequest, user_id: str = Depends(get_current_user_id)):
    ok, msg = db.can_create_course(user_id)
    if not ok:
        raise HTTPException(403, msg)
    link = db.get_share_link(req.token)
    if not link:
        raise HTTPException(404, "分享码无效或已失效")

    try:
        new_id = db.import_course(link["course_id"], user_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {"course_id": new_id}


@router.post("/share/{course_id}")
async def share_course(course_id: str, user_id: str = Depends(get_current_user_id)):
    owner = db.course_owner(course_id)
    if owner is None:
        raise HTTPException(404, "课程不存在")
    if owner != user_id:
        raise HTTPException(403, "无权分享该课程")

    token = secrets.token_urlsafe(8)
    db.create_share_link(course_id, token)
    return {"token": token}


# ---------- 工具 ----------

def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _read_file(file: UploadFile):
    from ..core.ocr import ExtractedDoc, extract_pdf

    name = (file.filename or "").lower()
    raw = await file.read()

    if name.endswith((".md", ".txt")):
        return ExtractedDoc(text=raw.decode("utf-8", errors="ignore"), engine="text")

    if name.endswith(".zip"):
        text, _truncated = course_service.extract_zip_text(raw)
        return ExtractedDoc(text=text, engine="zip")

    if name.endswith(".pdf"):
        try:
            return extract_pdf(raw)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    return ExtractedDoc(text=raw.decode("utf-8", errors="ignore"), engine="text")
