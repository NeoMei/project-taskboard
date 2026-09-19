import importlib.util
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "taskboard.py"
spec = importlib.util.spec_from_file_location("taskboard", MODULE_PATH)
taskboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(taskboard)


TASKS = [
    {"id": "superpowers-plan-x-task-1", "title": "Task 1", "external_id": "superpowers:/tmp/a.md:task:1", "status": "todo"},
    {"id": "superpowers-plan-x-task-2", "title": "Task 2", "external_id": "superpowers:/tmp/a.md:task:2", "status": "done"},
    {"id": "superpowers-plan-x-task-1-step-1", "title": "Step", "external_id": "superpowers:/tmp/a.md:task:1:step:1", "status": "done"},
    {"id": "superpowers-plan-y-task-1", "title": "Other Plan Task 1", "external_id": "superpowers:/tmp/b.md:task:1", "status": "todo"},
]


def test_config_prefers_arguments_over_environment():
    os.environ["AGENTWIKI_URL"] = "https://env.example.com/"
    try:
        config = taskboard.agentwiki_config("https://arg.example.com", "space-arg", "agk_arg")
    finally:
        del os.environ["AGENTWIKI_URL"]
    assert config == {"server": "https://arg.example.com", "space": "space-arg", "key": "agk_arg"}


def test_config_falls_back_to_environment_and_strips_trailing_slash():
    os.environ["AGENTWIKI_URL"] = "https://env.example.com/"
    os.environ["AGENTWIKI_SPACE_ID"] = "space-env"
    os.environ["AGENTWIKI_AGENT_KEY"] = "agk_env"
    try:
        config = taskboard.agentwiki_config(None, None, None)
    finally:
        for name in ("AGENTWIKI_URL", "AGENTWIKI_SPACE_ID", "AGENTWIKI_AGENT_KEY"):
            del os.environ[name]
    assert config == {"server": "https://env.example.com", "space": "space-env", "key": "agk_env"}


def test_config_reports_missing_entries():
    try:
        taskboard.agentwiki_config(None, None, None)
    except RuntimeError as exc:
        assert "AGENTWIKI_URL" in str(exc) and "AGENTWIKI_SPACE_ID" in str(exc) and "AGENTWIKI_AGENT_KEY" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for missing config")


def test_import_payload_shape():
    payload = taskboard.agentwiki_import_payload("# Plan", "/tmp/a.md", True, "My Project")
    assert payload == {"content": "# Plan", "sourcePath": "/tmp/a.md", "syncStatus": True, "project": "My Project"}
    minimal = taskboard.agentwiki_import_payload("# Plan", "/tmp/a.md", False)
    assert minimal == {"content": "# Plan", "sourcePath": "/tmp/a.md", "syncStatus": False}


def test_resolve_task_by_id_external_id_and_number():
    assert taskboard.resolve_agentwiki_task(TASKS, "superpowers-plan-x-task-2")["title"] == "Task 2"
    assert taskboard.resolve_agentwiki_task(TASKS, "superpowers:/tmp/a.md:task:1")["title"] == "Task 1"
    assert taskboard.resolve_agentwiki_task(TASKS, "2")["title"] == "Task 2"
    assert taskboard.resolve_agentwiki_task(TASKS, "superpowers:/tmp/b.md:task:1")["title"] == "Other Plan Task 1"


def test_resolve_task_rejects_ambiguous_and_unknown_refs():
    try:
        taskboard.resolve_agentwiki_task(TASKS, "1")
    except RuntimeError as exc:
        assert "不唯一" in str(exc)
    else:
        raise AssertionError("expected ambiguity error")
    try:
        taskboard.resolve_agentwiki_task(TASKS, "missing-title")
    except RuntimeError as exc:
        assert "未找到任务" in str(exc)
    else:
        raise AssertionError("expected unknown-ref error")


def _start_server(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_agentwiki_request_sends_auth_and_parses_json():
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen["path"] = self.path
            seen["auth"] = self.headers.get("Authorization")
            body = json.dumps({"board": {"tasks": []}}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = _start_server(Handler)
    try:
        result = taskboard.agentwiki_request(f"http://127.0.0.1:{server.server_port}", "space-1", "agk_key", "")
    finally:
        server.shutdown()
    assert result == {"board": {"tasks": []}}
    assert seen["path"] == "/api/spaces/space-1/taskboard"
    assert seen["auth"] == "Bearer agk_key"


def test_agentwiki_request_posts_json_payload():
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            seen["path"] = self.path
            seen["body"] = json.loads(self.rfile.read(length).decode("utf-8"))
            body = b'{"task": {"id": "t1", "status": "done"}}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = _start_server(Handler)
    try:
        result = taskboard.agentwiki_request(
            f"http://127.0.0.1:{server.server_port}", "space-1", "agk_key",
            "/tasks/t1/status", {"status": "done"},
        )
    finally:
        server.shutdown()
    assert result["task"]["status"] == "done"
    assert seen["path"] == "/api/spaces/space-1/taskboard/tasks/t1/status"
    assert seen["body"] == {"status": "done"}


def test_agentwiki_request_maps_http_error_to_runtime_error():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"code": "SPACE_ACCESS_DENIED", "message": "denied"}'
            self.send_response(403)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = _start_server(Handler)
    try:
        try:
            taskboard.agentwiki_request(f"http://127.0.0.1:{server.server_port}", "space-1", "agk_key", "")
        except RuntimeError as exc:
            assert "HTTP 403" in str(exc) and "denied" in str(exc)
        else:
            raise AssertionError("expected RuntimeError for HTTP 403")
    finally:
        server.shutdown()
