# dsh-nexttavern 0.2.9 → dsh 0.2.1-alpha.1 适配说明

验证状态：**浏览器实测已通过**（见下方实测记录）。
仍未验证的只有一件事：真实故事生成（需要配模型 Key 后实际跑一轮）。

## 浏览器实测记录（2026-10-07）

用系统 Chrome（playwright-core 驱动）实打实打开，全程 **0 个 console 错误**：

| 步骤 | 结果 |
| --- | --- |
| 打开首页 | 标题 `DeepSeek Harness`，侧边栏出现 **「酒馆管理」**（class `dsh-rp-nav-entry`，插件注入） |
| 新建会话 | 正常 |
| 展开模式下拉 | 列表里出现 **「NextTavern — 沉浸式长篇小说角色扮演工作台」**，与标准/PTC/极简/创造并列 |
| 选中 NextTavern | 「酒馆管理」opacity `0.4 → 1`（由灰态转为可用），渲染出 `dsh-rp-nav-icon` / `dsh-rp-nav-label` / `dsh-rp-status-toggle` |

即：插件的侧栏入口、模式预设、状态栏开关在 0.2.1-alpha.1 上**都活了**。

### 实测踩到的两个环境坑

- 服务必须先退出才会 flush 日志，所以 **token 要等 1～3 分钟**才出现在日志里；没 token 访问返回 401/303。
- 沙箱里 `curl 127.0.0.1` 会被代理拦成 502/000，**不是服务没起来**；用 socket 直连或浏览器加 `--no-proxy-server` 验证。
- 端口被上一次残留进程占用会级联：webserver `EADDRINUSE` → connection/webRuntime/fileUploads 全 pending → session-controller 不激活 → 插件报 `enabled entry is not active`。换端口即可。

## 适配了什么

代码逻辑一行未改，只做了三件事：

| 项 | 原始值 | 改为 | 原因 |
| --- | --- | --- | --- |
| 79 个 peerDependencies | `0.1.7-rc.2` / cordis `4.0.4` 等 | `0.2.1-alpha.1` / cordis `4.0.5-alpha.1` 等 | 宿主整条版本线变了 |
| `@deepseek-ai/dsh-invariants` | 必需 peer | `peerDependenciesMeta.optional = true` | 该包在 0.2.1 已被移除，插件代码从未 import 它 |
| 版本号 | 保持 `0.2.9` | **不要改** | 改了会触发 `Bundled dependency inventory does not match` |

### 不能碰的地方

- **9 个 `dsh-nexttavern-*` 子包的 package.json 全都在受保护清单内**，
  改了会报 `Protected package hash differs`。它们声明的旧版本号不影响运行——
  插件的 peer 校验只比对**解析出的真实路径**，不比对版本字符串。
- `nexttavern.dependencies.json` 里的 `productVersion` 必须与主包 version 一致。

## 安装步骤

前置：Node **24+**（本机 `D:\Node js`），pnpm 已在 PATH。

```bash
# 0. Node 24
export PATH="/d/Node js:$PATH"

# 1. 装到独立 profile（不要动已有的 web）
dsh plugin --profile tavern021 add "file:///C:/Users/admin/WorkBuddy/2026-10-07-14-36-16/nt/dsh-nexttavern-0.2.9-dsh021.tgz"

# 2. profile 的 bundles 必须包含宿主 web-app，否则插件要禁用的 UI 条目找不到
#    ~/.dsh/profiles/tavern021/package.json:
#    "bundles": ["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app", "dsh-nexttavern"]

# 3. 补 dsh-invariants stub（宿主目录放实体，profile 用 junction 指过去，
#    两边 realpath 必须一致，否则报 "uses a different host peer"）
#    宿主: <npm全局>/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-invariants/
#    profile: ~/.dsh/profiles/tavern021/node_modules/@deepseek-ai/dsh-invariants  ->  junction

# 4. 宿主的版本豁免
dsh plugin --profile tavern021 allow-version "dsh-nexttavern-presets@0.3.0-dev.1" \
  --dsh-version 0.2.1-alpha.1 --accept-risk

# 5. 启动
dsh --profile tavern021 --host 127.0.0.1 --port 3099
```

## 排查过的坑（按遇到顺序）

1. `Bundled dependency inventory does not match` —— 版本号被我改成 `0.2.9-compat.1`，还原成 `0.2.9` 即可。
2. `patch: entry "ui-chat" not found` —— 新建的空 profile 只有 `dsh-base`，缺 `dsh-web-app` bundle，不是适配问题。
3. `No package metadata for peer: @deepseek-ai/dsh-invariants` —— 0.2.1 移除了该包，用 stub 补。
4. `Protected package hash differs` —— 改了受保护子包的 package.json，用原始 tarball 还原。
5. `disabling ... dsh-nexttavern-presets@0.3.0-dev.1 is incompatible` —— 宿主自带的版本豁免开关，官方支持。

## 遗留风险

- 插件 fork 的 6 个宿主组件（llm-pi-ai / session-controller / ui-chat / ui-workspace / token-meter / session-persistence-jsonl）
  是照 0.1.7-rc.2 fork 的，在 0.2.1 上未做功能级验证。
- 会话格式两边都是 V4，理论可通，但未实测导入旧会话。
- 作者明确声明未扩展到 DSH 0.2，出问题无官方支持。
