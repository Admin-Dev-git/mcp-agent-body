"""
MCP Agent Body - 15 Tool MCP Server with HTTP/SSE Transport
Run: python server.py
Connect: Any MCP client (Claude Desktop, Cursor, etc.) via http://HOST:PORT/sse
"""

import json
import shlex
import subprocess
import time
import threading
from pathlib import Path
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "mcp-agent-body",
    instructions="MCP Agent Body with 15 tools: file I/O, shell, git, web, memory, tasks",
)

MEMORY: dict[str, str] = {}
MEMORY_LOCK = threading.Lock()

TASKS: dict[str, dict] = {}
TASKS_LOCK = threading.Lock()
TASK_COUNTER = 0


# ---------------------------------------------------------------------------
# 1. read_file
# ---------------------------------------------------------------------------
@mcp.tool()
def read_file(file_path: str) -> str:
    resolved = Path(file_path).resolve()
    if not resolved.is_file():
        return f"Error: File not found: {file_path}"
    try:
        return resolved.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading file: {e}"


# ---------------------------------------------------------------------------
# 2. write_file
# ---------------------------------------------------------------------------
@mcp.tool()
def write_file(file_path: str, content: str) -> str:
    resolved = Path(file_path).resolve()
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return f"Written {len(content)} bytes to {file_path}"
    except Exception as e:
        return f"Error writing file: {e}"


# ---------------------------------------------------------------------------
# 3. edit_file  (find-and-replace)
# ---------------------------------------------------------------------------
@mcp.tool()
def edit_file(file_path: str, old_string: str, new_string: str) -> str:
    resolved = Path(file_path).resolve()
    if not resolved.is_file():
        return f"Error: File not found: {file_path}"
    try:
        text = resolved.read_text(encoding="utf-8")
        if old_string not in text:
            return f"Error: old_string not found in {file_path}"
        count = text.count(old_string)
        text = text.replace(old_string, new_string)
        resolved.write_text(text, encoding="utf-8")
        return f"Replaced {count} occurrence(s) in {file_path}"
    except Exception as e:
        return f"Error editing file: {e}"


# ---------------------------------------------------------------------------
# 4. list_dir
# ---------------------------------------------------------------------------
@mcp.tool()
def list_dir(directory_path: str = ".") -> str:
    resolved = Path(directory_path).resolve()
    if not resolved.is_dir():
        return f"Error: Directory not found: {directory_path}"
    try:
        entries = []
        for p in sorted(resolved.iterdir()):
            suffix = "/" if p.is_dir() else ""
            entries.append(f"{p.name}{suffix}")
        return "\n".join(entries) if entries else "(empty directory)"
    except Exception as e:
        return f"Error listing directory: {e}"


# ---------------------------------------------------------------------------
# 5. exec_shell
# ---------------------------------------------------------------------------
@mcp.tool()
def exec_shell(
    command: str,
    workdir: str = ".",
    timeout_seconds: int = 30,
) -> str:
    resolved_wd = Path(workdir).resolve()
    if not resolved_wd.is_dir():
        return f"Error: Directory not found: {workdir}"
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(resolved_wd),
            timeout=timeout_seconds,
        )
        out = result.stdout
        if result.stderr:
            out += "\nSTDERR:\n" + result.stderr
        if result.returncode != 0:
            out += f"\n(exit code {result.returncode})"
        return out if out else "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout_seconds}s"
    except Exception as e:
        return f"Error executing command: {e}"


# ---------------------------------------------------------------------------
# 6. exec_git
# ---------------------------------------------------------------------------
@mcp.tool()
def exec_git(args: str, workdir: str = ".") -> str:
    resolved_wd = Path(workdir).resolve()
    if not resolved_wd.is_dir():
        return f"Error: Directory not found: {workdir}"
    try:
        result = subprocess.run(
            ["git"] + shlex.split(args),
            capture_output=True,
            text=True,
            cwd=str(resolved_wd),
            timeout=30,
        )
        out = result.stdout
        if result.stderr:
            out += "\nSTDERR:\n" + result.stderr
        if result.returncode != 0:
            out += f"\n(exit code {result.returncode})"
        return out if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Git command timed out after 30s"
    except Exception as e:
        return f"Error executing git: {e}"


