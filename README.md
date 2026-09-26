# Project Taskboard (项目任务看板)

通用且运行时无关的本地项目任务看板，原生支持 [Superpowers](https://github.com/obra/superpowers) 计划体系与多 Agent 协同。

无需依赖特定 PM Session 或中心化管理平台，可自动从项目的实施计划（`docs/superpowers/plans/*.md`）提取任务层级与步骤，并在文件修改时自动热重载同步；同时提供本地 REST API 支持任意 Agent（Codex、OpenCode、Claude 等）幂等上报当前执行状态。

---

## 核心特性

- **零手工录入与自动发现**：自动扫描项目下的 `docs/superpowers/plans/*.md` 文件，自动提取 `### Task N` 作为执行任务，提取 `- [ ] **Step N**` 作为展开层级，自动计算任务总数与分母。
- **计划状态自动监听**：服务后台监听计划文件变动，计划中的复选框（`- [x]`）勾选后自动将任务状态推进为 `done` 并记录完成时间戳。
- **多运行时 Agent 状态汇报**：支持任意 Agent 在开始/结束任务时通过本地 HTTP API 提交 `in_progress`、`current_step`、`blocked` 等状态，支持幂等更新。
- **项目全景可视化看板**：
  - 顶部水平阶段轨道（规划推进与状态圆点统计）；
  - 左侧层级拓扑连线图（按真实 `parent_id` 动态展开任意深度，阶段 → 模块 → 任务 → 步骤只是常见示例）；
  - 右侧任务详情面板（三阶段状态、起止时间进度、规格依据链接、验收要点）；
  - 底部“正在执行”任务实时表格，支持点击一键高亮定位节点。
- **开箱即用与零外部依赖**：服务端纯 Python 3 标准库实现，前端纯原生 HTML/CSS/JS，无第三方包依赖。

---

## 快速上手

### 1. 从项目计划初始化看板

```bash
python3 scripts/taskboard.py init   --root ./project-dashboard   --project-root /path/to/your/project   --project "你的项目名称"
```

### 2. 启动看板服务与计划文件监听

```bash
python3 scripts/taskboard.py start   --root ./project-dashboard   --project-root /path/to/your/project
```

服务默认监听 `http://127.0.0.1:47832/`，打开浏览器即可查看。

---

## 作为 Agent 技能安装

### Codex
复制或链接到 `~/.codex/skills/project-taskboard`。

### OpenCode
复制或链接到 `~/.config/opencode/skills/project-taskboard`。

---

## 同步到 AgentWiki 服务端

看板可以整体托管到 AgentWiki（每个 Space 一块看板）。**已连接 AgentWiki MCP 的 Agent 无需重复配置服务器或密钥**：调用 `list_spaces` 选定项目 Space，以 `get_taskboard` 读取看板、`import_taskboard_plans` 批量导入本地文件内容、`update_taskboard_status` 上报状态。多个 Space 时先确定项目映射。需要 AgentWiki v0.12.9+，升级后刷新/重连 MCP 工具列表。

批量导入每次最多 20 个文件 / 2 MB 内容，按文件提交并报告结果；失败项单独处理，默认保留远程状态。完整流程与稳定来源约定见 [SKILL.md](SKILL.md#agentwiki-远程同步)。

只有不使用 MCP 的独立 CLI 才需要配置环境变量：

```bash
export AGENTWIKI_URL="https://agentwiki.quukk.com"
export AGENTWIKI_SPACE_ID="<空间 ID>"
export AGENTWIKI_AGENT_KEY="agk_..."   # Agent 密钥（需该 Space 的 editor 授权）

python3 scripts/taskboard.py push --project-root .                 # 推送全部计划
python3 scripts/taskboard.py report 1 in_progress --step "写测试"  # 上报状态
```

推送为幂等合并（保留远程执行状态），`--sync-status` 按计划勾选推进状态但不覆盖 blocked/in_review/canceled。

### 多 Agent 协作同一块看板

AgentWiki 看板按 Space 共享：多个 Agent 各持自己的 `agk_` 密钥并拥有该 Space 的 editor 授权后，即可共同读写同一块板。协作规则：

- 任务进入 `in_progress`/`in_review`/`done` 时自动认领给当前 Agent；他人认领的任务直接上报会被拒绝，需显式 `takeover`。
- `depends_on` 中的任务未全部完成前，任务无法进入 `in_progress`。
- 每次变更记录操作者（状态历史 + 事件流），看板页通过 Socket 实时刷新，多端看到同一进度。

Agent 端通过 MCP 上报执行状态；独立 CLI 使用 `report`。计划变更默认合并规划，只有明确要求按勾选同步进度时使用 `syncStatus:true` 或 `push --sync-status`。

### 从 AgentWiki 页面导入计划

计划可以存为 AgentWiki 空间内的 Markdown 页面，服务端直接读取页面内容，无需本地文件：网页导入对话框选「空间页面」，或推送时用 `pageId`（调用 `/import-plan` 传 `{"pageId": "..."}`）。同一页面的重复导入按 `agentwiki-page:<id>` 稳定对齐任务 ID。

## License

MIT
