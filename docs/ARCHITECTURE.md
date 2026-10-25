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

## 续开发：独立搜索与比赛演示

`CreateInvestigation.workflow` 为 `investigation`（默认）或 `search`。后者只执行一次元宝查询，不需要模型，不访问网页、不拆分声明、不生成原文证据，保存搜索及阶段报告后以 PARTIAL 结束。fixture 与 search 组合返回 422。完整真实调查分支继续保持缺模型就失败，不做伪模型降级。

两个分支共用 `Engine.search_query`：保存 provider、查询、intent、时间、原始 Response 和解析页；失败保存错误码，取消或超时保存 interrupted。HTTPX 超时/网络异常映射为稳定错误码，不泄露异常中的凭证或消息。`GET /health.search_history` 是历史尝试/成功数，不是免费额度、不保证当前凭证有效。Markdown 增加检索审计段。

`POST /extract-image` 接收最大 5 MB 的 PNG/JPEG/WebP data URL，检查格式及文件签名，传给用户配置的图片模型并结构化转录文字，交给用户编辑后再发起任务。当前未凭图片模型实测；接口不保存图片，不作事实判断，模型不支持或缺凭证时明确报错。

`demo_cases.py` 固定四个虚构案例；无真实 RequestId、无占位网页截图、最终仍为 INSUFFICIENT。前端 `search-trail.tsx` 展示搜索记录与原始返回，并提供基于已存 claim/evidence/source 绑定的简易引用图。图中引用实线只表示记录绑定，不表示独立性或现实传播关系。

关注列表仅将任务 ID 保存到当前浏览器 localStorage；“重新核验”填入新任务表单，由用户手动发起。通知从现有任务列表读取，非后台推送。当前用户入口是本地工作空间设置，未实现身份验证或计费订阅。

## 完整闭环版本：显式复核与取证 v2

本节更新上文的早期限制。DeepSeek 已通过真实结构化输出调用；专用配置为 `LLM_BASE_URL=https://api.deepseek.com`、`LLM_MODEL=deepseek-flash`。采用官方 JSON 格式，对 DeepSeek 使用 `max_tokens` 和关闭思考的参数，其他兼容服务继续使用各自的兼容参数。密钥仅保存在忽略跟踪的 `.env`。

### 取证边界

早期 v1 通过 Playwright route 返回重定向时，后续主文档可能由 Chromium 自行请求，最终审计发现部分最终文档没有固定连接记录。该方案已撤回，不再作为安全验收依据。

v2 先由 HTTPX 手动处理最多六跳请求，**每一跳**都重新核对 HTTPS、无用户名密码、443、域名允许列表和公网 IP；连接 URL 为该公网 IP，Host 和 TLS SNI 保持原始域名，证书验证不关闭。可选固定 Cloudflare HTTPS DNS 解析处理本地 fake-IP，不允许把保留地址当公网。每次响应最多4 MB。

Playwright context 设置 `offline=True`、禁用 JS/ServiceWorker，只有已校验的 HTTP 响应可被 route.fulfill 交给浏览器。导航使用已校验的最终 URL；非预期导航拒绝，资源的重定向同样由受控传输处理。静态资源先在有限预算内预取，渲染阶段路由只返回缓存字节；资源预算最多40个、三层、12 MB/12秒。浏览器不在路由中发起外部异步请求，关闭前解除路由。实际原文与截图仍来自真实响应，但受脚本禁用、资源域名限制和字体加载影响，截图可能存在不完整渲染，不能以“有截图”代替阅读正文。旧 v1 快照不能通过新的复核门槛。

### 证据与裁决

`model_run` 保存请求 ID、模型、用量、结构化输出、输入哈希及原始响应。模型拆解保持原消息，不擅自纠正；候选来源必须来自元宝返回，不接受自造 ID，并预过滤不安全 URL。来源提议 `source_profile` 只是模型建议；出处引文与实际链接可定位不表示已经证明独立性。

`POST /investigations/{id}/review` 接收复核者、复核类型（manual/assistant）、所用报告 ID、出处依据原文、分组理由、证据相关性/时间/立场和每条声明的裁决方法。服务器验证所有关联与正文哈希，合并同机构域名、同出处组、同正文及已定位引用链。不同域名永远不会自动获得独立资格。

明确比较后，支持与反驳并存保留 CONFLICTED；至少两个经显式确认的独立出处组可形成有范围的支持/反驳裁决；`primary_document` 需要第一方文件和至少20字的适用范围，不能冒充两源独立核验；其他情况为 INSUFFICIENT。必须已执行成功的反证检索才允许开放实质裁决。复核不能由模型 JSON 直接触发，AI 操作者也需按实际角色留档。

报告追加 `revision`，复核、报告及完成事件在同一事务保存。过期报告 ID 返回409；COMPLETED 可经显式复核修订为更审慎的结论，全部历史保留。COMPLETED 表示流程已完成复核，不代表每条声明都已证明真伪。安全审计发现不可信取证可显式撤回旧结论为 PARTIAL，并保留撤回事件。

新增 `GET /investigations/{id}/snapshots/{snapshot_id}` 只返回属于本调查的原文记录。交叉验证工作台可比较来源、读取存档原文、查看网络及模型审计、切换真实截图并提交/修订复核。截图转录单独保存图像哈希与模型审计，不在审计文件中保留上传图片或密钥。

## 静态比赛发布分支

`data-client.ts`通过构建常量`NEXT_PUBLIC_SHOWCASE`选择公开版适配器。默认本机模式仍调用原FastAPI及SSE；公开模式只读固定`/showcase`资源，固定fixture存localStorage，所有真实创建、图片识别和复核写入拒绝。`CrossCheck`在公开模式隐藏编辑表单，截图与Markdown指向同源静态文件。`export-showcase.py`仅对白名单任务及字段做显式导出；本机原始模型/网络日志留档，公开界面说明省略范围。`overview.tsx`按实际任务创建日期绘图，真实与fixture分别统计；COMPLETED仍表示复核过程完成，允许INSUFFICIENT。`next.config.ts`开启静态导出，EdgeOne只托管构建产物；服务密钥从不进入公开配置。

## EdgeOne 云端适配 · 2026-10-25

`cloud-functions/api/[[default]].js` 处理签名 Cookie、同源校验及短 API 转发；`agents/truthhunter/rpc.py` 校验工作空间令牌，复用 FastAPI、调查引擎和核验规则。任务通过独立长请求运行，前端用轮询替代 SSE；本机仍使用原 SSE。`context.store.state` 分任务保存记录、事件和截图，隔离不同浏览器工作空间；内存缓存不作为唯一持久层。回收不自动重放付费调用。

`scripts/prepare-edgeone.py` 仅复制显式源文件和公开前端，将 Playwright 驱动留在 Sandbox，避免 Agent 包超限。Sandbox 内使用与平台 SDK 相同的认证本地 CDP 端点连接 Chromium；该端点仅为受信浏览器控制通道，证据来源必须通过原 v2 公网传输检查。服务端配置使用 YUANBAO_API_KEY 别名，凭证和 CDP 令牌不写入业务响应或持久化状态。

静态 SHOWCASE 分支继续保留用于离线展示；正式 CLOUD 分支允许自由提问、真实搜索、模型调用、取证和显式复核，同时合并只读历史公开案例。两者是不同构建，不能把离线模式的禁用行为当成云端限制。