# ---------------------------------------------------------------------------
# 7. web_fetch
# ---------------------------------------------------------------------------
@mcp.tool()
def web_fetch(url: str) -> str:
    try:
        result = httpx.get(url, follow_redirects=True, timeout=30)
        result.raise_for_status()
        content_type = result.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                data = result.json()
                return json.dumps(data, indent=2, ensure_ascii=False)
            except Exception:
                return result.text
        return result.text
    except Exception as e:
        return f"Error fetching URL: {e}"


# ---------------------------------------------------------------------------
# 8. web_search
# ---------------------------------------------------------------------------
@mcp.tool()
def web_search(query: str, num_results: int = 8) -> str:
    try:
        search_url = f"https://html.duckduckgo.com/html/?q={httpx.utils.quote(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; MCPAgentBody/1.0)"
        }
        result = httpx.get(search_url, headers=headers, follow_redirects=True, timeout=30)
        result.raise_for_status()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(result.text, "html.parser")
        results = []
        for item in soup.select(".result")[:num_results]:
            title_el = item.select_one(".result__title a")
            snippet_el = item.select_one(".result__snippet")
            if title_el:
                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                results.append(f"{title}\n  URL: {href}\n  {snippet}")
        if not results:
            return "No search results found"
        return "\n\n".join(results)
    except Exception as e:
        return f"Error searching web: {e}"


# ---------------------------------------------------------------------------
# 9. memory_write
# ---------------------------------------------------------------------------
@mcp.tool()
def memory_write(key: str, value: str) -> str:
    with MEMORY_LOCK:
        MEMORY[key] = value
    return f"Stored key '{key}' ({len(value)} bytes)"


# ---------------------------------------------------------------------------
# 10. memory_read
# ---------------------------------------------------------------------------
@mcp.tool()
def memory_read(key: str) -> str:
    with MEMORY_LOCK:
        val = MEMORY.get(key)
    if val is None:
        return f"Error: key '{key}' not found in memory"
    return val


# ---------------------------------------------------------------------------
# 11. memory_delete
# ---------------------------------------------------------------------------
@mcp.tool()
def memory_delete(key: str) -> str:
    with MEMORY_LOCK:
        if key in MEMORY:
            del MEMORY[key]
            return f"Deleted key '{key}'"
        return f"Error: key '{key}' not found in memory"


# ---------------------------------------------------------------------------
# 12. task_create
# ---------------------------------------------------------------------------
@mcp.tool()
def task_create(title: str, description: str = "") -> str:
    global TASK_COUNTER
    with TASKS_LOCK:
        TASK_COUNTER += 1
        tid = str(TASK_COUNTER)
        TASKS[tid] = {
            "id": tid,
            "title": title,
            "description": description,
            "status": "pending",
            "created_at": time.time(),
        }
    return json.dumps(TASKS[tid], indent=2)


# ---------------------------------------------------------------------------
# 13. task_list
# ---------------------------------------------------------------------------
@mcp.tool()
def task_list() -> str:
    with TASKS_LOCK:
        if not TASKS:
            return "(no tasks)"
        return json.dumps(list(TASKS.values()), indent=2)


# ---------------------------------------------------------------------------
# 14. task_update
# ---------------------------------------------------------------------------
@mcp.tool()
def task_update(
    task_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
) -> str:
    with TASKS_LOCK:
        task = TASKS.get(task_id)
        if task is None:
            return f"Error: task '{task_id}' not found"
        if title is not None:
            task["title"] = title
        if description is not None:
            task["description"] = description
        if status is not None:
            task["status"] = status
        task["updated_at"] = time.time()
    return json.dumps(task, indent=2)


# ---------------------------------------------------------------------------
# 15. task_delete
# ---------------------------------------------------------------------------
@mcp.tool()
def task_delete(task_id: str) -> str:
    with TASKS_LOCK:
        if task_id in TASKS:
            del TASKS[task_id]
            return f"Deleted task '{task_id}'"
        return f"Error: task '{task_id}' not found"


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="MCP Agent Body Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8000, help="Port")
    args = parser.parse_args()

    print(f"MCP Agent Body starting on http://{args.host}:{args.port}/sse")
    print(f"Available tools: read_file, write_file, edit_file, list_dir, exec_shell, exec_git, web_fetch, web_search, memory_write, memory_read, memory_delete, task_create, task_list, task_update, task_delete")
    app = mcp.sse_app()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
