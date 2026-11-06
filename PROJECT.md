# AI 私教学习系统（ai-tutor）

## 项目概述

一个「AI 私教」学习系统：用户上传一套学习资料（如课程、文档、代码），系统自动把资料拆解成课程，像真人老师一样讲课——逻辑清楚、通俗易懂、自动配图，并在讲解过程中主动反问用户，根据用户的回答调整讲解深度，实现苏格拉底式教学闭环。

**解决什么问题**：把「一堆静态学习资料」变成「一个会提问、会配图、因材施教的私人老师」。

## 技术栈与依赖

- 后端：Python 3.10 + FastAPI + Uvicorn（流式 SSE 输出）
- 前端：Vue 3 + Vite + Pinia（状态管理）
- 图表：Mermaid（由 LLM 生成图源码，前端渲染）
- 大模型：多模型可切换适配层，默认 DeepSeek（OpenAI 兼容接口）
- 数据存储：SQLite（第一版 MVP，单机文件库）
- 记忆调度：FSRS（PyPI `fsrs`，间隔重复）
- PDF 解析：pypdf（文本层提取）

## 目录结构

```
ai-tutor/
├── PROJECT.md          # 项目说明（本文件）
├── README.md           # 快速开始
├── docs/               # 设计图纸
│   ├── 01_产品需求PRD.md
│   ├── 02_系统架构.md
│   └── 03_UI设计规范.md
├── backend/            # FastAPI 后端
│   └── app/
│       ├── main.py     # 应用入口
│       ├── core/       # 配置、LLM 适配层
│       ├── models/     # 数据模型（课程/章节/进度）
│       ├── services/   # 拆课、教学引擎、配图生成
│       └── api/        # 路由
└── frontend/           # Vue 3 前端
    └── src/
        ├── views/      # 页面
        ├── components/ # 组件
        ├── stores/     # Pinia 状态
        └── api/        # 接口封装
```

## 核心功能

1. 上传资料 → 自动拆解成课程与章节（原文锚点）
2. AI 讲课（流式输出）+ 自动配图（Mermaid）
3. 讲解中反问用户 → 根据回答调整讲解（掌握门：补讲 + 平行再测）
4. 过关后自动生成记忆卡片 → 间隔重复（FSRS）复习
5. 学习进度记录与断点续学（理解进度 + 记忆进度双轨）

> 产品方向已从「会讲课」升级为「学会并记住」，详见 `docs/05_学会并记住_产品战略与PRD.md` 与 `docs/06_可行性开发方案.md`。

## 启动方式

```bash
# 后端
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173

## 变更记录

- 2026-09-03 | 新增 | 初始化项目：目录结构、PRD、系统架构、UI 设计规范四份文档 | PROJECT.md、docs/
- 2026-09-03 | 新增 | 实现后端：LLM 适配层、SQLite 存储、拆课服务、教学引擎、SSE 流式 API | backend/app/
- 2026-09-03 | 新增 | 实现前端：Vue3 页面（首页/听课页/上传）、Mermaid 配图、反问交互、流式渲染 | frontend/src/
- 2026-09-03 | 修复 | 修正 routes.py 的 db 导入路径（`from .. import db` → `from ..models import db`） | backend/app/api/routes.py
- 2026-09-03 | 验证 | 后端导入冒烟、健康检查、课程列表、上传错误处理、前端构建全部通过 | 全项目
- 2026-09-03 | 验证 | 填入 DeepSeek key，端到端实测通过：拆课(7章23知识点)、SSE流式讲课、Mermaid配图、反问、掌握度判分 | backend/.env、全链路
- 2026-09-03 | 新增 | 多用户系统：注册/登录/JWT认证、数据隔离、学习看板、课程分享 | backend/app/core/auth.py、models/db.py、api/routes.py、前端 Login/Dashboard/Home
- 2026-09-03 | 修复 | 分享导入路由顺序问题（/share/import 被 /share/{course_id} 吞掉） | backend/app/api/routes.py
- 2026-09-04 | 配置 | 前后端监听 0.0.0.0 支持局域网/手机访问，新增一键启动脚本和防火墙放行脚本 | vite.config.js、一键启动.bat、一键放行防火墙.bat
- 2026-09-08 | 产品 | 重写产品方向：从「会讲课」升级为「学会并记住」；对标 Khanmigo / NotebookLM / Anki，补掌握门与间隔重复 | docs/05_学会并记住_产品战略与PRD.md
- 2026-09-08 | 新增 | 落实掌握学习 + FSRS 记忆：原文锚点拆课、补讲再测、制卡、今日复习、双进度、个人保持率报告、PDF 文本提取 | backend/app/、frontend/src/
- 2026-09-08 | 产品 | 新增可行性开发方案（Cursor 实施规格）：数据模型/API/里程碑/验收；修正 FSRS 直接采用 py-fsrs 库、复习以自评为准；补充技术栈 fsrs+pypdf | docs/06_可行性开发方案.md、docs/05、PROJECT.md
- 2026-09-08 | 验证 | 端到端验收通过（DeepSeek 实测）：上传拆课带原文锚点→流式讲课配图提问→答错补讲→再测换题→答对制卡(5张)→复习评分调度→今日摘要/掌握报告 | 全链路
- 2026-09-08 | 修复 | 修复验收 5 问题：过关后前进按钮独立渲染、制卡 source_ref 兜底不丢弃、复习 hard 计入记住、欠账含 learning、复习日志时区统一 UTC | backend/app/models/db.py、services/tutor_service.py、frontend/src/views/Learn.vue、Review.vue
