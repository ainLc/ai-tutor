"""SQLite 持久化层。

表：users / courses / chapters / lessons / progress / share_links / cards / review_logs。
进度拆成理解轴（progress.understanding）与记忆轴（cards + FSRS）。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..core.config import settings
from ..core.plans import CIRCUIT_DUE_LIMIT, PLANS, is_owner, normalize_plan, plan_of, public_plans, quota_message
from ..core.scheduler import end_of_local_day, end_of_local_day_iso

DB_PATH = settings.data_dir / "ai-tutor.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _id() -> str:
    return uuid.uuid4().hex[:12]


def _json_list(raw) -> list:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """建表（幂等） + 兼容旧数据迁移。"""
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                nickname TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );
            CREATE TABLE IF NOT EXISTS courses (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                title TEXT NOT NULL,
                source_file TEXT DEFAULT '',
                shared_from TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS chapters (
                id TEXT PRIMARY KEY,
                course_id TEXT NOT NULL,
                title TEXT NOT NULL,
                ord INTEGER DEFAULT 0,
                FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS lessons (
                id TEXT PRIMARY KEY,
                chapter_id TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT DEFAULT '',
                content TEXT DEFAULT '',
                diagram TEXT DEFAULT '',
                question TEXT DEFAULT '',
                ord INTEGER DEFAULT 0,
                FOREIGN KEY(chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS progress (
                lesson_id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'not_started',
                attempts INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS share_links (
                id TEXT PRIMARY KEY,
                course_id TEXT NOT NULL,
                token TEXT UNIQUE NOT NULL,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS cards (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                lesson_id TEXT NOT NULL,
                card_type TEXT NOT NULL DEFAULT 'concept',
                front TEXT NOT NULL,
                back TEXT NOT NULL,
                source_ref TEXT DEFAULT '',
                fsrs_state TEXT DEFAULT '',
                due_at TEXT DEFAULT '',
                lapses INTEGER DEFAULT 0,
                deleted INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_cards_due ON cards(user_id, deleted, due_at);
            CREATE TABLE IF NOT EXISTS review_logs (
                id TEXT PRIMARY KEY,
                card_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                rating TEXT NOT NULL,
                elapsed_days REAL DEFAULT 0,
                scheduled_days REAL DEFAULT 0,
                reviewed_at TEXT DEFAULT '',
                FOREIGN KEY(card_id) REFERENCES cards(id) ON DELETE CASCADE
            );
            """
        )
        _migrate(c)


