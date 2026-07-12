# MCP Agent Body

A 15-tool MCP (Model Context Protocol) server with HTTP/SSE transport. Any MCP-compatible client (Claude Desktop, Cursor, etc.) can connect and use all tools.

## Quick Start

```bash
pip install -r requirements.txt
python server.py --port 8000
```

Server starts on `http://0.0.0.0:8000/sse`.

## Tools

### File Operations
| Tool | Arguments | Description |
|------|-----------|-------------|
| `read_file` | `file_path` | Read file contents |
| `write_file` | `file_path`, `content` | Write content to file (creates parent dirs) |
| `edit_file` | `file_path`, `old_string`, `new_string` | Find-and-replace in file |
| `list_dir` | `directory_path` (default `.`) | List directory entries |

### Shell & Git
| Tool | Arguments | Description |
|------|-----------|-------------|
| `exec_shell` | `command`, `workdir` (default `.`), `timeout_seconds` (default 30) | Execute shell command |
| `exec_git` | `args`, `workdir` (default `.`) | Execute git command |

### Web
| Tool | Arguments | Description |
|------|-----------|-------------|
| `web_fetch` | `url` | Fetch URL content |
| `web_search` | `query`, `num_results` (default 8) | Search web via DuckDuckGo |

### Memory (in-memory KV store)
| Tool | Arguments | Description |
|------|-----------|-------------|
| `memory_write` | `key`, `value` | Store a value |
| `memory_read` | `key` | Retrieve a value |
| `memory_delete` | `key` | Delete a value |

### Task Management (in-memory)
| Tool | Arguments | Description |
|------|-----------|-------------|
| `task_create` | `title`, `description` (default `""`) | Create a task |
| `task_list` | *none* | List all tasks |
| `task_update` | `task_id`, `title?`, `description?`, `status?` | Update a task |
| `task_delete` | `task_id` | Delete a task |

## Connecting

### MCP Protocol Flow

1. Connect to `http://HOST:PORT/sse` (SSE stream)
2. Receive `endpoint` event with session URL
3. Send `initialize` request
4. Send `notifications/initialized`
5. Call tools via `tools/call`

### Example (Python)

```python
import httpx, json

BASE = "http://localhost:8000"

# Connect to SSE
with httpx.Client() as client:
    with client.stream("GET", f"{BASE}/sse") as sse:
        for line in sse.iter_lines():
            if line.startswith("data: /"):
                endpoint = line[6:]
                break

    post_url = f"{BASE}{endpoint}"

    # Initialize
    client.post(post_url, json={
        "jsonrpc": "2.0", "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "my-client", "version": "1.0"}
        }
    })

    # Call a tool
    client.post(post_url, json={
        "jsonrpc": "2.0", "id": 2,
        "method": "tools/call",
        "params": {
            "name": "read_file",
            "arguments": {"file_path": "/etc/hostname"}
        }
    })
```

Responses arrive as SSE `data:` events on the SSE connection.

### Claude Desktop Config

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mcp-agent-body": {
      "command": "python",
      "args": ["/path/to/server.py"],
      "env": {}
    }
  }
}
```

Or for HTTP mode with `mcp` CLI:

```json
{
  "mcpServers": {
    "mcp-agent-body": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

## CLI Options

```
python server.py --host 0.0.0.0 --port 8000
```

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `0.0.0.0` | Bind address |
| `--port` | `8000` | Port number |

## Dependencies

- `mcp` — MCP Python SDK
- `httpx` — HTTP client
- `httpx-sse` — SSE support
- `beautifulsoup4` — HTML parsing for web_search
- `uvicorn` — ASGI server

## Security

**No sandboxing.** The server has full access to the filesystem and shell. Run only in trusted environments.
