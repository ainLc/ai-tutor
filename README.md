# AI 私教学习系统（ai-tutor）

上传一套学习资料，得到一个按这份资料授课的私教：先把你讲懂、再拦住你往下赶，最后按遗忘曲线把该记的东西送回你面前，直到你真的记住。

## 快速开始

### 1. 后端

```bash
cd backend
pip install -r requirements.txt
# 复制 .env.example 为 .env，填入 LLM_API_KEY
uvicorn app.main:app --reload --port 8000
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173

扫描版 PDF 会自动 OCR（需 `pip install -r requirements.txt` 装齐）。手机浏览器可「添加到主屏幕」做 PWA；复习页支持朗读与口答，离线时使用上次缓存的卡片队列。

## 文档

- [产品战略与 PRD（现行方向）](docs/05_学会并记住_产品战略与PRD.md)
- [可行性开发方案（Cursor 实施规格）](docs/06_可行性开发方案.md)
- [产品需求 PRD（MVP 史）](docs/01_产品需求PRD.md)
- [系统架构](docs/02_系统架构.md)
- [UI 设计规范](docs/03_UI设计规范.md)
- [多用户与分享设计](docs/04_多用户与分享设计.md)
- [P2 落地计划](docs/07_P2落地计划.md)
- [产品扩展与商业化（公网收费）](docs/08_产品扩展与商业化.md)
- [商业化架构增量（C0）](docs/09_商业化架构增量.md)

## 技术栈

FastAPI + Vue 3 + Mermaid + 多模型适配（默认 DeepSeek）+ SQLite + FSRS（间隔重复）+ pypdf

## English overview

**AI Tutor** turns a set of learning materials into a personal tutor: it teaches from *your* notes, blocks you from rushing ahead until you understand, and brings forgotten items back via spaced repetition (FSRS) until you actually remember them.

**Stack:** FastAPI + Vue 3 + Mermaid + OpenAI-compatible LLM (DeepSeek by default) + SQLite + FSRS + pypdf/OCR.

**Setup:** copy `backend/.env.example` → `backend/.env`, set `LLM_API_KEY`, then start backend (`uvicorn app.main:app --reload --port 8000`) and frontend (`npm install && npm run dev`).

This repository is a personal portfolio / sample of owned product work (not client or employer code).

