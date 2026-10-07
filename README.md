# dsh_tav

让 [dsh-NextTavern](https://github.com/a86582751/dsh-nexttavern) 跑在 **它官方并未支持的 dsh 宿主版本**上（已在 `0.2.1-alpha.1` 实测通过）。

官方 README 原话：「本版未承诺 Git 源码直装，也未扩展到 DSH 0.2／desktop」。
插件把 79 个 `@deepseek-ai/*` 依赖精确锁在 `0.1.7-rc.2`，宿主一升级，安装期就过不去。

本仓库不改一行插件代码——只把版本约束重映射掉，并处理一个已被宿主移除的包。

## 为什么改元数据就够了

NextTavern 几乎不直接 import 宿主：整个 `lib/` 里只有 `cordis`、`cordis-plugin-loader`、
`dsh-atomic-write` 三个静态 import，其余能力全靠 Cordis 容器**按服务名注入**。
所以跨宿主版本的兼容性取决于「服务在不在」，而不是「符号签名变没变」。

实测比对 `0.1.7-rc.2` → `0.2.1-alpha.1`：

| 检查项 | 结果 |
| --- | --- |
| `dsh-tools` / `dsh-agent` 导出符号 | 124→121、35→32，少的只是 cordis 插件声明，别名级一致 |
| `dsh-session-format` / `dsh-client-ui-slots` | 导出完全一致 |
| 浏览器端 8 个注入点 | 全部存在 |
| 会话格式 | 仍是 V3→V4，**没有 V5**，与插件支持的 Session V4 对齐 |
| 宿主 Cordis | `4.0.4` → `4.0.5-alpha.1` |

唯一的实质差异：`@deepseek-ai/dsh-invariants` 这个包在 0.2.x 里被删了，
而插件把它声明为必需 peer（虽然代码里 grep 不到任何引用）。

## 快速开始

需要 Node **24+**、pnpm 在 PATH。安装会写入一个独立 profile，**不碰你现有的 `web`**。

```powershell
git clone https://github.com/<your-name>/dsh_tav.git
cd dsh_tav\scripts
.\install.ps1 -ProfileName tavern -Port 3096
```

脚本会依次做完：探测宿主版本 → 打补丁 → 装包 → 补 stub 与 junction → 授予宿主版本豁免 → 启动。

手动分步请见 [`ADAPTATION.md`](ADAPTATION.md)。

## 实测结果（2026-10-07，dsh 0.2.1-alpha.1）

用真实 Chrome 跑完整流程，**全程 0 个 console 错误**：

| 步骤 | 结果 |
| --- | --- |
| 打开首页 | 侧边栏出现「酒馆管理」（class `dsh-rp-nav-entry`，插件注入） |
| 展开模式下拉 | 出现「NextTavern — 沉浸式长篇小说角色扮演工作台」 |
| 选中 NextTavern | 「酒馆管理」opacity `0.4 → 1`，渲染出 `dsh-rp-nav-icon` / `dsh-rp-status-toggle` |

未验证的部分：**真实故事生成**（需要自备模型 Key）。界面层之外的功能——
记忆检索、角色卡导入、世界书、分支导出等——按现状可用性未知。

## 仓库里有什么

| 路径 | 说明 |
| --- | --- |
| `scripts/patch.py` | 下载官方 tarball，把 peer 版本重映射到本机宿主版本，产出新的 tgz。自动探测宿主，不写死版本号 |
| `scripts/install.ps1` | Windows 一键安装（含 stub、junction、版本豁免） |
| `ADAPTATION.md` | 完整适配细节与踩过的 5 个坑 |

不打包含改后的 62MB 包——它是 GPL 二进制产物，自己跑脚本生成更干净。

## 已知限制

- 插件 fork 的 6 个宿主组件（`llm-pi-ai` / `session-controller` / `ui-chat` / `ui-workspace` /
  `token-meter` / `session-persistence-jsonl`）是照 `0.1.7-rc.2` fork 的，在 0.2.x 上只验到「能起来」。
- 上游明确不支持 0.2 系列，出问题没有官方支持，请到上游仓库提 issue 时注明你用了非官方适配。
- 每次 dsh 宿主升级，重跑一次 `patch.py` 即可；脚本会重新探测版本。

## 许可证

GPL-3.0-only，与上游一致（见 [`LICENSE`](LICENSE)）。
本仓库只做版本约束层面的适配，未修改上游代码的逻辑；所有权利归上游作者。
