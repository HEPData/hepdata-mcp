# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.2.0 - 2026-08-25

### Added

- Server now advertises rich metadata per the latest MCP specification: server
  `title`, `description`, and `version` are reported during connection instead
  of an empty version string.
- All tools advertise tool annotations (`readOnlyHint`, `destructiveHint`,
  `idempotentHint`, `openWorldHint`) and human-readable titles, allowing MCP
  clients to skip confirmation prompts for these read-only queries.
- Domain errors from tools now surface as actionable `ToolError` messages to
  agents (for example, "HEPData returned 404 Not Found: ...") instead of a
  generic crash notice, letting agents self-correct.
- End-to-end agent-style verification against the live HEPData API covering
  tool discovery, multi-step workflows, resource templates, and error paths.

### Changed

- **Breaking:** upgraded the MCP Python SDK from 1.x (`mcp>=1.27,<2`) to 2.x
  (`mcp>=2.1.1,<3`), targeting the 2026-07-28 protocol revision. The server
  still serves older clients over stdio and Streamable HTTP.
- Transport settings (`--host`, `--port`, `--path`, `--stateless-http`) are now
  applied per transport when the server starts, matching the SDK v2 API where
  these parameters moved from the server constructor into `run()`.
- `list_tables` now fetches the full record instead of the light record;
  HEPData's light JSON payload omits tables entirely, so the previous
  implementation always returned an empty table list against the live API.

### Fixed

- `list_tables` returned zero tables for every record when queried against the
  live HEPData service because the extraction ran on the light record, which
  contains no table data. Tables are now correctly listed (verified live:
  `ins3103133` reports its 2 data tables).
