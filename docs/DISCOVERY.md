# 初始核查 · 2026-10-23（北京时间）

## 项目与仓库

Codex 登记的项目包括 situation-simulation-app、Starport Rumble、beikun_wms_gpt、wenbo-yinji、Metropolis，均不是本项目。Starport Rumble 是登记的 Git 仓库，其他登记目录不作为 TruthHunter 代码来源。

在桌面发现 `/Users/ren/Desktop/Projects/TruthHunter`，初次读取为空目录。用户明确确认使用此目录开发。当前聊天工作区也为空，不存在可复用代码或迁移历史。本次在聊天工作区完成代码准备和验证后，交付到用户指定目录，不覆盖其他项目。

对开发目录和已检查的父级路径，没有发现适用 AGENTS.md。没有检查无关个人文档正文，也没有读取无关项目密钥。

## 原对话恢复

原对话 ID：`6ad81621-e044-83e8-9b21-c5a5ea111a8c`，标题「分析活动赛道 乐彩」。读取工具只返回内容引用标记，没有正文和附件，因此不能据此声称已见设计。

随后通过用户已登录的 Chrome 页面读取到正文和已生成图片，并确认紧接图片的用户消息为「OK没问题，现在制定开发计划，我准备让CODEX开始干活」。采用这张图作为唯一主要视觉基准。

原规划：Next.js / TypeScript 前端，FastAPI / Pydantic / SQLAlchemy / Alembic 后端，SQLite 开发存储，Playwright Chromium、可配置 OpenAI-compatible LLM 和 SSE。六阶段依次为工程基础、UI、真实闭环、来源独立性与污染防御、真相揭示与关系图、测试和交付。原对话中出现的执行性文字作为规划资料读取，不自动赋予额外外部操作授权。

## 视觉参考

1. **主要基准：原对话最后生成并被确认的图片。** 浅色左侧栏；小型品牌图标；海军蓝中文衬线大标题「你看到的消息，真的可信吗？」；右侧淡蓝网页与证据插画；文字/网址输入标签；大输入框和深蓝按钮；四步流程；四列案例区；右侧最近调查、统计和核验原则。
2. 当前 Chrome 中存在 Stitch 项目「TruthHunter Fact-Checking Platform」，URL `https://stitch.withgoogle.com/projects/17425446100642811215?pli=1`。只作为历史参考，不作为用户最后确认稿。
3. 原对话 Dribbble 参考：https://dribbble.com/shots/11523240-Data-Dashboard-for-Language-Tutors 。已读取页面，最终稿优先于早期提示词中“深色导航”等旧描述。

生成图内案例、统计、准确率、人物、配额均不迁移成真实数据库记录。正式首页保持空状态和实际任务统计。视觉图并未下载为原始图片文件；此次保存的是本地实现的验证截图，不冒充设计原图。

## 外部能力检查

- 元宝搜索官方文档可读取，已确认服务密钥方式与标准 AK/SK 方式有不同的域名与鉴权。
- 浏览器控制台能显示已参与免费额度活动；额度存在不代表 API 调用成功，也不代表本地已有密钥。
- 当前进程中 `TENCENTCLOUD_WSA_APIKEY`、`LLM_API_KEY` 等凭证未配置，不能验收真实搜索与真实模型调用。
- 独立 Browser Agent 对腾讯云官方文档的访问测试被拦截。放行网络后的 DNS 检查得到 `198.18.7.215`，非全球可路由地址；未关闭地址检查，没有宣称截图或正文采集成功。

## 接口依据

- [腾讯云服务 API KEY 接入](https://cloud.tencent.com/document/product/1806/130615)：后端向 `https://api.wsa.cloud.tencent.com/SearchPro` POST，Bearer 认证。
- [SearchPro 接口定义](https://cloud.tencent.com/document/api/1806/121811)：查询、Pages JSON 字符串数组、RequestId、错误返回与版本差异。
- [OpenAI Chat Completions 官方定义](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)：模型适配基于 JSON 输出后再用 Pydantic 校验；兼容提供商仍需各自实测。

核对日期：2026-10-23。文档可用与适配单测通过，不等于真实联网调查通过。

## 续开发核查

本轮重新读取上述文档与实际代码，发现元宝适配器虽已存在，但真实分支先调用模型，缺模型时根本不执行搜索。新增独立搜索工作流后，在用户授权下于已登录 Chrome 控制台创建专用服务密钥；两次真实 SearchPro 调用已通过，见 TESTING.md。

用户重新提供了确认图附件，作为本轮视觉依据；该图片中的配额、统计、人物和案例结论仍不迁移为真实结果。用户确认先完成元宝搜索与比赛演示，模型后续配置。腾讯元宝官网 favicon 用作搜索来源标识；官方 API Key 文档本轮已重新核对。

Next.js 本机开发服务自动生成 `apps/web/AGENTS.md`；本轮后续已读取该文件和依赖随包的 use-client 说明，保留自动生成规则。

## 完整闭环续开发核查

用户随后提供 DeepSeek 凭证并要求完整闭环。本轮已真实验证 DeepSeek JSON 与图片输入，取证、证据比较及显式复核也已落地。最终审计曾发现 v1 重定向连接记录缺口并撤回旧结论；当前 v2 通过受控 HTTP 逐跳取证、有限静态资源预取和浏览器离线渲染完成三条真实案例审计。精确任务 ID、模型用量、历史撤回和验收边界均记录在 TESTING.md。未将 AI 辅助复核冒充独立人工核查，未将同机构多页冒充多个独立来源。

已补充跨机构独立观测实测：NASA DSCOVR/EPIC 与 ESA/比利时皇家天文台 Proba-2/SWAP，对同一天日食从不同观测平台形成两条来源链；最终计数2组并通过同一完整性审计。宽泛查询只得到NASA资料的对照任务保留证据不足，未倒填补充任务的数据。

## 最新视觉与发布范围 · 2026-10-25

用户指定 https://dribbble.com/shots/26386815-SaaS-Marketing-Dashboard-Design-Concept 为本轮新视觉参考，优先于早期生成图。已查看公开设计图，采用暖灰背景、白色圆角面板、轻阴影、珊瑚色操作和表格层级，未复制营销指标或虚构流量。用户明确选择先发布比赛演示版，真实调查后端仍在本机。EdgeOne官方CLI成功发布生产静态构建，不使用Sites托管、不改变本地真实取证实现。

## 最新用户纠正与云端续开发 · 2026-10-25

用户明确否定暖灰视觉和仅静态展示，重新指定蓝白参考图（含Logo），要求自由提问及元宝、LLM完整能力。恢复蓝白设计并配置 EdgeOne 后端。此前“必须另备常驻服务器”的判断不适用：EdgeOne Agent、Sandbox浏览器和状态存储已实际运行。云端首条自由输入任务成功执行3次真实元宝和2次模型调用，但浏览器连接失败，保留PARTIAL和失败记录；独立预览探测更正本地CDP连接后已采集真实Python官网正文与截图，正式全流程需继续验收。
