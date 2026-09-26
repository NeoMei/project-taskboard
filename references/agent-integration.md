# Agent 接入约定

任何项目运行 Skill 都可以把任务进度写入看板。看板只要求 agent 遵守以下最小协议，不要求 PM Session、特定模型、特定代码仓库或特定 agent 工具。Codex、OpenCode 以及其他能执行 shell/HTTP 请求的运行时都可以使用同一套协议。

## 运行时安装

Skill 的发现路径由运行时决定；服务和数据格式不随运行时变化。

| 运行时 | 用户级 Skill 目录示例 |
|---|---|
| Codex | `~/.codex/skills/project-taskboard` |
| OpenCode | `~/.config/opencode/skills/project-taskboard` |
| 其他 agent | 该运行时的 Skill 目录，或直接调用 `scripts/taskboard.py` |

如果多个 agent 共同推进同一个项目，只需要启动一份看板服务，其他 agent 复用同一个 `TASKBOARD_URL`。不要因为运行时不同而创建多份项目看板。

## 已连接 AgentWiki MCP

优先使用现有 MCP；无需再次配置服务器地址或 API 密钥。先发现工具并调用 `list_spaces`。Local Sync 网关使用 `wiki_*` 名称；若实际 schema 是 `__args`，把参数包在其中（例如 `wiki_get_taskboard({__args:{spaceId}})`），直连 MCP 直接传参数。复用用户已确定的项目 Space 映射；多个候选时先确认目标，不能任取第一个。映射只含 MCP 连接标识和 Space ID。

- 读取远程：`get_taskboard({spaceId})`，取得稳定来源及精确任务 ID。
- 读取本地全部计划内容后批量导入：`import_taskboard_plans({spaceId,documents:[{sourcePath,content}],syncStatus:false})`；每批最多 20 个文件 / 内容合计 2 MB，逐文件提交及返回结果。已有看板用完整 `board.json` 替代原始计划批次。
- 开工：`update_taskboard_status({spaceId,taskId,status:"in_progress",current_step:"写失败测试",expected_status:"todo",session_id:"本次执行的稳定标识"})`。
- 完成：先读取当前状态，再传相应 `expected_status` 并上报 `done`；只有验证证据支持完成时才这样报告。
- `isError:true` 的批量结果可能已经有成功文件；只修正失败项并沿用来源重试。读取远程确认结果。权限/网络错误也可能发生在部分提交之后。
- 任务认领、依赖与并发检查沿用服务器规则。不得自动接管；多个文件里的 Task 1 不可当作唯一 ID。
- 工具缺失先刷新/重连；服务器需要 v0.12.9+。仍不可用就报告兼容性阻塞，不读取 MCP 密钥或默认退回 HTTP。

这条路径由 Agent 执行本地读文件并发送内容；服务端不读取本地路径，Python `push` 也不会继承 MCP。CLI 环境变量仅用于用户选择的独立 HTTP 方式。本地监听不会自动调用远程 MCP。

## 本地看板接入步骤

1. 直接扫描项目的 `docs/superpowers/plans/*.md` 初始化任务树：`taskboard.py init --root /绝对路径/项目看板 --project-root /绝对路径/项目目录`。每个 `### Task N` 是执行任务，每个 `Step N` 是展开用的步骤节点，不需要手动创建任务。
2. 用 `taskboard.py start --root /绝对路径/项目看板 --project-root /绝对路径/项目目录` 启动自动同步服务，并把看板地址传给 agent，例如 `TASKBOARD_URL=http://127.0.0.1:47832`。
3. 看板服务持续监听计划文件；Superpowers 执行计划中的勾选变化会自动更新任务状态和完成时间。
4. agent 仍可以为执行中的任务补充负责人、当前步骤、证据以及 `blocked`/`in_review` 等运行时状态，但不需要创建任务。重复调用同一个稳定 ID 也不会产生重复卡片。
5. 计划发生结构变化时，自动同步会加入新增任务并保留 agent 已经上报的执行状态；已移除的任务保留在看板中，避免丢失历史。

## 推荐生命周期

```text
todo -> in_progress -> in_review -> done
                         └-> blocked
```

取消的任务使用 `canceled` 并保留原卡片。规划节点使用 `phase`、`module` 或 `capability`；agent 真正执行的节点使用 `task`、`implementation_task` 或 `work_item`。

## 最小请求示例

```bash
board="${TASKBOARD_URL:-http://127.0.0.1:47832}"

curl -sS -X PUT "$board/api/tasks/agent-login-001" \
  -H 'Content-Type: application/json' \
  -d '{"title":"实现登录流程","kind":"implementation_task","owner":"agent-auth","agent_id":"agent-auth","run_id":"run-20260920-001","parent_id":"module-auth","status":"todo"}'

curl -sS -X POST "$board/api/tasks/agent-login-001/status" \
  -H 'Content-Type: application/json' \
  -d '{"status":"in_progress","current_step":"实现 API"}'

curl -sS -X POST "$board/api/tasks/agent-login-001/status" \
  -H 'Content-Type: application/json' \
  -d '{"status":"done","current_step":"已完成并提交验证证据"}'
```

## 责任边界

看板能保证任务树校验、状态变更记录、开始/完成时间登记和本地原子写入。它不能自动判断 agent 是否真的执行了代码、测试或发布；这些事实仍需要 agent 把证据写入 `evidence` 或 `summary`，并由项目自己的验收流程核实。

所有 agent 必须使用同一个看板 URL。不要为每个子 agent 启动一个独立服务，否则它们会写入不同的 `board.json`，页面无法形成统一全景。
