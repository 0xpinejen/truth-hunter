# EdgeOne 云端版 · 2026-10-25

用户最新要求恢复原蓝白参考图，并开放自由提问及真实搜索、模型调用。EdgeOne 可承接本项目后端，无须为比赛另购常驻服务器。当前采用静态前端＋Cloud Functions 会话网关＋长时 Makers Agent＋Sandbox Chromium＋会话 Blob 状态存储。此前纯静态发布限制保留在下方历史记录，已不代表当前模式。

## 构建与发布

```sh
npm --prefix apps/web ci
npm --prefix apps/web run build:cloud
python3 scripts/prepare-edgeone.py
npx edgeone makers deploy artifacts/edgeone-release --name truthhunter-20-demo --env production --area overseas --skip-ai-gateway-sync
```

仅上传显式生成的 `artifacts/edgeone-release`，不上传 `.env`、本机数据库、凭证目录或整个工作区。根目录 edgeone.json/package.json 同时提供 Git 构建入口，但当前实际验收使用官方 CLI 直接上传，未建立 Git 自动部署。

服务端 production 环境配置：`YUANBAO_API_KEY`、`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`、随机 `TH_SESSION_SECRET`、正式域名 `TH_PUBLIC_ORIGIN`、`BROWSER_DNS_MODE=doh`、`BROWSER_ALLOW_PUBLIC_WEB=true`。这些值不能加 NEXT_PUBLIC_ 前缀。腾讯云函数保留 TENCENTCLOUD_ 前缀，生产环境必须使用 YUANBAO_API_KEY 别名；Python 进程内再映射到原适配器名称。本机 .env 继续用原字段。

## 会话和运行边界

网关发放 HttpOnly、Secure、SameSite=Lax 签名 Cookie，并签发一小时 Agent 请求令牌；服务端校验 workspace ID、签名、有效期和写入来源。私有任务、原文、截图在会话状态中保存；公开四例始终只读。浏览器会话不是实名账号，清理 Cookie 会失去该工作空间入口，不保证跨设备访问。匿名工作空间限制每天20项真实任务、最多40项档案和两项并发；尚无覆盖所有访问者的全局费用预算或完整生产账户系统。

长任务直接调用300秒 Agent，前端轮询进展，避免120秒网关上限。每1.5秒保存变化记录，进程回收后恢复已存记录；未结束任务保留部分报告，不自动重放付费请求。Sandbox 用平台认证的本地 CDP 连接 Chromium；证据仍逐跳验证公开 HTTPS、公网 IP、Host/TLS，渲染时离线，不允许浏览器访问任意内网。

当前正式生产部署：`dpdsh2l6anmm`；核心真实调查和图片转录已实测，任务与测试详情见TESTING.md。

## 历史静态发布记录（已被云端模式替代）

# EdgeOne 比赛演示版

2026-10-25 视觉更新参考 [Conceptzilla SaaS Marketing Dashboard](https://dribbble.com/shots/26386815-SaaS-Marketing-Dashboard-Design-Concept)：暖灰背景、白色浮层、细分隔线、紧凑表格和珊瑚色主操作。趋势图按真实档案及浏览器演示任务的创建日期生成，无模拟流量、准确率或额度。

## 公开版与本机版

公开版通过 `NEXT_PUBLIC_SHOWCASE=true` 构建为静态页面，不调用本机地址、元宝或模型。四条经审核的公开案例保留原始日期、报告版本、逐字引文、来源截图和 AI 辅助复核标识；不是当前新调查，也不冒充独立人工事实核查。完整模型输入、原始接口返回、网络日志、其他任务、数据库及密钥不公开。网页中的审计说明注明该裁剪范围。

四个虚构案例在访问者浏览器中生成并保存，维持 `fixture`、`INSUFFICIENT` 和无真实截图/RequestId 的边界；最多保存30项，存储失败明确报错。浏览器关注列表不构成定时追踪。公开档案不能提交或修订复核。新增真实核验、截图识别继续使用本机版。

## 构建与上传

```sh
npm --prefix apps/web ci
npm --prefix apps/web run test:showcase
npm --prefix apps/web run build:showcase
npx edgeone login
npx edgeone makers deploy apps/web/out --name truthhunter-20-demo --area overseas --skip-ai-gateway-sync
```

上传目录只能是 `apps/web/out`，不要上传仓库根目录、`.env`、`apps/api/data` 或 `apps/api/artifacts`。`--skip-ai-gateway-sync` 防止为纯静态站点同步不需要的模型凭证。

本次使用 EdgeOne 官方 CLI 将已验证构建直接上传；无需授予 EdgeOne 访问私人 Git 仓库的额外权限。若以后改用用户提供的 [Git 导入流程](https://pages.edgeone.ai/zh/document/importing-a-git-repository)，仓库根目录 `edgeone.json` 已提供构建命令与输出目录，导入时使用根目录并设置相同参数，不配置任何搜索或模型密钥。Git 模式与直接上传是不同项目类型，需要另建 Git 导入项目；不要声称本次已建立 Git 自动部署。

本机重新准备经过批准的四份公开案例时，可运行 `.venv/bin/python scripts/export-showcase.py`。该脚本只读取固定四个验收任务 ID，并通过字段白名单导出；新机器使用已提交的公开节选即可构建，不需要本地数据库。不得扩大为全库导出。

## 本机真实服务

未设置 `NEXT_PUBLIC_SHOWCASE=true` 时仍使用原 FastAPI 服务；按 README 启动两个服务。不要把未鉴权的本机后端开放公网。静态站点发布不代表真实调查后端已上线。

## 本次已验证部署

- 地址：https://truthhunter-20-demo-hooqvhsf.edgeone.dev
- 项目：`makers-5lwh2fqnuzhv`；生产部署：`dpnbzsz1cpw2`。
- 官方CLI返回成功；正式HTTPS页面、真实报告/截图、虚构案例及刷新恢复通过；47份线上静态文件与本地构建逐字节一致。
