# TruthHunter 2.0 · 真相猎手

别急着相信，先看看证据。

本地分阶段开发版本。已实现可运行的首页、调查室、事件存储、演示闭环、报告与档案。真实元宝搜索与模型适配代码已实现，但尚未凭真实凭证验收。来源独立性复核尚未实现，因此真实任务不会自动给出已核实的事实裁决。

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
cp .env.example .env
```

在本地编辑 `.env`，填入 `TENCENTCLOUD_WSA_APIKEY`、`LLM_API_KEY`、`LLM_MODEL`，根据模型提供商设置 `LLM_BASE_URL`。不要把密钥发到聊天或提交 Git。浏览器只访问 `BROWSER_ALLOWED_DOMAINS` 显式允许的公开 HTTPS 域名。

两个终端分别运行：

```sh
sh scripts/dev-api.sh
```

```sh
sh scripts/dev-web.sh
```

打开 http://127.0.0.1:3000。无需凭证也可点击「运行演示」，该操作只使用虚构资料，并在任务、事件、报告中标明。缺少凭证的真实任务必须失败，不会降级为假成功。

## 验证

```sh
sh scripts/test.sh
```

仅当网络 DNS 返回公网地址时，执行独立的真实浏览器检查：

```sh
BROWSER_ALLOWED_DOMAINS=cloud.tencent.com .venv/bin/python scripts/browser-smoke.py
```

该检查不是事实核验案例。执行结果、截图和文本位于忽略跟踪的 `artifacts/`。本次检查被非公网 DNS 解析拦截，未生成成功记录。

## 工程状态

- [执行里程碑与验收矩阵](docs/MILESTONES.md)
- [仓库、对话与视觉核查](docs/DISCOVERY.md)
- [测试结果](docs/TESTING.md)
- [架构](docs/ARCHITECTURE.md)
- [产品与视觉基准](docs/PRODUCT.md)
- [安全边界与待解决问题](docs/SECURITY.md)
- [演示与真实案例验收](docs/DEMO.md)

当前仅适合本机开发；未实现用户身份验证，不要开放到公网。持续追踪、交互式传播关系图、PDF、长图分享、完整来源独立性审核属于后续阶段。
