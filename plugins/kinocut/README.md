# Kinocut plugin

![Kinocut icon](icon.png)

Guarded local video editing for AI agents. The plugin adds the Kinocut MCP
server and two skills (`kinocut`, `kinocut-repurpose`) to your agent.

Kinocut runs on your own machine. Your video never leaves it.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- FFmpeg and ffprobe on `PATH`
- Python 3.11 or newer (uv installs it if needed)

Check your setup with `uvx kinocut==1.16.2 doctor`.

## Claude installation

Claude Code and Cowork use the bundled Python project and uv lockfile to
install Kinocut 1.16.2 and its exact core dependencies. The launcher runs
`uv run --locked --exact`: it fails if the project and lock disagree rather than
resolving new dependency versions, and removes dependencies no longer in the lock.
Its environment is stored in Claude's
persistent plugin data directory, outside the installed plugin files.

The first launch downloads the locked dependencies from PyPI. Later launches
reuse that environment. This does not bundle FFmpeg or optional AI packages.
Cursor, MiniMax, Kimi and Agent Plugins hosts retain the pinned
`uvx kinocut==1.16.2` launcher below.

Claude's directory still requires manual review for registry package launchers,
including locked ones. The lock improves reproducibility; it does not guarantee
approval or a Verified badge. The directory-only icon, documentation, support,
privacy and terms fields are intentional listing metadata.

## What's in this folder

| Agent | Files |
| --- | --- |
| Claude Code / Cowork | `.claude-plugin/plugin.json`, `.mcp.json`, `pyproject.toml`, `uv.lock`, `skills/` |
| Hermes Agent and other Agent Plugins v1 hosts | `plugin.json`, `mcp.json`, `skills/` |
| OpenClaw / ClawHub | Claude Code layout above, bundled icon |
| Grok Build | Claude Code layout above |
| ZCode | Installs from the Claude Code marketplace |
| MiniMax | `.minimax-plugin/plugin.json`, `kinocut.mcp.json`, bundled icon |
| Cursor | Repository marketplace manifest, `.cursor-plugin/plugin.json`, `mcp.json`, `skills/` |
| Kimi Code | `kimi.plugin.json`, `skills/` |
| OpenCode | Configuration in `opencode-plugin/README.md` |

## Manual setup for any MCP client

The Claude layout requires a host that expands `CLAUDE_PLUGIN_ROOT` and
`CLAUDE_PLUGIN_DATA`. Other clients can use the pinned manual configuration:

```json
{
  "mcpServers": {
    "kinocut": { "command": "uvx", "args": ["kinocut==1.16.2"] }
  }
}
```

## Links

- Website: https://kinocut.dev/
- Source and issues: https://github.com/KyaniteLabs/kinocut
- License: Apache-2.0
