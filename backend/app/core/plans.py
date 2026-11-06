"""套餐与配额。支付未接入前由设置页演示切换。"""
from __future__ import annotations

from typing import Optional

PLANS: dict[str, dict] = {
    "free": {
        "id": "free",
        "name": "体验",
        "price": "0 元",
        "max_courses": 1,
        "official_certificate": False,
        "defense": True,
        "blurb": "1 门课、掌握门、今日复习、双进度、自带 Key。凭证带体验水印。",
    },
    "pro": {
        "id": "pro",
        "name": "个人 Pro",
        "price": "49 元/月",
        "max_courses": 99,
        "official_certificate": True,
        "defense": True,
        "blurb": "多门课、合上书答辩正式凭证、负荷熔断、考前模式。",
    },
    "sprint": {
        "id": "sprint",
        "name": "冲刺包",
        "price": "69 元 / 14 天",
        "max_courses": 1,
        "official_certificate": True,
        "defense": True,
        "blurb": "一门课的正式答辩凭证。支付上线后按 14 天有效。",
    },
    "lab": {
        "id": "lab",
        "name": "实验室",
        "price": "内部",
        "max_courses": 9999,
        "official_certificate": True,
        "defense": True,
        "blurb": "不限门课，正式凭证，可在本页切换体验/Pro/冲刺预览。",
    },
}

DEFAULT_PLAN = "free"
CIRCUIT_DUE_LIMIT = 40
OWNER_USERNAMES = {"ain"}


def is_owner(username: Optional[str]) -> bool:
    return (username or "").strip().lower() in OWNER_USERNAMES


def public_plans(current_plan: str) -> list[dict]:
    """实验室套餐只给内部账号看，避免普通用户点到。"""
    if current_plan == "lab":
        return list(PLANS.values())
    return [p for p in PLANS.values() if p["id"] != "lab"]

DEFAULT_PLAN = "free"
CIRCUIT_DUE_LIMIT = 40


def normalize_plan(plan: Optional[str]) -> str:
    p = (plan or DEFAULT_PLAN).strip().lower()
    return p if p in PLANS else DEFAULT_PLAN


def plan_of(user: Optional[dict]) -> dict:
    return PLANS[normalize_plan((user or {}).get("plan"))]


def quota_message(plan: dict, used: int) -> str:
    name = plan["name"]
    cap = plan["max_courses"]
    return f"「{name}」最多 {cap} 门课，你已有 {used} 门。删除一门，或到设置里切换到个人 Pro。"
