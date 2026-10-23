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
