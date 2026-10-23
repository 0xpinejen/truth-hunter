# 架构与数据契约

## 目录

```text
apps/web/                 Next.js App Router、TypeScript、中文界面、响应式 CSS
apps/api/truthhunter/     FastAPI、Pydantic、SQLAlchemy、调查编排与适配器
apps/api/alembic/         数据库版本迁移
apps/api/tests/           契约、核验规则、失败状态与 API 闭环测试
packages/shared/         前端状态类型及导出的 OpenAPI
docs/                    基准、里程碑、测试、演示、安全边界
scripts/                 启动、测试、独立浏览器检查
```

首轮用项目自己的 CSS 还原确认图，尚未引入 Tailwind/shadcn；不影响后端与 Provider 边界。React 当前用单页视图切换承接闭环，URL 深链接与大型组件拆分作为后续重构项。

## 调用链

浏览器 → FastAPI 创建调查 → SQLite 保存任务与事件 → 异步 Engine → LLM 拆分声明 → TencentYuanbaoSearchProvider 查询与反证查询 → BrowserAgent 只读访问 → 原文存档与逐字引文 → 模型提议/引用校验 → 审慎的阶段报告 → SSE/档案/Markdown。

本地 fixture 走明确的独立分支。它不调用元宝、模型或浏览器，不制造 RequestId，不生成浏览器占位截图。真实分支绝不自动回退到 fixture。

## 持久化

开发采用 SQLite + SQLAlchemy + Alembic。三张基础表：`investigations`、`records`、`events`。records 的 kind 区分 Claim、SearchRun、Source、Snapshot、Evidence、SourceRelationship、CaptureFailure、Report；Pydantic 校验模型输出，业务引用必须绑定同一调查中的声明和证据。

这是最小可运行持久化方案，尚未实现原规划全部实体的独立关系表、数据库级外键和唯一性规则。生产 PostgreSQL、Alembic 的后续规范化迁移、事务队列和多 worker 调度待实现；不可直接把当前进程内任务队列当成分布式执行引擎。

`Source.search_excerpt` 只是检索线索。`Snapshot.text`/`.sha256` 记录实际捕获正文。`Evidence` 绑定原文片段、Unicode 起止位置、最终 URL、抓取时间及正文哈希。正文被截断时标记 `truncated`。哈希只说明所存文本的一致性，不证明内容真实，不等于可信时间戳或司法存证。

## 状态与事件

主执行链：CREATED → PLANNING → SEARCHING → BROWSING → EXTRACTING → VERIFYING → REPORTING。允许为不同查询/页面重复搜索和浏览步骤。终态：COMPLETED / PARTIAL / FAILED / CANCELLED。一旦终态写入，迟到结果不得覆盖。SSE 使用持久化单调事件 ID，并接受 `Last-Event-ID`/`after` 游标重放。

取消会取消后台 task 并保存阶段报告。超时写 PARTIAL；无证据的执行错误写 FAILED；重启发现未结束任务会写 PARTIAL + PROCESS_RESTARTED，不自动重试付费 API。没有 durable worker，不保证进程被强制杀死时正在写入的外部文件完整。

## API

| 路径 | 行为 |
|---|---|
| GET /health | 连接配置是否存在，明确 connectivity=not_verified |
| POST /investigations | 创建 live 或预定义 fixture 任务 |
| GET /investigations | 本地档案列表 |
| GET /investigations/{id} | 任务、记录与事件 |
| POST /investigations/{id}/cancel | 取消调查，终态不覆盖 |
| GET /investigations/{id}/events | SSE，支持游标续传 |
| GET /investigations/{id}/report.md | 导出阶段报告，无报告返回 409 |
| GET /investigations/{id}/screenshots/{filename} | 只返回属于该调查的截图 |

## Provider

元宝服务密钥实现使用 `https://api.wsa.cloud.tencent.com/SearchPro`，只发送 `Query` 以兼容当前版本。HTTP 失败、Error 对象、缺 RequestId、错误 Pages JSON 不会视为成功。Query、开始结束时间、intent、原始返回和解析结果一起保存。默认无自动重试，避免隐性重复计费。标准 AK/SK 签名方式尚未实现。

可配置 LLM 通过 HTTPS Chat Completions JSON 输出，结果必须通过 Pydantic 校验。没有工具调用权限；网页材料作为不可信数据传入。当前没有模型请求/token/成本审计表，也未验证所有兼容供应商；需在开放真实并发前完善。

BrowserAgent 使用 Playwright Chromium、禁用 JS/ServiceWorker、限制 GET、域名允许列表与逐请求 DNS 公网检查。只读访问并截图，尚非能自主点击、表单操作或处理登录状态的通用浏览器智能体。
