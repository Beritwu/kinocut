# Kinocut plugin

![Kinocut icon](icon.png)

Guarded local video editing for AI agents. The plugin adds the Kinocut MCP
server and two skills (`kinocut`, `kinocut-repurpose`) to your agent.

Kinocut processes media on your own machine. Network use depends on the features
you choose:

- The first launch downloads Kinocut and its dependencies from PyPI.
- URL inputs download the requested media.
- Font and model-weight features download assets from GitHub when needed.
- With `use_ai` enabled and `ANTHROPIC_API_KEY` set, AI color grading sends a
  video frame to Anthropic.
- Revideo dependency installation runs `npm ci`, which accesses the npm registry.

Local FFmpeg editing does not upload your media. Review and approve optional
network features before using them.

Prefer new output paths. Never target credentials, session files or agent
configuration directories.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- FFmpeg and ffprobe on `PATH`
- Python 3.11 or newer (uv installs it if needed)

Check your setup with `uvx kinocut==1.16.2 doctor`.

## Claude installation

Claude Code and Cowork run the pinned `uvx kinocut==1.16.2` launcher.
The bundled Python project and `uv.lock` record exact core dependency versions,
public PyPI sources and artifact hashes for directory review. The directory's
locked-launcher check requires this plain pinned command, without environment
overrides or dependency-file options.

uvx pins Kinocut itself and resolves its dependencies when creating a tool
environment; it does not consume the bundled uv.lock. That lock is an audit
snapshot. uv caches the environment outside the installed plugin files.

The first launch downloads the dependencies from PyPI. Later launches
reuse that environment. This does not bundle FFmpeg or optional AI packages.
Cursor, MiniMax, Kimi and Agent Plugins hosts retain the pinned
`uvx kinocut==1.16.2` launcher below.

Claude's directory still requires manual review for registry package launchers,
including locked ones. The lock documents a dependency snapshot; it does not guarantee
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

Clients can also use the pinned configuration directly:

```json
{
  "mcpServers": {
    "kinocut": { "command": "uvx", "args": ["kinocut==1.16.2"] }
  }
}
```

## Narrowing the tool list

Kinocut exposes about 200 MCP tools. A host tool allowlist reduces the schemas
sent with each model request. For Hermes, this small inspection-and-trim set
goes in `mcp_servers` in your Hermes `config.yaml`:

```yaml
mcp_servers:
  kinocut:
    command: uvx
    args: ["kinocut==1.16.2"]
    tools:
      include: [search_tools, video_info, video_trim, video_thumbnail]
      resources: false
      prompts: false
```

Hermes uses this explicit, same-name server configuration in preference to the
plugin's launcher. Keep its version aligned with the plugin's `mcp.json` when
updating. Run `/reload-mcp` after changing the configuration. Use server-native
tool names in `include`, and add the edit and quality-check tools your workflow
needs. `search_tools` helps discover names; it does not enable excluded tools or
hide schemas by itself. See the [Hermes MCP configuration reference](https://hermes-agent.nousresearch.com/docs/reference/mcp-config-reference/).

For other hosts, use their tool-filtering controls if available.

## Links

- Website: https://kinocut.dev/
- Source and issues: https://github.com/KyaniteLabs/kinocut
- License: Apache-2.0
