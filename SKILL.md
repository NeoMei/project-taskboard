---
name: project-taskboard
description: Create, serve, validate, and update a local hierarchical project task board from Codex, OpenCode, or another agent runtime without requiring a PM session.
---

# 通用项目任务看板

当用户需要从规格、计划、任务清单或已有任务 JSON 生成一个可以持续更新的项目看板时使用本 Skill。它提供独立的本地数据文件、层级视图、状态和类型颜色、起止时间、正在执行列表，以及创建和更新任务的 HTTP 接口。

本 Skill 是运行时无关的：看板服务只依赖 Python 3 标准库和 HTTP，项目可以由 Codex、OpenCode 或其他能执行 shell/HTTP 请求的 agent 共同更新。PM Session 是可选的协调者，不是看板的前置条件。每个运行时只需要把本 Skill 安装到自己的 Skill 发现目录，所有 agent 再通过同一个项目看板 URL 写入同一份任务数据。

节点树不假定固定层数。画布根据 `parent_id` 的实际路径动态生成层级列；点击有子节点的卡片继续展开，面包屑可以回到任意祖先，叶节点显示为不可继续展开。深层路径会自动获得更宽的可滚动画布，避免把第 4 层、第 5 层或更深层级压缩到固定布局中。

## 本地看板流程（远程同步见下文）

1. 选择一个专用看板目录，不要直接覆盖已有项目目录。初始化空看板：

   ```bash
   python3 <project-taskboard-skill-dir>/scripts/taskboard.py init \
     --root /绝对路径/项目看板 \
     --project "项目名称"
   ```

   从已有任务 JSON 初始化时增加 `--input /绝对路径/tasks.json`。输入可以是任务数组，也可以是包含 `tasks` 数组的对象。使用 Superpowers 计划初始化时改用 `--plan /绝对路径/docs/superpowers/plans/YYYY-MM-DD-feature.md`；计划标题、`### Task N` 和每个任务下的 `Step N` 会自动形成层级。

   对完整 Superpowers 项目直接扫描标准计划目录，不需要手动列出任务或计划文件：

   ```bash
   python3 <project-taskboard-skill-dir>/scripts/taskboard.py init \
     --root /绝对路径/项目看板 \
     --project-root /绝对路径/项目目录 \
     --project "项目名称"
   ```

   未发现 Superpowers 计划时仍生成并启动空看板，页面说明暂无规划和任务，不虚构示例任务，也不将空任务集合视为项目已完成。后续新增计划会自动同步；也可导入任务 JSON 或通过 API 添加任务。未指定项目目录的空看板显示通用的“暂无任务”说明。

2. 校验并启动服务：

   ```bash
   python3 <project-taskboard-skill-dir>/scripts/taskboard.py check --root /绝对路径/项目看板
   python3 <project-taskboard-skill-dir>/scripts/taskboard.py start \
     --root /绝对路径/项目看板 \
     --project-root /绝对路径/项目目录
   ```

   默认地址是 `http://127.0.0.1:47832/`。传入 `--project-root` 后，服务会持续监听 `docs/superpowers/plans/*.md`，计划中的任务和勾选状态变化会自动同步到看板。复用正在运行的服务，不重复启动第二份看板。`<project-taskboard-skill-dir>` 指当前 agent 实际发现到的本 Skill 目录；Codex 和 OpenCode 的安装路径可以不同，但它们应指向同一个看板根目录和 URL。

3. 打开页面并核对项目名称、根节点汇总、完整层级、任务状态、任务类型颜色、时间进度和“正在执行”列表。没有 PM Session 时，任务更新直接通过本 Skill 的本地 API 或页面详情面板完成。

## 更新接口

- `GET /api/board`：读取完整项目和任务树；`GET /api/progress` 是兼容别名。
- `GET /api/health`：校验任务树并返回任务数量。
- `POST /api/tasks`：创建任务。至少提供 `title`，可提供 `parent_id`、`kind`、`owner`、`status`、`planned_start`、`planned_end`。
- `POST /api/tasks/{id}/children`：创建指定任务的子任务。
- `PUT /api/tasks/{id}`：按稳定任务 ID 幂等创建或更新任务，适合任意 agent 在开始前声明任务。
- `PATCH /api/tasks/{id}`：更新任务标题、父节点、类型、状态、负责人、当前步骤、起止时间、阶段状态和说明。
- `POST /api/tasks/{id}/status`：只更新状态和当前步骤的快捷接口。

已有看板可以用 `import-plan --root /绝对路径/项目看板 --plan /绝对路径/implementation-plan.md` 同步 Superpowers 计划的新增、删除外的结构变化。同步只更新计划标题、父子关系、任务类型和规格来源，保留 agent 已经上报的状态、负责人和时间。

状态从 `todo` 改为 `in_progress` 时，如果没有开始时间，接口自动登记 `started_at`；状态改为 `done` 时，如果没有结束时间，接口自动登记 `completed_at`。显式提供的真实时间会被保留。每次状态变化会追加到 `status_history`，并原子写回 `board.json`。

## AgentWiki 远程同步

