"""数据模型（Pydantic schema）。

定义课程三级结构：课程 → 章节 → 知识点，以及学习进度。
同时定义拆课服务从 LLM 收到的结构化契约。
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------- 拆课：LLM 返回的结构化契约 ----------

class LessonOutline(BaseModel):
    """拆课时 LLM 返回的单个知识点。"""
    title: str = Field(description="知识点标题，一句话")
    summary: str = Field(default="", description="这个知识点的核心结论，一两句话")
    excerpts: List[str] = Field(default_factory=list, description="从原文逐字摘录的 1–3 段")
    loc: str = Field(default="", description="摘录在资料中的位置")

    @field_validator("excerpts", mode="before")
    @classmethod
    def _coerce_excerpts(cls, v):
        if not v:
            return []
        out = []
        for item in v:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                text = (item.get("excerpt") or item.get("text") or "").strip()
                if text:
                    out.append(text)
        return out


class ChapterOutline(BaseModel):
    """拆课时 LLM 返回的章节。"""
    title: str = Field(description="章节标题")
    lessons: List[LessonOutline] = Field(description="该章节下的知识点列表")


class CourseOutline(BaseModel):
    """拆课时 LLM 返回的整门课程结构。"""
    title: str = Field(description="课程标题")
    chapters: List[ChapterOutline] = Field(description="章节列表")


# ---------- 领域模型 ----------

class Lesson(BaseModel):
    """知识点（已含讲解内容）。"""
    id: str
    chapter_id: str
    title: str
    summary: str = ""
    content: str = ""          # 讲解正文
    diagram: str = ""          # Mermaid 图源码
    question: str = ""         # 反问的问题
    ord: int = 0
    status: str = "not_started"   # not_started / in_progress / completed / needs_review
    attempts: int = 0


class Chapter(BaseModel):
    """章节。"""
    id: str
    title: str
    ord: int = 0
    lessons: List[Lesson] = []


class Course(BaseModel):
    """课程（含进度统计）。"""
    id: str
    title: str
    source_file: str = ""
    chapters: List[Chapter] = []
    total_lessons: int = 0
    completed_lessons: int = 0


class AnswerRequest(BaseModel):
    """用户回答反问。"""
    lesson_id: str
    answer: str


class MemoryCardOut(BaseModel):
    """过关后生成的记忆卡片。"""
    id: str = ""
    card_type: str = "concept"
    front: str = ""
    back: str = ""
    source_ref: str = ""


class AnswerResult(BaseModel):
    """AI 判断用户回答后的反馈。"""
    verdict: str          # mastered / partial / not_mastered
    feedback: str         # 给用户的反馈
    explanation: str = "" # 补充讲解（未掌握时）
    next: bool = False    # 是否进入下一个知识点
    gap: str = ""         # 具体缺口，供补讲
    retest_required: bool = False
    cards: List[MemoryCardOut] = Field(default_factory=list)


class ReteachRequest(BaseModel):
    """请求补讲。"""
    answer: str = ""
    gap: str = ""


class CardReviewRequest(BaseModel):
    """记忆复习自评。"""
    rating: str = Field(description="again / hard / good / easy")


class TutorChunk(BaseModel):
    """流式讲课的一帧。"""
    type: str             # text / diagram / question / done / error
    content: str = ""


class CourseProgress(BaseModel):
    """课程整体进度。"""
    course_id: str
    total: int
    completed: int
    percent: int


# ---------- 认证 ----------

class RegisterRequest(BaseModel):
    """注册请求。"""
    username: str = Field(min_length=2, max_length=32, description="用户名")
    password: str = Field(min_length=6, max_length=64, description="密码")
    nickname: str = Field(default="", max_length=32, description="昵称")


class LoginRequest(BaseModel):
    """登录请求。"""
    username: str
    password: str


class AuthResponse(BaseModel):
    """认证响应。"""
    token: str
    user_id: str
    username: str
    nickname: str = ""


class ShareImportRequest(BaseModel):
    """分享导入请求。"""
    token: str


class CourseSettingsRequest(BaseModel):
    """课程设置：考试日与目标保持率。"""
    exam_date: Optional[str] = ""
    desired_retention: Optional[float] = None


class ChapterQuizAnswerRequest(BaseModel):
    """章节收口测验作答。"""
    index: int
    answer: str


class ReportRequest(BaseModel):
    """讲解不在资料里。"""
    reason: str = "not_in_source"
    note: str = ""


class PretestAnswerRequest(BaseModel):
    """诊断前测作答。"""
    answer: str


class LlmSettingsRequest(BaseModel):
    """页面配置的大模型（OpenAI 兼容）。"""
    provider: str = "deepseek"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.7


class PlanSwitchRequest(BaseModel):
    """演示切换套餐。支付上线后关闭。"""
    plan: str = "free"


class CircuitOverrideRequest(BaseModel):
    """负荷熔断知情确认。"""
    acknowledge: bool = False


class DefenseAnswerRequest(BaseModel):
    """合上书答辩作答。"""
    index: int
    answer: str


class DeleteAccountRequest(BaseModel):
    """删除账号确认。"""
    confirm: str = ""