def _migrate(c: sqlite3.Connection) -> None:
    """兼容旧数据：补列 + 理解轴映射。"""
    cols = {row["name"] for row in c.execute("PRAGMA table_info(courses)").fetchall()}
    if "user_id" not in cols:
        c.execute("ALTER TABLE courses ADD COLUMN user_id TEXT")
    if "shared_from" not in cols:
        c.execute("ALTER TABLE courses ADD COLUMN shared_from TEXT DEFAULT ''")

    orphans = c.execute("SELECT id FROM courses WHERE user_id IS NULL OR user_id=''").fetchall()
    if orphans:
        c.execute(
            "INSERT OR IGNORE INTO users (id, username, password_hash, nickname) "
            "VALUES (?, ?, ?, ?)",
            ("_default", "默认用户", "!", "历史数据"),
        )
        c.execute("UPDATE courses SET user_id='_default' WHERE user_id IS NULL OR user_id=''")

    lesson_cols = {row["name"] for row in c.execute("PRAGMA table_info(lessons)").fetchall()}
    if "source_excerpts" not in lesson_cols:
        c.execute("ALTER TABLE lessons ADD COLUMN source_excerpts TEXT DEFAULT '[]'")
    if "reteach_content" not in lesson_cols:
        c.execute("ALTER TABLE lessons ADD COLUMN reteach_content TEXT DEFAULT ''")

    prog_cols = {row["name"] for row in c.execute("PRAGMA table_info(progress)").fetchall()}
    if "understanding" not in prog_cols:
        c.execute("ALTER TABLE progress ADD COLUMN understanding TEXT DEFAULT 'not_started'")
    if "last_verdict" not in prog_cols:
        c.execute("ALTER TABLE progress ADD COLUMN last_verdict TEXT DEFAULT ''")
    if "retest_count" not in prog_cols:
        c.execute("ALTER TABLE progress ADD COLUMN retest_count INTEGER DEFAULT 0")
    if "asked_questions" not in prog_cols:
        c.execute("ALTER TABLE progress ADD COLUMN asked_questions TEXT DEFAULT '[]'")

    course_cols = {row["name"] for row in c.execute("PRAGMA table_info(courses)").fetchall()}
    if "exam_date" not in course_cols:
        c.execute("ALTER TABLE courses ADD COLUMN exam_date TEXT DEFAULT ''")
    if "desired_retention" not in course_cols:
        c.execute("ALTER TABLE courses ADD COLUMN desired_retention REAL DEFAULT 0.9")
    if "source_hash" not in course_cols:
        c.execute("ALTER TABLE courses ADD COLUMN source_hash TEXT DEFAULT ''")

    user_cols = {row["name"] for row in c.execute("PRAGMA table_info(users)").fetchall()}
    if "plan" not in user_cols:
        c.execute("ALTER TABLE users ADD COLUMN plan TEXT DEFAULT 'free'")
    if "circuit_override_until" not in user_cols:
        c.execute("ALTER TABLE users ADD COLUMN circuit_override_until TEXT DEFAULT ''")

    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS chapter_quizzes (
            id TEXT PRIMARY KEY,
            chapter_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            questions TEXT DEFAULT '[]',
            results TEXT DEFAULT '[]',
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            lesson_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            reason TEXT DEFAULT 'not_in_source',
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS user_llm_settings (
            user_id TEXT PRIMARY KEY,
            provider TEXT DEFAULT 'deepseek',
            base_url TEXT DEFAULT '',
            api_key TEXT DEFAULT '',
            model TEXT DEFAULT '',
            temperature REAL DEFAULT 0.7,
            updated_at TEXT DEFAULT '',
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS defense_sessions (
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            questions TEXT DEFAULT '[]',
            answers TEXT DEFAULT '[]',
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT '',
            finished_at TEXT DEFAULT '',
            FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_defense_course ON defense_sessions(course_id, user_id, created_at);
        """
    )

    # 旧 status → 理解轴（只填尚未映射的行）
    c.execute(
        """
        UPDATE progress SET understanding = CASE status
            WHEN 'completed'    THEN 'understood'
            WHEN 'needs_review' THEN 'needs_reteach'
            WHEN 'in_progress'  THEN 'learning'
            ELSE COALESCE(NULLIF(understanding, ''), 'not_started')
        END
        WHERE understanding IS NULL OR understanding = '' OR understanding = 'not_started'
        """
    )
    # 上面会把真正的 not_started 也走 CASE；completed 等旧数据能被映射。
    # 再把仍是空的补上。
    c.execute("UPDATE progress SET understanding='not_started' WHERE understanding IS NULL OR understanding=''")
    c.execute("UPDATE users SET plan='lab' WHERE lower(username) IN ('ain')")


def _lesson_public(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["source_excerpts"] = _json_list(d.get("source_excerpts"))
    understanding = d.get("understanding") or "not_started"
    d["understanding"] = understanding
    # 旧前端字段：不再用 completed 表示「听过」
    status_map = {
        "understood": "understood",
        "needs_reteach": "needs_reteach",
        "learning": "learning",
        "not_started": "not_started",
    }
    d["status"] = status_map.get(understanding, understanding)
    return d


# ---------- 用户 ----------

def create_user(username: str, password_hash: str, nickname: str) -> Optional[str]:
    user_id = _id()
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO users (id, username, password_hash, nickname) VALUES (?, ?, ?, ?)",
                (user_id, username, password_hash, nickname),
            )
        return user_id
    except sqlite3.IntegrityError:
        return None


def get_user_by_username(username: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    return dict(row) if row else None


def get_user(user_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


# ---------- 课程写 ----------

def fingerprint_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


def create_course(
    title: str,
    source_file: str,
    outline: dict,
    user_id: str = "",
    source_hash: str = "",
) -> str:
    """根据拆课结果 outline 落库，返回 course_id。"""
    course_id = _id()
    with _conn() as c:
        c.execute(
            "INSERT INTO courses (id, user_id, title, source_file, source_hash) VALUES (?, ?, ?, ?, ?)",
            (course_id, user_id, title, source_file, source_hash or ""),
        )
        for ci, ch in enumerate(outline["chapters"]):
            chapter_id = _id()
            c.execute(
                "INSERT INTO chapters (id, course_id, title, ord) VALUES (?, ?, ?, ?)",
                (chapter_id, course_id, ch["title"], ci),
            )
            for li, les in enumerate(ch["lessons"]):
                lesson_id = _id()
                excerpts = []
                loc = les.get("loc") or ""
                for item in les.get("excerpts") or []:
                    if isinstance(item, dict):
                        excerpts.append(
                            {"excerpt": item.get("excerpt", ""), "loc": item.get("loc", loc)}
                        )
                    elif item:
                        excerpts.append({"excerpt": str(item), "loc": loc})
                c.execute(
                    "INSERT INTO lessons (id, chapter_id, title, summary, ord, source_excerpts) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        lesson_id,
                        chapter_id,
                        les["title"],
                        les.get("summary", ""),
                        li,
                        json.dumps(excerpts, ensure_ascii=False),
                    ),
                )
                c.execute(
                    "INSERT INTO progress (lesson_id, status, understanding) VALUES (?, 'not_started', 'not_started')",
                    (lesson_id,),
                )
    return course_id


def save_lesson_content(lesson_id: str, content: str, diagram: str, question: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE lessons SET content=?, diagram=?, question=? WHERE id=?",
            (content, diagram, question, lesson_id),
        )


def save_reteach_content(lesson_id: str, content: str) -> None:
    with _conn() as c:
        c.execute("UPDATE lessons SET reteach_content=? WHERE id=?", (content, lesson_id))


def save_lesson_question(lesson_id: str, question: str) -> None:
    with _conn() as c:
        c.execute("UPDATE lessons SET question=? WHERE id=?", (question, lesson_id))


def save_source_excerpts(lesson_id: str, excerpts: list) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE lessons SET source_excerpts=? WHERE id=?",
            (json.dumps(excerpts, ensure_ascii=False), lesson_id),
        )


def get_lesson_source(lesson_id: str) -> list:
    with _conn() as c:
        row = c.execute("SELECT source_excerpts FROM lessons WHERE id=?", (lesson_id,)).fetchone()
    return _json_list(row["source_excerpts"] if row else None)


def update_progress(lesson_id: str, status: str, attempts: Optional[int] = None) -> None:
    """兼容旧调用：同步写 status，理解轴请用 update_understanding。"""
    with _conn() as c:
        if attempts is None:
            c.execute(
                "UPDATE progress SET status=?, updated_at=datetime('now','localtime') "
                "WHERE lesson_id=?",
                (status, lesson_id),
            )
        else:
            c.execute(
                "UPDATE progress SET status=?, attempts=?, "
                "updated_at=datetime('now','localtime') WHERE lesson_id=?",
                (status, attempts, lesson_id),
            )


def update_understanding(
    lesson_id: str,
    understanding: str,
    last_verdict: Optional[str] = None,
    retest_count: Optional[int] = None,
    attempts: Optional[int] = None,
) -> None:
    # 旧 status 仅作镜像，不再作为判断依据
    status_mirror = {
        "understood": "completed",
        "needs_reteach": "needs_review",
        "learning": "in_progress",
        "not_started": "not_started",
    }.get(understanding, understanding)
    with _conn() as c:
        sets = [
            "understanding=?",
            "status=?",
            "updated_at=datetime('now','localtime')",
        ]
        args: list = [understanding, status_mirror]
        if last_verdict is not None:
            sets.append("last_verdict=?")
            args.append(last_verdict)
        if retest_count is not None:
            sets.append("retest_count=?")
            args.append(retest_count)
        if attempts is not None:
            sets.append("attempts=?")
            args.append(attempts)
        args.append(lesson_id)
        c.execute(f"UPDATE progress SET {', '.join(sets)} WHERE lesson_id=?", args)


def add_asked_question(lesson_id: str, q: str) -> None:
    if not q:
        return
    with _conn() as c:
        row = c.execute("SELECT asked_questions FROM progress WHERE lesson_id=?", (lesson_id,)).fetchone()
        asked = _json_list(row["asked_questions"] if row else None)
        if q not in asked:
            asked.append(q)
        c.execute(
            "UPDATE progress SET asked_questions=? WHERE lesson_id=?",
            (json.dumps(asked, ensure_ascii=False), lesson_id),
        )


def list_asked_questions(lesson_id: str) -> list:
    with _conn() as c:
        row = c.execute("SELECT asked_questions FROM progress WHERE lesson_id=?", (lesson_id,)).fetchone()
    return _json_list(row["asked_questions"] if row else None)


# ---------- 课程读 ----------

def list_courses(user_id: str = "") -> list[dict]:
    with _conn() as c:
        if user_id:
            rows = c.execute(
                """
                SELECT c.id, c.title, c.source_file, c.shared_from, c.created_at, c.user_id,
                       c.exam_date, c.desired_retention, c.source_hash,
                       (SELECT COUNT(*) FROM lessons l JOIN chapters ch ON l.chapter_id=ch.id
                         WHERE ch.course_id=c.id) AS total_lessons,
                       (SELECT COUNT(*) FROM lessons l JOIN chapters ch ON l.chapter_id=ch.id
                         JOIN progress p ON p.lesson_id=l.id
                         WHERE ch.course_id=c.id AND p.understanding='understood') AS understood_lessons,
                       (SELECT COUNT(*) FROM cards cd JOIN lessons l ON cd.lesson_id=l.id
                         JOIN chapters ch ON l.chapter_id=ch.id
                         WHERE ch.course_id=c.id AND cd.user_id=c.user_id AND cd.deleted=0) AS total_cards,
                       (SELECT COUNT(DISTINCT rl.card_id) FROM review_logs rl
                         JOIN cards cd ON rl.card_id=cd.id
                         JOIN lessons l ON cd.lesson_id=l.id
                         JOIN chapters ch ON l.chapter_id=ch.id
                         WHERE ch.course_id=c.id AND cd.user_id=c.user_id AND cd.deleted=0
                           AND rl.rating IN ('good','easy') AND rl.scheduled_days >= 3) AS settled_cards,
                       (SELECT MIN(cd.due_at) FROM cards cd JOIN lessons l ON cd.lesson_id=l.id
                         JOIN chapters ch ON l.chapter_id=ch.id
                         WHERE ch.course_id=c.id AND cd.user_id=c.user_id AND cd.deleted=0
                           AND cd.due_at IS NOT NULL AND cd.due_at != '') AS next_due_at
                FROM courses c WHERE c.user_id=? ORDER BY c.created_at DESC
                """,
                (user_id,),
            ).fetchall()
        else:
            rows = c.execute(
                """
                SELECT c.id, c.title, c.source_file, c.shared_from, c.created_at, c.user_id,
                       c.exam_date, c.desired_retention, c.source_hash,
                       (SELECT COUNT(*) FROM lessons l JOIN chapters ch ON l.chapter_id=ch.id
                         WHERE ch.course_id=c.id) AS total_lessons,
                       (SELECT COUNT(*) FROM lessons l JOIN chapters ch ON l.chapter_id=ch.id
                         JOIN progress p ON p.lesson_id=l.id
                         WHERE ch.course_id=c.id AND p.understanding='understood') AS understood_lessons
                FROM courses c ORDER BY c.created_at DESC
                """
            ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["completed_lessons"] = d.get("understood_lessons") or 0
        d["understood_lessons"] = d.get("understood_lessons") or 0
        d["total_cards"] = d.get("total_cards") or 0
        d["settled_cards"] = d.get("settled_cards") or 0
        d["completion_label"] = _completion_label(d)
        d["exam_date"] = d.get("exam_date") or ""
        d["desired_retention"] = d.get("desired_retention") or 0.9
        d["source_hash"] = d.get("source_hash") or ""
        d["fingerprint"] = (d["source_hash"] or "")[:12]
        result.append(d)
    return result


def _completion_label(d: dict) -> str:
    total = d.get("total_lessons") or 0
    understood = d.get("understood_lessons") or 0
    total_cards = d.get("total_cards") or 0
    settled = d.get("settled_cards") or 0
    if total and understood >= total and total_cards and settled >= total_cards:
        return "已记住"
    if understood:
        return "已学过，尚未记住"
    return "未开始"


def get_course(course_id: str) -> Optional[dict]:
    with _conn() as c:
        course = c.execute("SELECT * FROM courses WHERE id=?", (course_id,)).fetchone()
        if not course:
            return None
        chapters = c.execute(
            "SELECT * FROM chapters WHERE course_id=? ORDER BY ord", (course_id,)
        ).fetchall()
        result = dict(course)
        result["chapters"] = []
        for ch in chapters:
            chapter = dict(ch)
            lessons = c.execute(
                """
                SELECT l.*, COALESCE(p.understanding,'not_started') AS understanding,
                       COALESCE(p.status,'not_started') AS status,
                       COALESCE(p.attempts,0) AS attempts,
                       COALESCE(p.last_verdict,'') AS last_verdict,
                       COALESCE(p.retest_count,0) AS retest_count
                FROM lessons l LEFT JOIN progress p ON p.lesson_id=l.id
                WHERE l.chapter_id=? ORDER BY l.ord
                """,
                (ch["id"],),
            ).fetchall()
            chapter["lessons"] = [_lesson_public(l) for l in lessons]
            result["chapters"].append(chapter)
        stats = course_progress(course_id)
        result.update(stats)
        result["completion_label"] = _completion_label({**result, **stats})
        result["source_hash"] = result.get("source_hash") or ""
        result["fingerprint"] = (result["source_hash"] or "")[:12]
        owner = result.get("user_id") or ""
        latest = latest_defense(course_id, owner) if owner else None
        result["defense"] = (
            {"id": latest.get("id"), "status": latest.get("status")} if latest else None
        )
    return result


def get_lesson(lesson_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            """
            SELECT l.*, COALESCE(p.understanding,'not_started') AS understanding,
                   COALESCE(p.status,'not_started') AS status,
                   COALESCE(p.attempts,0) AS attempts,
                   COALESCE(p.last_verdict,'') AS last_verdict,
                   COALESCE(p.retest_count,0) AS retest_count,
                   COALESCE(p.asked_questions,'[]') AS asked_questions
            FROM lessons l LEFT JOIN progress p ON p.lesson_id=l.id
            WHERE l.id=?
            """,
            (lesson_id,),
        ).fetchone()
    if not row:
        return None
    d = _lesson_public(row)
    d["asked_questions"] = _json_list(row["asked_questions"])
    return d


def get_lesson_content(lesson_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            "SELECT content, diagram, question, reteach_content, source_excerpts FROM lessons WHERE id=?",
            (lesson_id,),
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["source_excerpts"] = _json_list(d.get("source_excerpts"))
    return d


def delete_course(course_id: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM courses WHERE id=?", (course_id,))


def course_owner(course_id: str) -> Optional[str]:
    with _conn() as c:
        row = c.execute("SELECT user_id FROM courses WHERE id=?", (course_id,)).fetchone()
    return row["user_id"] if row else None


def lesson_owner(lesson_id: str) -> Optional[str]:
    with _conn() as c:
        row = c.execute(
            """
            SELECT c.user_id FROM lessons l
            JOIN chapters ch ON l.chapter_id=ch.id
            JOIN courses c ON ch.course_id=c.id
            WHERE l.id=?
            """,
            (lesson_id,),
        ).fetchone()
    return row["user_id"] if row else None


def lesson_course_id(lesson_id: str) -> Optional[str]:
    with _conn() as c:
        row = c.execute(
            """
            SELECT ch.course_id FROM lessons l
            JOIN chapters ch ON l.chapter_id=ch.id
            WHERE l.id=?
            """,
            (lesson_id,),
        ).fetchone()
    return row["course_id"] if row else None


# ---------- 学习看板 ----------

def get_dashboard() -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            """
            SELECT u.id, u.username, u.nickname, u.created_at,
                   (SELECT COUNT(*) FROM courses c WHERE c.user_id=u.id) AS course_count,
                   (SELECT COUNT(*) FROM lessons l
                     JOIN chapters ch ON l.chapter_id=ch.id
                     JOIN courses c ON ch.course_id=c.id
                     WHERE c.user_id=u.id) AS total_lessons,
                   (SELECT COUNT(*) FROM lessons l
                     JOIN chapters ch ON l.chapter_id=ch.id
                     JOIN courses c ON ch.course_id=c.id
                     JOIN progress p ON p.lesson_id=l.id
                     WHERE c.user_id=u.id AND p.understanding='understood') AS completed_lessons
            FROM users u
            WHERE u.id != '_default'
            ORDER BY completed_lessons DESC, course_count DESC
            """
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        total = d.get("total_lessons", 0) or 0
        d["mastery"] = round((d.get("completed_lessons", 0) or 0) / total * 100) if total else 0
        result.append(d)
    return result


# ---------- 分享 ----------

def create_share_link(course_id: str, token: str) -> str:
    with _conn() as c:
        c.execute(
            "INSERT INTO share_links (id, course_id, token) VALUES (?, ?, ?)",
            (_id(), course_id, token),
        )
    return token


def get_share_link(token: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM share_links WHERE token=?", (token,)).fetchone()
    return dict(row) if row else None


def import_course(source_course_id: str, user_id: str) -> str:
    """复制课程结构到 user_id 名下（含原文锚点与讲解，不含记忆卡片）。"""
    src = get_course(source_course_id)
    if not src:
        raise ValueError("源课程不存在")

    outline = {
        "chapters": [
            {
                "title": ch["title"],
                "lessons": [
                    {
                        "title": l["title"],
                        "summary": l.get("summary", ""),
                        "excerpts": l.get("source_excerpts") or [],
                        "loc": "",
                    }
                    for l in ch["lessons"]
                ],
            }
            for ch in src["chapters"]
        ]
    }
    new_id = create_course(src["title"], src.get("source_file", ""), outline, user_id)

    with _conn() as c:
        new_chapters = c.execute(
            "SELECT * FROM chapters WHERE course_id=? ORDER BY ord", (new_id,)
        ).fetchall()
        for si, s_ch in enumerate(src["chapters"]):
            if si >= len(new_chapters):
                break
            n_ch = new_chapters[si]
            n_lessons = c.execute(
                "SELECT * FROM lessons WHERE chapter_id=? ORDER BY ord", (n_ch["id"],)
            ).fetchall()
            for li, s_lesson in enumerate(s_ch["lessons"]):
                if li >= len(n_lessons):
                    break
                n_lesson = n_lessons[li]
                excerpts = s_lesson.get("source_excerpts") or []
                if not isinstance(excerpts, str):
                    excerpts = json.dumps(excerpts, ensure_ascii=False)
                c.execute(
                    "UPDATE lessons SET content=?, diagram=?, question=?, source_excerpts=? WHERE id=?",
                    (
                        s_lesson.get("content", ""),
                        s_lesson.get("diagram", ""),
                        s_lesson.get("question", ""),
                        excerpts,
                        n_lesson["id"],
                    ),
                )
        c.execute(
            "UPDATE courses SET shared_from=?, source_hash=? WHERE id=?",
            (source_course_id, src.get("source_hash") or "", new_id),
        )
    return new_id


# ---------- 卡片 ----------

def _lesson_source_fallback(lesson_id: str) -> str:
    """create_cards 用：摘要 → 摘录首句 → 标题。"""
    lesson = get_lesson(lesson_id) or {}
    summary = (lesson.get("summary") or "").strip()
    if summary:
        return summary[:200]
    excerpts = lesson.get("source_excerpts") or []
    texts = []
    for item in excerpts:
        if isinstance(item, dict):
            t = (item.get("excerpt") or "").strip()
        else:
            t = str(item or "").strip()
        if t:
            texts.append(t)
    blob = "\n".join(texts).strip()
    if blob:
        for sep in ("。", "！", "？", "\n"):
            if sep in blob:
                first = blob.split(sep, 1)[0].strip()
                if first:
                    return first[:200]
        return blob[:200]
    return (lesson.get("title") or "").strip()[:200]


def create_cards(user_id: str, lesson_id: str, cards: list) -> int:
    """批量建卡。已有未删卡则跳过。source_ref 为空时用摘要/摘录首句兜底，不丢弃。"""
    from ..core.scheduler import new_card_state

    existing = list_cards(lesson_id, user_id, include_deleted=False)
    if existing:
        return 0
    fallback = _lesson_source_fallback(lesson_id)
    created = 0
    with _conn() as c:
        for card in cards:
            front = (card.get("front") or "").strip()
            back = (card.get("back") or "").strip()
            if not front or not back:
                continue
            source_ref = (card.get("source_ref") or "").strip() or fallback or front[:200]
            fsrs_state, due_at = new_card_state(1.0)
            c.execute(
                """
                INSERT INTO cards (id, user_id, lesson_id, card_type, front, back, source_ref,
                                   fsrs_state, due_at, lapses, deleted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
                """,
                (
                    _id(),
                    user_id,
                    lesson_id,
                    card.get("card_type") or "concept",
                    front,
                    back,
                    source_ref,
                    fsrs_state,
                    due_at,
                ),
            )
            created += 1
    return created


def list_cards(lesson_id: str, user_id: str, include_deleted: bool = False) -> list[dict]:
    with _conn() as c:
        if include_deleted:
            rows = c.execute(
                "SELECT * FROM cards WHERE lesson_id=? AND user_id=? ORDER BY created_at",
                (lesson_id, user_id),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM cards WHERE lesson_id=? AND user_id=? AND deleted=0 ORDER BY created_at",
                (lesson_id, user_id),
            ).fetchall()
    return [dict(r) for r in rows]


def get_card(card_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
    return dict(row) if row else None


def card_desired_retention(card_id: str) -> float:
    with _conn() as c:
        row = c.execute(
            """
            SELECT c.desired_retention
            FROM cards cd
            JOIN lessons l ON cd.lesson_id=l.id
            JOIN chapters ch ON l.chapter_id=ch.id
            JOIN courses c ON ch.course_id=c.id
            WHERE cd.id=?
            """,
            (card_id,),
        ).fetchone()
    try:
        return float(row["desired_retention"]) if row and row["desired_retention"] else 0.9
    except (TypeError, ValueError):
        return 0.9


def soft_delete_card(card_id: str) -> None:
    with _conn() as c:
        c.execute("UPDATE cards SET deleted=1 WHERE id=?", (card_id,))


def update_card_fsrs(card_id: str, fsrs_state: str, due_at: str, lapses: int) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE cards SET fsrs_state=?, due_at=?, lapses=? WHERE id=?",
            (fsrs_state, due_at, lapses, card_id),
        )


def due_cards(user_id: str, now: str, limit: int = 50) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            """
            SELECT cd.*, l.title AS lesson_title, l.reteach_content, ch.course_id, c.title AS course_title
            FROM cards cd
            JOIN lessons l ON cd.lesson_id=l.id
            JOIN chapters ch ON l.chapter_id=ch.id
            JOIN courses c ON ch.course_id=c.id
            WHERE cd.user_id=? AND cd.deleted=0 AND cd.due_at != '' AND cd.due_at <= ?
            ORDER BY cd.due_at
            LIMIT ?
            """,
            (user_id, now, limit),
        ).fetchall()
        pulled = c.execute(
            """
            SELECT cd.*, l.title AS lesson_title, l.reteach_content, ch.course_id, c.title AS course_title
            FROM cards cd
            JOIN lessons l ON cd.lesson_id=l.id
            JOIN chapters ch ON l.chapter_id=ch.id
            JOIN courses c ON ch.course_id=c.id
            WHERE cd.user_id=? AND cd.deleted=0 AND cd.due_at != ''
              AND c.exam_date != ''
              AND date(c.exam_date) BETWEEN date('now') AND date('now', '+14 days')
              AND cd.due_at > ?
              AND cd.due_at > c.exam_date
            ORDER BY cd.due_at
            LIMIT 15
            """,
            (user_id, now),
        ).fetchall()
    seen: set[str] = set()
    out: list[dict] = []
    for r in list(rows) + list(pulled):
        d = dict(r)
        if d["id"] in seen:
            continue
        seen.add(d["id"])
        out.append(d)
        if len(out) >= limit:
            break
    return out


def add_review_log(card_id: str, user_id: str, rating: str, elapsed_days: float, scheduled_days: float) -> None:
    with _conn() as c:
        c.execute(
            """
            INSERT INTO review_logs (id, card_id, user_id, rating, elapsed_days, scheduled_days, reviewed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (_id(), card_id, user_id, rating, elapsed_days, scheduled_days, _now_iso()),
        )


def count_settled_cards(lesson_id: str, user_id: str) -> int:
    with _conn() as c:
        row = c.execute(
            """
            SELECT COUNT(DISTINCT rl.card_id) AS n FROM review_logs rl
            JOIN cards cd ON rl.card_id=cd.id
            WHERE cd.lesson_id=? AND cd.user_id=? AND cd.deleted=0
              AND rl.rating IN ('good','easy') AND rl.scheduled_days >= 3
            """,
            (lesson_id, user_id),
        ).fetchone()
    return int(row["n"] or 0) if row else 0


def course_progress(course_id: str) -> dict:
    with _conn() as c:
        row = c.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM lessons l JOIN chapters ch ON l.chapter_id=ch.id
                WHERE ch.course_id=?) AS total,
              (SELECT COUNT(*) FROM lessons l JOIN chapters ch ON l.chapter_id=ch.id
                JOIN progress p ON p.lesson_id=l.id
                WHERE ch.course_id=? AND p.understanding='understood') AS understood,
              (SELECT user_id FROM courses WHERE id=?) AS user_id
            """,
            (course_id, course_id, course_id),
        ).fetchone()
        user_id = row["user_id"] if row else ""
        cards_row = c.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM cards cd JOIN lessons l ON cd.lesson_id=l.id
                JOIN chapters ch ON l.chapter_id=ch.id
                WHERE ch.course_id=? AND cd.user_id=? AND cd.deleted=0) AS total_cards,
              (SELECT COUNT(DISTINCT rl.card_id) FROM review_logs rl
                JOIN cards cd ON rl.card_id=cd.id
                JOIN lessons l ON cd.lesson_id=l.id
                JOIN chapters ch ON l.chapter_id=ch.id
                WHERE ch.course_id=? AND cd.user_id=? AND cd.deleted=0
                  AND rl.rating IN ('good','easy') AND rl.scheduled_days >= 3) AS settled_cards
            """,
            (course_id, user_id or "", course_id, user_id or ""),
        ).fetchone()
    return {
        "total_lessons": int(row["total"] or 0) if row else 0,
        "understood_lessons": int(row["understood"] or 0) if row else 0,
        "completed_lessons": int(row["understood"] or 0) if row else 0,
        "total_cards": int(cards_row["total_cards"] or 0) if cards_row else 0,
        "settled_cards": int(cards_row["settled_cards"] or 0) if cards_row else 0,
    }


def today_summary(user_id: str) -> dict:
    cutoff = end_of_local_day_iso()
    due = due_cards(user_id, cutoff, limit=200)
    due_count = len(due)
    with _conn() as c:
        debts = c.execute(
            """
            SELECT l.id AS lesson_id, l.title, ch.course_id, c.title AS course_title
            FROM progress p
            JOIN lessons l ON p.lesson_id=l.id
            JOIN chapters ch ON l.chapter_id=ch.id
            JOIN courses c ON ch.course_id=c.id
            WHERE c.user_id=? AND p.understanding IN ('needs_reteach', 'learning')
            ORDER BY p.updated_at DESC
            """,
            (user_id,),
        ).fetchall()
        next_row = c.execute(
            """
            SELECT l.id AS lesson_id, l.title, ch.course_id, c.title AS course_title
            FROM lessons l
            JOIN chapters ch ON l.chapter_id=ch.id
            JOIN courses c ON ch.course_id=c.id
            LEFT JOIN progress p ON p.lesson_id=l.id
            WHERE c.user_id=? AND COALESCE(p.understanding,'not_started') != 'understood'
            ORDER BY c.created_at DESC, ch.ord, l.ord
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    user = get_user(user_id) or {}
    override_until = user.get("circuit_override_until") or ""
    override_active = _iso_in_future(override_until)
    overloaded = due_count > CIRCUIT_DUE_LIMIT
    return {
        "due_count": due_count,
        "due_minutes": 0,
        "overloaded": overloaded,
        "locked_new": overloaded and not override_active,
        "override_until": override_until if override_active else "",
        "circuit_limit": CIRCUIT_DUE_LIMIT,
        "debts": [dict(r) for r in debts],
        "next_lesson": dict(next_row) if next_row else None,
        "exam_risks": exam_risks(user_id),
    }


def review_stats(user_id: str) -> dict:
    cutoff = end_of_local_day_iso()
    cutoff_14 = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    cutoff_7 = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    due = due_cards(user_id, cutoff, limit=500)
    with _conn() as c:
        recent = c.execute(
            """
            SELECT rating, scheduled_days, reviewed_at, card_id FROM review_logs
            WHERE user_id=? AND reviewed_at >= ?
            """,
            (user_id, cutoff_14),
        ).fetchall()
        week = c.execute(
            """
            SELECT COUNT(*) AS n FROM review_logs
            WHERE user_id=? AND reviewed_at >= ?
            """,
            (user_id, cutoff_7),
        ).fetchone()
        weakest = c.execute(
            """
            SELECT l.id AS lesson_id, l.title, ch.course_id, c.title AS course_title,
                   SUM(CASE WHEN rl.rating='again' THEN 1 ELSE 0 END) AS again_count,
                   COUNT(*) AS review_count
            FROM review_logs rl
            JOIN cards cd ON rl.card_id=cd.id
            JOIN lessons l ON cd.lesson_id=l.id
            JOIN chapters ch ON l.chapter_id=ch.id
            JOIN courses c ON ch.course_id=c.id
            WHERE rl.user_id=? AND cd.deleted=0
            GROUP BY l.id
            HAVING again_count > 0
            ORDER BY again_count DESC, review_count DESC
            LIMIT 5
            """,
            (user_id,),
        ).fetchall()
        chapters = c.execute(
            """
            SELECT c.id AS course_id, c.title AS course_title, ch.id AS chapter_id, ch.title AS chapter_title,
                   COUNT(l.id) AS total,
                   SUM(CASE WHEN p.understanding='understood' THEN 1 ELSE 0 END) AS understood
            FROM courses c
            JOIN chapters ch ON ch.course_id=c.id
            JOIN lessons l ON l.chapter_id=ch.id
            LEFT JOIN progress p ON p.lesson_id=l.id
            WHERE c.user_id=?
            GROUP BY ch.id
            ORDER BY c.created_at DESC, ch.ord
            """,
            (user_id,),
        ).fetchall()

    ratings = [r["rating"] for r in recent]
    success = sum(1 for r in ratings if r in ("good", "easy"))
    retention_14d = round(success / len(ratings) * 100) if ratings else None
    week_reviews = int(week["n"] or 0) if week else 0
    week_due_proxy = week_reviews + len(due)
    week_compliance = round(week_reviews / week_due_proxy * 100) if week_due_proxy else None

    courses = list_courses(user_id)
    return {
        "retention_14d": retention_14d,
        "due_today": len(due),
        "week_reviews": week_reviews,
        "week_compliance": week_compliance,
        "weakest": [dict(r) for r in weakest],
        "chapters": [dict(r) for r in chapters],
        "courses": courses,
        "sample_size": len(ratings),
        "exam_risks": exam_risks(user_id),
    }


def update_course_settings(
    course_id: str,
    exam_date: str | None = None,
    desired_retention: float | None = None,
) -> None:
    fields: list[str] = []
    args: list = []
    if exam_date is not None:
        fields.append("exam_date=?")
        args.append(exam_date.strip())
    if desired_retention is not None:
        rate = float(desired_retention)
        if rate not in (0.85, 0.9, 0.95):
            raise ValueError("目标保持率只能是 0.85 / 0.9 / 0.95")
        fields.append("desired_retention=?")
        args.append(rate)
    if not fields:
        return
    args.append(course_id)
    with _conn() as c:
        c.execute(f"UPDATE courses SET {', '.join(fields)} WHERE id=?", args)


def exam_risks(user_id: str) -> list[dict]:
    """有考试日且尚未记住的课。"""
    with _conn() as c:
        rows = c.execute(
            """
            SELECT c.id, c.title, c.exam_date,
                   (SELECT COUNT(*) FROM lessons l JOIN chapters ch ON l.chapter_id=ch.id
                     WHERE ch.course_id=c.id) AS total_lessons,
                   (SELECT COUNT(*) FROM lessons l JOIN chapters ch ON l.chapter_id=ch.id
                     JOIN progress p ON p.lesson_id=l.id
                     WHERE ch.course_id=c.id AND p.understanding='understood') AS understood_lessons
            FROM courses c
            WHERE c.user_id=? AND c.exam_date != ''
            ORDER BY c.exam_date
            """,
            (user_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["understood_lessons"] = d.get("understood_lessons") or 0
        d["total_lessons"] = d.get("total_lessons") or 0
        out.append(d)
    return out


def chapter_owner(chapter_id: str) -> Optional[str]:
    with _conn() as c:
        row = c.execute(
            """
            SELECT c.user_id FROM chapters ch
            JOIN courses c ON ch.course_id=c.id
            WHERE ch.id=?
            """,
            (chapter_id,),
        ).fetchone()
    return row["user_id"] if row else None


def get_chapter(chapter_id: str) -> Optional[dict]:
    with _conn() as c:
        ch = c.execute("SELECT * FROM chapters WHERE id=?", (chapter_id,)).fetchone()
        if not ch:
            return None
        lessons = c.execute(
            """
            SELECT l.*, COALESCE(p.understanding,'not_started') AS understanding
            FROM lessons l LEFT JOIN progress p ON p.lesson_id=l.id
            WHERE l.chapter_id=? ORDER BY l.ord
            """,
            (chapter_id,),
        ).fetchall()
    d = dict(ch)
    d["lessons"] = [_lesson_public(l) for l in lessons]
    return d


def chapter_older_lessons(chapter_id: str, user_id: str, limit: int = 6) -> list[dict]:
    """同课程中、本章之前已理解的知识点，供穿插。"""
    with _conn() as c:
        row = c.execute(
            "SELECT course_id, ord FROM chapters WHERE id=?", (chapter_id,)
        ).fetchone()
        if not row:
            return []
        rows = c.execute(
            """
            SELECT l.*, COALESCE(p.understanding,'not_started') AS understanding
            FROM lessons l
            JOIN chapters ch ON l.chapter_id=ch.id
            LEFT JOIN progress p ON p.lesson_id=l.id
            WHERE ch.course_id=? AND ch.ord < ? AND p.understanding='understood'
            ORDER BY ch.ord DESC, l.ord DESC
            LIMIT ?
            """,
            (row["course_id"], row["ord"], limit),
        ).fetchall()
    return [_lesson_public(r) for r in rows]


def chapter_understood(chapter_id: str) -> bool:
    with _conn() as c:
        row = c.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN p.understanding='understood' THEN 1 ELSE 0 END) AS understood
            FROM lessons l LEFT JOIN progress p ON p.lesson_id=l.id
            WHERE l.chapter_id=?
            """,
            (chapter_id,),
        ).fetchone()
    total = int(row["total"] or 0) if row else 0
    understood = int(row["understood"] or 0) if row else 0
    return total > 0 and understood >= total


def get_latest_quiz(chapter_id: str, user_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            """
            SELECT * FROM chapter_quizzes
            WHERE chapter_id=? AND user_id=?
            ORDER BY created_at DESC LIMIT 1
            """,
            (chapter_id, user_id),
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["questions"] = _json_list(d.get("questions"))
    d["results"] = _json_list(d.get("results"))
    return d


def save_chapter_quiz(chapter_id: str, user_id: str, questions: list) -> dict:
    qid = _id()
    with _conn() as c:
        c.execute(
            """
            INSERT INTO chapter_quizzes (id, chapter_id, user_id, questions, results, status, created_at)
            VALUES (?, ?, ?, ?, '[]', 'pending', ?)
            """,
            (qid, chapter_id, user_id, json.dumps(questions, ensure_ascii=False), _now_iso()),
        )
    return get_latest_quiz(chapter_id, user_id) or {
        "id": qid,
        "questions": questions,
        "results": [],
        "status": "pending",
    }


def update_quiz_results(quiz_id: str, results: list, status: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE chapter_quizzes SET results=?, status=? WHERE id=?",
            (json.dumps(results, ensure_ascii=False), status, quiz_id),
        )


def add_report(lesson_id: str, user_id: str, reason: str, note: str = "") -> None:
    with _conn() as c:
        c.execute(
            """
            INSERT INTO reports (id, lesson_id, user_id, reason, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (_id(), lesson_id, user_id, reason or "not_in_source", note or "", _now_iso()),
        )


def get_llm_settings(user_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM user_llm_settings WHERE user_id=?", (user_id,)
        ).fetchone()
    return dict(row) if row else None


def upsert_llm_settings(
    user_id: str,
    provider: str,
    base_url: str,
    model: str,
    temperature: float,
    api_key: str | None,
) -> dict:
    prev = get_llm_settings(user_id)
    key = (api_key or "").strip()
    if not key or key.startswith("•") or set(key) <= {"*", "•"}:
        key = (prev or {}).get("api_key") or ""
    with _conn() as c:
        c.execute(
            """
            INSERT INTO user_llm_settings
                (user_id, provider, base_url, api_key, model, temperature, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                provider=excluded.provider,
                base_url=excluded.base_url,
                api_key=excluded.api_key,
                model=excluded.model,
                temperature=excluded.temperature,
                updated_at=excluded.updated_at
            """,
            (user_id, provider, base_url.strip(), key, model.strip(), float(temperature), _now_iso()),
        )
    return get_llm_settings(user_id) or {}


def clear_llm_settings(user_id: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM user_llm_settings WHERE user_id=?", (user_id,))


# ---------- 套餐 / 熔断 / 答辩 / 销户 ----------

def _iso_in_future(raw: str) -> bool:
    if not raw:
        return False
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt > datetime.now(timezone.utc)
    except ValueError:
        return False


def count_courses(user_id: str) -> int:
    with _conn() as c:
        row = c.execute("SELECT COUNT(*) AS n FROM courses WHERE user_id=?", (user_id,)).fetchone()
    return int(row["n"] or 0) if row else 0


def billing_snapshot(user_id: str) -> dict:
    user = get_user(user_id) or {}
    plan = plan_of(user)
    used = count_courses(user_id)
    return {
        "plan": plan["id"],
        "plan_name": plan["name"],
        "price": plan["price"],
        "blurb": plan["blurb"],
        "max_courses": plan["max_courses"],
        "used_courses": used,
        "remaining_courses": max(0, plan["max_courses"] - used),
        "official_certificate": bool(plan["official_certificate"]),
        "defense": bool(plan["defense"]),
        "plans": public_plans(plan["id"]),
    }


def set_user_plan(user_id: str, plan: str) -> dict:
    pid = normalize_plan(plan)
    with _conn() as c:
        c.execute("UPDATE users SET plan=? WHERE id=?", (pid, user_id))
    return billing_snapshot(user_id)


def grant_owner_plan(user_id: str, username: str) -> None:
    if is_owner(username):
        with _conn() as c:
            c.execute("UPDATE users SET plan='lab' WHERE id=?", (user_id,))


def can_create_course(user_id: str) -> tuple[bool, str]:
    user = get_user(user_id) or {}
    plan = plan_of(user)
    used = count_courses(user_id)
    if used >= int(plan["max_courses"]):
        return False, quota_message(plan, used)
    return True, ""


def set_circuit_override(user_id: str) -> dict:
    until = end_of_local_day()
    with _conn() as c:
        c.execute(
            "UPDATE users SET circuit_override_until=? WHERE id=?",
            (until.astimezone(timezone.utc).isoformat(), user_id),
        )
    return today_summary(user_id)


def list_understood_lessons(course_id: str) -> list[dict]:
    course = get_course(course_id)
    if not course:
        return []
    out = []
    for ch in course.get("chapters") or []:
        for l in ch.get("lessons") or []:
            if (l.get("understanding") or "") == "understood":
                out.append(l)
    return out


def _defense_public(row) -> dict:
    if not row:
        return {}
    d = dict(row)
    d["questions"] = _json_list(d.get("questions"))
    d["answers"] = _json_list(d.get("answers"))
    return d


def latest_defense(course_id: str, user_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            """
            SELECT * FROM defense_sessions
            WHERE course_id=? AND user_id=?
            ORDER BY created_at DESC LIMIT 1
            """,
            (course_id, user_id),
        ).fetchone()
    return _defense_public(row) if row else None


def get_defense(defense_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM defense_sessions WHERE id=?", (defense_id,)).fetchone()
    return _defense_public(row) if row else None


def create_defense(course_id: str, user_id: str, questions: list) -> dict:
    did = _id()
    with _conn() as c:
        c.execute(
            """
            INSERT INTO defense_sessions
                (id, course_id, user_id, questions, answers, status, created_at)
            VALUES (?, ?, ?, ?, '[]', 'pending', ?)
            """,
            (did, course_id, user_id, json.dumps(questions, ensure_ascii=False), _now_iso()),
        )
    return get_defense(did) or {}


def update_defense_answers(defense_id: str, answers: list, status: str) -> None:
    finished = _now_iso() if status in ("passed", "failed") else ""
    with _conn() as c:
        if finished:
            c.execute(
                "UPDATE defense_sessions SET answers=?, status=?, finished_at=? WHERE id=?",
                (json.dumps(answers, ensure_ascii=False), status, finished, defense_id),
            )
        else:
            c.execute(
                "UPDATE defense_sessions SET answers=?, status=? WHERE id=?",
                (json.dumps(answers, ensure_ascii=False), status, defense_id),
            )


def delete_user(user_id: str) -> None:
    """级联删除账号下的课、卡、Key、答辩。"""
    with _conn() as c:
        c.execute("DELETE FROM chapter_quizzes WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM review_logs WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM cards WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM reports WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM defense_sessions WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM user_llm_settings WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM courses WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM users WHERE id=?", (user_id,))


def certificate_payload(defense: dict, user_id: str) -> dict:
    course = get_course(defense.get("course_id") or "") or {}
    stats = review_stats(user_id)
    plan = plan_of(get_user(user_id) or {})
    answers = {a.get("index"): a for a in (defense.get("answers") or [])}
    items = []
    for i, q in enumerate(defense.get("questions") or []):
        a = answers.get(i) or {}
        items.append(
            {
                "index": i,
                "question": q.get("question") or "",
                "answer_excerpt": ((a.get("answer") or "")[:180]),
                "verdict": a.get("verdict") or "",
                "feedback": a.get("feedback") or "",
                "lesson_title": q.get("lesson_title") or "",
            }
        )
    understood = course.get("understood_lessons") or 0
    total = course.get("total_lessons") or 0
    return {
        "defense_id": defense.get("id"),
        "status": defense.get("status"),
        "official": bool(plan["official_certificate"]) and defense.get("status") == "passed",
        "plan": plan["id"],
        "course_title": course.get("title") or "",
        "fingerprint": (course.get("source_hash") or "")[:12],
        "source_file": course.get("source_file") or "",
        "understood_lessons": understood,
        "total_lessons": total,
        "settled_cards": course.get("settled_cards") or 0,
        "total_cards": course.get("total_cards") or 0,
        "completion_label": course.get("completion_label") or "",
        "retention_14d": stats.get("retention_14d"),
        "sample_size": stats.get("sample_size") or 0,
        "finished_at": defense.get("finished_at") or "",
        "created_at": defense.get("created_at") or "",
        "items": items,
        "passed": defense.get("status") == "passed",
    }

