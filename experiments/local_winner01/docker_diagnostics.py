"""Sanitized Docker stage and process diagnostics; no raw test or patch output."""
import json


def classify_output(output: str) -> str:
    """Classify known signatures, never exposing stdout or stderr."""
    log = output.lower()
    if "dubious ownership in repository" in log:
        return "GIT_DUBIOUS_OWNERSHIP"
    if "index.lock" in log and ("permission denied" in log or "unable to create" in log):
        return "GIT_INDEX_WRITE_DENIED"
    if ("permission denied" in log or "operation not permitted" in log) and (
        "fatal:" in log or ".git/" in log
    ):
        return "GIT_ACCESS_DENIED"
    if "permission denied" in log or "operation not permitted" in log:
        return "FILESYSTEM_ACCESS_DENIED"
    if "exec format error" in log:
        return "EXEC_FORMAT_ERROR"
    if "no space left on device" in log:
        return "DISK_EXHAUSTED"
    if "no such file or directory" in log:
        return "MISSING_FILE_OR_EXECUTABLE"
    if "error response from daemon" in log or "oci runtime" in log:
        return "DOCKER_DAEMON_OR_RUNTIME_ERROR"
    return "UNKNOWN"


def inspect_snapshot(raw: str, cli_exit: int) -> dict:
    if cli_exit != 0:
        return {"available": False, "parse_error": "INSPECT_COMMAND_FAILED"}
    try:
        state = json.loads(raw)
        if not isinstance(state, dict):
            raise ValueError("not a dict")
    except (ValueError, TypeError):
        return {"available": False, "parse_error": "INSPECT_JSON_INVALID"}
    started = state.get("StartedAt")
    return {
        "available": True,
        "status": state.get("Status") if state.get("Status") in (
            "created", "running", "exited", "dead", "paused", "restarting"
        ) else "other",
        "exit_code": state.get("ExitCode") if type(state.get("ExitCode")) is int else None,
        "oom_killed": state.get("OOMKilled") is True,
        "runtime_error": bool(state.get("Error")),
        "started": isinstance(started, str) and bool(started)
        and not started.startswith("0001-01-01"),
    }


def exit_origin(cli_exit: int, state: dict) -> str:
    """Do not conflate Docker CLI exit 128 with inner process exit 128."""
    if not state.get("available"):
        return "UNKNOWN_WITHOUT_INSPECT"
    if state.get("runtime_error"):
        return "DOCKER_RUNTIME"
    if state.get("oom_killed"):
        return "CONTAINER_OOM"
    if (state.get("started") and state.get("status") == "exited"
            and state.get("exit_code") == cli_exit):
        return "CONTAINER_PROCESS"
    return "DOCKER_CLI_OR_UNDETERMINED"
