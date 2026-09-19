import importlib.util
import json
import subprocess
import time
from urllib.request import urlopen
from argparse import Namespace
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "taskboard.py"
spec = importlib.util.spec_from_file_location("taskboard", MODULE_PATH)
taskboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(taskboard)


PLAN = """# Account Flow Implementation Plan

**Goal:** Build the account flow.

### Task 1: Add the login contract

**Files:**
- Create: `src/auth.py`

- [ ] **Step 1: Write the failing test**
- [x] **Step 2: Run the test**

### Task 2: Implement the login flow

- [x] **Step 1: Write the failing test**
- [x] **Step 2: Implement the minimal code**
"""


def test_imports_superpowers_tasks_and_steps_as_a_hierarchy():
    board = taskboard.parse_superpowers_plan(PLAN, "/tmp/account-flow.md")

    assert board["project"] == "Account Flow"
    assert [task["kind"] for task in board["tasks"]] == [
        "phase",
        "implementation_task",
        "step",
        "step",
        "implementation_task",
        "step",
        "step",
    ]
    assert board["tasks"][1]["parent_id"] == board["tasks"][0]["id"]
    assert board["tasks"][2]["parent_id"] == board["tasks"][1]["id"]
    assert board["tasks"][2]["title"] == "Write the failing test"


def test_import_derives_execution_status_from_checked_superpowers_steps():
    board = taskboard.parse_superpowers_plan(PLAN, "/tmp/account-flow.md")
    tasks = {task["title"]: task for task in board["tasks"]}

    assert tasks["Add the login contract"]["status"] == "in_progress"
    assert tasks["Implement the login flow"]["status"] == "done"
    assert tasks["Write the failing test"]["status"] in {"todo", "done"}


def test_import_uses_stable_ids_for_the_same_plan():
    first = taskboard.parse_superpowers_plan(PLAN, "/tmp/account-flow.md")
    second = taskboard.parse_superpowers_plan(PLAN, "/tmp/account-flow.md")

    assert [task["id"] for task in first["tasks"]] == [task["id"] for task in second["tasks"]]
    assert all(task["source"] == ["/tmp/account-flow.md"] for task in first["tasks"])


def test_plan_ids_survive_a_plan_title_change():
    first = taskboard.parse_superpowers_plan(PLAN, "/tmp/account-flow.md")
    renamed = taskboard.parse_superpowers_plan(
        PLAN.replace("# Account Flow Implementation Plan", "# Revised Account Flow Implementation Plan"),
        "/tmp/account-flow.md",
    )

    assert first["tasks"][0]["id"] == renamed["tasks"][0]["id"]
    assert first["tasks"][1]["id"] == renamed["tasks"][1]["id"]


def test_init_can_bootstrap_a_board_from_a_superpowers_plan(tmp_path):
    plan_path = tmp_path / "account-flow.md"
    plan_path.write_text(PLAN, encoding="utf-8")
    board_root = tmp_path / "board"

    taskboard.cmd_init(Namespace(
        root=board_root,
        project=None,
        input=None,
        plan=plan_path,
        force=False,
    ))

    board = taskboard.read_json(board_root / "board.json")
    assert board["source_type"] == "superpowers_plan"
    assert sum(task["kind"] == "implementation_task" for task in board["tasks"]) == 2


def test_reimport_updates_plan_structure_without_overwriting_live_status(tmp_path):
    plan_path = tmp_path / "account-flow.md"
    plan_path.write_text(PLAN, encoding="utf-8")
    board_root = tmp_path / "board"
    taskboard.cmd_init(Namespace(root=board_root, project=None, input=None, plan=plan_path, force=False))

    board = taskboard.read_json(board_root / "board.json")
    live_task = next(task for task in board["tasks"] if task["kind"] == "implementation_task")
    live_task["status"] = "in_progress"
    live_task["owner"] = "agent-auth"
    taskboard.write_atomic(board_root / "board.json", board)

    updated_plan = PLAN.replace("Add the login contract", "Add the revised login contract")
    taskboard.merge_superpowers_plan(board_root, updated_plan, str(plan_path))

    merged = taskboard.read_json(board_root / "board.json")
    merged_task = next(task for task in merged["tasks"] if task["id"] == live_task["id"])
    assert merged_task["title"] == "Add the revised login contract"
    assert merged_task["status"] == "in_progress"
    assert merged_task["owner"] == "agent-auth"


def test_project_discovery_imports_all_superpowers_plans(tmp_path):
    plans_dir = tmp_path / "docs" / "superpowers" / "plans"
    plans_dir.mkdir(parents=True)
    (plans_dir / "2026-09-20-auth.md").write_text(PLAN, encoding="utf-8")
    (plans_dir / "2026-09-21-billing.md").write_text(PLAN.replace("Account Flow", "Billing Flow"), encoding="utf-8")

    board = taskboard.build_board_from_project(tmp_path, "Demo Project")

    assert len(taskboard.discover_superpowers_plans(tmp_path)) == 2
    assert board["project"] == "Demo Project"
    assert sum(task["kind"] == "implementation_task" for task in board["tasks"]) == 4
    assert len(board["sources"]) == 2


def test_project_sync_follows_superpowers_checkbox_changes(tmp_path):
    plans_dir = tmp_path / "docs" / "superpowers" / "plans"
    plans_dir.mkdir(parents=True)
    plan_path = plans_dir / "2026-09-20-auth.md"
    plan_path.write_text(PLAN, encoding="utf-8")
    board_root = tmp_path / "board"
    taskboard.cmd_init(Namespace(root=board_root, project=None, input=None, plan=None, project_root=tmp_path, force=False))

    plan_path.write_text(PLAN.replace("- [ ] **Step 1: Write the failing test**", "- [x] **Step 1: Write the failing test**"), encoding="utf-8")
    taskboard.sync_project_plans(board_root, tmp_path)

    board = taskboard.read_json(board_root / "board.json")
    execution_task = next(task for task in board["tasks"] if task["kind"] == "implementation_task")
    assert execution_task["status"] == "done"
    assert execution_task["completed_at"]


def test_serve_watches_plan_file_without_manual_task_creation(tmp_path):
    plans_dir = tmp_path / "docs" / "superpowers" / "plans"
    plans_dir.mkdir(parents=True)
    plan_path = plans_dir / "2026-09-20-auth.md"
    plan_path.write_text(PLAN, encoding="utf-8")
    board_root = tmp_path / "board"
    taskboard.cmd_init(Namespace(root=board_root, project=None, input=None, plan=None, project_root=tmp_path, force=False))
    process = subprocess.Popen([
        "python3", str(MODULE_PATH), "serve", "--root", str(board_root),
        "--project-root", str(tmp_path), "--port", "47841", "--watch-interval", "0.5",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(30):
            try:
                with urlopen("http://127.0.0.1:47841/api/health", timeout=0.2) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(0.1)
        plan_path.write_text(PLAN.replace("- [ ] **Step 1: Write the failing test**", "- [x] **Step 1: Write the failing test**"), encoding="utf-8")
        deadline = time.time() + 4
        status = None
        while time.time() < deadline:
            with urlopen("http://127.0.0.1:47841/api/board", timeout=0.5) as response:
                payload = json.loads(response.read())
            task = next(task for task in payload["board"]["tasks"] if task["kind"] == "implementation_task")
            status = task["status"]
            if status == "done":
                break
            time.sleep(0.2)
        assert status == "done"
    finally:
        process.terminate()
        process.wait(timeout=5)