Agent 已连接 AgentWiki MCP 时，**优先复用现有 MCP 连接和授权身份**，不要要求用户另填服务器地址、导出密钥或设置 `AGENTWIKI_*`。Python 脚本不会自动继承宿主 MCP；由调用本 Skill 的 Agent 直接调用已发现的 MCP 工具。

1. 发现 `list_spaces`、`get_taskboard`、`import_taskboard_plans`、`update_taskboard_status`（工具可能带宿主前缀；Local Sync 网关为 `wiki_*`）。始终遵循实际输入 schema：如果工具暴露 `__args`，把下述参数整体放入它，例如 `wiki_get_taskboard({__args:{spaceId}})`；直连 MCP 则直接传 `{spaceId}`。工具缺失时先刷新/重连 MCP；服务器须支持这些工具（AgentWiki v0.12.9+）。若仍缺失，说明兼容性阻塞，不虚构工具、不自动改走 HTTP 或索取密钥。
2. 确定目标 Space：优先复用用户已确认的当前项目映射，并通过 `list_spaces` 校验；没有映射且只有一个可写 Space（editor/publisher）时使用它并告知。多个候选必须询问用户；只有 reader 时说明缺少写权限。项目映射只记录 MCP 连接标识与 `spaceId`，不记录密钥。
3. 调用 `get_taskboard({spaceId})` 查看已有任务和来源。已有本地 `board.json` 时读取完整内容；否则扫描项目的 `docs/superpowers/plans/*.md`，读取每个文件的实际内容。不要把本地路径当上传数据，不要混合上传看板快照与它的原始计划而制造重复任务。
4. 调用 `import_taskboard_plans({spaceId, documents:[{sourcePath,content}], syncStatus:false})`。一批最多 20 个文件，内容合计最多 2 MB（UTF-8）；超限分批。`sourcePath` 是稳定身份：优先沿用远程已有来源，首次用项目内稳定路径并让协作 Agent 复用，不能随工作树/机器改名。JSON 中任务 ID 也保持不变。
5. 每个文件独立提交，检查每项 `results` 的 `status`、`summary` 或错误 `code`；部分失败会返回 `isError:true`，不等于全部回滚。只处理失败文件，按原 `sourcePath` 重试；遇到权限/网络错误先读取远程确认已写入部分，不能声称全批成功。导入后再次 `get_taskboard` 核对任务树。
6. 执行时从远程读取**精确任务 ID**，调用 `update_taskboard_status({spaceId,taskId,status,current_step,expected_status,session_id})`。多计划中裸任务序号不唯一；`session_id` 在同一次执行中保持一致，`expected_status` 使用刚读到的状态。遇到认领/依赖/状态冲突先核对，不自动 `takeover:true`。需要时由用户明确决定接管。

重复导入默认只合并规划字段，保留远程已有状态、负责人和时间；只有明确需要以计划勾选同步进度时才启用 `syncStatus:true`，且不会覆盖 blocked/in_review/canceled。导入或上报只在 Agent 调用工具时发生；本地文件监听不等于远程自动同步。写入以当前 MCP 身份记录审计，并推送到网页看板。

### 无 MCP 时的独立 CLI

仅在没有 MCP 且用户选择独立 HTTP 方式时，使用环境变量 `AGENTWIKI_URL`、`AGENTWIKI_SPACE_ID`、`AGENTWIKI_AGENT_KEY`（需目标 Space 的 editor/publisher 授权）。不要读取宿主 MCP 配置中的秘密来拼接命令。

```bash
python3 <project-taskboard-skill-dir>/scripts/taskboard.py push --project-root /绝对路径/项目目录
python3 <project-taskboard-skill-dir>/scripts/taskboard.py report "superpowers:/abs/path.md:task:2" in_progress --step "写失败测试"
```

`push` 扫描全部标准计划，`--plan` 仅推一个文件，`--sync-status` 显式按勾选同步状态。独立 CLI 仍直接使用 HTTP，不具备宿主 MCP 的自动连接能力。

## 数据边界

- 该 Skill 自己维护 `board.json`，不要求 PM Session，也不依赖 `tasks.json`、PM 心跳或外部任务系统。
- 任务层级由 `parent_id` 决定；执行任务由 `kind=task`、`implementation_task` 或 `work_item` 表示。Superpowers 计划中的 `### Task N` 导入为 `implementation_task`，`Step N` 导入为不计入执行任务数的 `step` 节点。阶段、模块、计划和能力节点用于组织层级，也不计入执行任务数。
- `updated_at` 只表示记录更新时间；没有 `completed_at` 时不把它冒充结束时间。父节点可以显示子任务时间范围，但会标注为汇总。
- 删除接口默认不提供，避免误删历史。需要移除任务时先将其标记为 `canceled`，保留层级和状态变更记录。

任意 agent 的接入约定见 [references/agent-integration.md](references/agent-integration.md)；详细字段和请求示例见 [references/api.md](references/api.md)。OpenCode 的用户级发现目录通常是 `~/.config/opencode/skills/project-taskboard`；其他运行时可使用其对应的 Skill 目录，或者直接调用本目录下的 `scripts/taskboard.py` 和 HTTP API。
