"""FSRS 间隔重复封装。

直接使用 PyPI `fsrs`（Scheduler / Card / Rating），卡状态 JSON 落库。
到期按当地自然日，不卡钟点：当天到期的卡，当天任何时候都可以练。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fsrs import Card, Rating, Scheduler

# 学习/重学都按「天」，不要 10 分钟后再见——那会让人以为不到点不能练。
_scheduler = Scheduler(
    desired_retention=0.9,
    learning_steps=(timedelta(days=1),),
    relearning_steps=(timedelta(days=1),),
)

_RATING = {
    "again": Rating.Again,
    "hard": Rating.Hard,
    "good": Rating.Good,
    "easy": Rating.Easy,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def local_now() -> datetime:
    return datetime.now().astimezone()


def end_of_local_day(when: datetime | None = None) -> datetime:
    """当天 23:59:59.999999（本地时区）。"""
    local = (when or local_now())
    if local.tzinfo is None:
        local = local.replace(tzinfo=local_now().tzinfo)
    else:
        local = local.astimezone()
    return local.replace(hour=23, minute=59, second=59, microsecond=999999)


def end_of_local_day_iso(when: datetime | None = None) -> str:
    return end_of_local_day(when).astimezone(timezone.utc).isoformat()


def snap_due_to_local_day(due: datetime) -> datetime:
    """把到期时刻落到当地日历日 0 点，当天全天都算到期。"""
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    local = due.astimezone()
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc)


def new_card_state(due_in_days: float = 1.0) -> tuple[str, str]:
    """新建一张尚未复习的卡：明天（自然日）到期。"""
    card = Card()
    raw = _utc_now() + timedelta(days=due_in_days)
    card.due = snap_due_to_local_day(raw)
    return card.to_json(), card.due.isoformat()


def review_card(
    fsrs_state: str,
    rating: str,
    now: datetime | None = None,
    desired_retention: float | None = None,
) -> dict:
    """根据上次序列化状态 + 本次评分，返回新状态与下次到期。"""
    key = (rating or "").strip().lower()
    if key not in _RATING:
        raise ValueError("评分必须是 again / hard / good / easy")

    card = Card.from_json(fsrs_state) if fsrs_state else Card()
    review_at = now or _utc_now()
    if review_at.tzinfo is None:
        review_at = review_at.replace(tzinfo=timezone.utc)
    else:
        review_at = review_at.astimezone(timezone.utc)

    last = card.last_review
    elapsed_days = 0.0
    if last is not None:
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        elapsed_days = max(0.0, (review_at - last).total_seconds() / 86400)

    scheduler = _scheduler
    if desired_retention in (0.85, 0.9, 0.95) and desired_retention != 0.9:
        scheduler = Scheduler(
            desired_retention=desired_retention,
            learning_steps=(timedelta(days=1),),
            relearning_steps=(timedelta(days=1),),
        )
    new_card, log = scheduler.review_card(card, _RATING[key], review_datetime=review_at)
    new_card.due = snap_due_to_local_day(new_card.due)
    scheduled_days = max(0.0, (new_card.due - log.review_datetime).total_seconds() / 86400)

    return {
        "fsrs_state": new_card.to_json(),
        "due_at": new_card.due.isoformat(),
        "scheduled_days": scheduled_days,
        "elapsed_days": elapsed_days,
        "stability": getattr(new_card, "stability", None),
        "difficulty": getattr(new_card, "difficulty", None),
    }
