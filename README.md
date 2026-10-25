# TruthHunter 2.0 · 真相猎手

别急着相信，先看看证据。

本地分阶段开发版本。已实现可运行的首页、调查室、事件存储、演示闭环、报告与档案。腾讯元宝搜索与 DeepSeek 已真实接通。真实调查经过检索、受控网页取证、逐字引文、模型提议和显式复核，生成可追溯的版本化报告。模型不能自行形成最终事实裁决；复核可保留证据不足。

## 在线云端版 · 2026-10-25

地址：[TruthHunter 2.0 · EdgeOne](https://truthhunter-20-demo-hooqvhsf.edgeone.dev)。按最新确认图恢复蓝白工作台、深蓝主操作和品牌 Logo。公开站点现使用 EdgeOne Cloud Functions、Makers Agents、Sandbox Chromium 和会话存储执行真实元宝搜索与 DeepSeek 分析，支持自由提问；四份历史公开报告保持只读，虚构案例持续标注。一条云端真实调查已完成3次检索、3份网页快照、3条逐字引文、显式AI辅助复核和报告下载；图片转录也已实测。详细结果见 TESTING.md，不以密钥已配置代表验收通过。

[部署配置与边界](docs/DEPLOYMENT.md) · [测试记录](docs/TESTING.md)

## 本地启动

要求：Python 3.11+、Node.js 20.9+（本次验证使用本机 Python 3.14 与已有 Node）。

```sh
cd /Users/ren/Desktop/Projects/TruthHunter
python3 -m venv .venv
.venv/bin/python -m pip install -r apps/api/requirements.lock
.venv/bin/python -m playwright install chromium
cd apps/web
npm ci
cd ../..
cp -n .env.example .env
```

在本地编辑 `.env`，填入 `TENCENTCLOUD_WSA_APIKEY`、`LLM_API_KEY`、`LLM_MODEL`，根据模型提供商设置 `LLM_BASE_URL`。不要把密钥发到聊天或提交 Git。浏览器只访问 `BROWSER_ALLOWED_DOMAINS` 显式允许的公开 HTTPS 域名。

两个终端分别运行：

```sh
sh scripts/dev-api.sh
```

```sh
sh scripts/dev-web.sh
```

打开 http://127.0.0.1:3000。元宝密钥已在本机配置时，可直接点击「开始搜索」或「仅搜索线索」，不依赖语言模型；每次仅执行一次真实搜索，结果保留为 PARTIAL，不计为完成核验。

无需凭证也可点击「运行演示」，该操作只使用虚构资料，并在任务、事件、报告中标明。缺少凭证的真实任务必须失败，不会降级为假成功。

## 验证

```sh
sh scripts/test.sh
```

仅当网络 DNS 返回公网地址时，执行独立的真实浏览器检查：

```sh
BROWSER_ALLOWED_DOMAINS=cloud.tencent.com .venv/bin/python scripts/browser-smoke.py
```

该检查不是事实核验案例。执行结果、截图和文本位于忽略跟踪的 `artifacts/`。本机使用可选的 HTTPS DNS 解析获取公网 IP。v2 取证逐跳处理重定向、固定公网连接并校验证书；浏览器离线渲染实际响应，保存原文和截图。系统 DNS 模式仍会拒绝 fake-IP。

## 工程状态

- [执行里程碑与验收矩阵](docs/MILESTONES.md)
- [仓库、对话与视觉核查](docs/DISCOVERY.md)
- [测试结果](docs/TESTING.md)
- [架构](docs/ARCHITECTURE.md)
- [产品与视觉基准](docs/PRODUCT.md)
- [安全边界与待解决问题](docs/SECURITY.md)
- [演示与真实案例验收](docs/DEMO.md)

本机原始 FastAPI 不带公网鉴权，不能直接开放；云端版使用签名浏览器会话隔离工作空间，尚无跨设备账号系统。本地关注列表、事件记录回放和声明—引文引用图已可体验；定时后台追踪、真实传播溯源图、PDF、长图分享、完整来源独立性审核属于后续阶段。

## 比赛演示版 · 本轮更新

- 首页参考确认图补齐元宝图标与来源标识、七类选题筛选、四个虚构演示案例、通知面板、本地用户入口和实际调用统计。未使用示意图中的假配额、准确率、人物身份和核验结论。
- 真实搜索：查询 → 元宝 SearchPro → RequestId / 原始返回持久化 → SSE → 页面线索 → Markdown。早期两次独立搜索每次返回 10 条线索。后续完整调查验收与取证重定向修复记录见 TESTING.md；不以检索成功代表事实正确。
- 调查页支持搜索审计、事件列表回放、引用绑定关系图；关注列表保存在当前浏览器，可手动重新核验，不自动运行付费请求。
- 截图上传通路已实现（PNG/JPEG/WebP，5 MB 上限），需要另行配置支持图片输入的语言模型；已用公开 Python 文档截图通过真实 DeepSeek 转录验收；首次结构校验失败保留记录，收紧为单条陈述后成功。
- 元宝图标取自[腾讯元宝官网](https://yuanbao.tencent.com/)的公开 favicon，仅标识搜索服务来源，不表示官方合作或背书。接入依据：[官方 API Key 文档](https://cloud.tencent.com/document/product/1806/130615)。

比赛讲解步骤见 [DEMO.md](docs/DEMO.md)，实际验收记录见 [TESTING.md](docs/TESTING.md)。

## 完整真实闭环

1. 提交一条明确声明（文字、网址或截图转录后确认）。
2. DeepSeek 拆解声明，腾讯元宝执行最多三次检索，含反证查询。
3. 在允许列表内选择原始资料；HTTPX 逐跳校验 HTTPS、域名、公网地址与 TLS 身份，浏览器离线渲染，避免浏览器自行跟随重定向。
4. 原文、最终 URL、每跳连接记录、截图、时间、SHA-256 和逐字引文留档；模型调用 ID、用量和原始输出同样留档。
5. 在交叉验证工作台审查出处组、相关性、时间和支持/反驳关系。两个经确认的独立组可按规则裁决；第一方文件只在明确定义的自身记载范围内裁决；缺证据保留 INSUFFICIENT。
6. 提交显式复核，生成新版本报告、完成事件和 Markdown。可修订，但旧报告和旧复核不删除。AI 辅助复核必须明确标注，不能冒充独立人工核查。

此版本仍是本机研究工具，未实现通用事实真伪的全自动保证或生产身份验证；已通过一条NASA与ESA不同仪器原始观测的独立核验案例，不能据此宣称所有领域都已验收。旧 v1 取证的三条试运行结论已因重定向连接记录缺口撤回；不能将这些历史报告作为当前验收成功资料。

最终四条主验收闭环（文件范围内反驳、文件范围内支持、证据不足、两条独立观测来源支持）及76项回归已通过；任务 ID 和完整性审计命令见 [TESTING.md](docs/TESTING.md)。
