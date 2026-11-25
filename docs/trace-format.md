# Trace format

A trace is what one agent run did, recorded the same way whichever CLI ran it. Adapters translate
their CLI's own output into a trace; checks, diffs and fixtures read only traces. The model lives in
`src/churnbench/trace.py`.

Traces are stored as JSON Lines: one trace per line, UTF-8, each line ending in a newline. Blank
lines are skipped when reading.

## Schema version 1

```json
{"schema_version":1,"model":"model-a","tool_version":"2.1.300 (Claude Code)","turns":7,"cost_usd":0.0421,"final_text":"Added the fee rule; tests pass.","events":[{"kind":"tool_call","name":"Bash","input_summary":"{\"command\":\"python -m pytest -q\"}","ok":false},{"kind":"permission_denied","tool":"Bash","input_summary":"{\"command\":\"rm -rf vendor\"}"},{"kind":"assistant_text","text":"Added the fee rule; tests pass."}]}
```

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | integer | Format version. Readers reject any value they do not know. |
| `model` | string | Model id the run used, as the adapter reports it. |
| `tool_version` | string | Version string of the agent CLI that ran. |
| `turns` | integer, >= 0 | Number of turns the CLI reports for the run. |
| `cost_usd` | finite number >= 0, or null | Estimated cost the CLI reports; `null` when it reports none. |
| `final_text` | string | The run's final answer text. |
| `events` | array | What happened, in the order it happened. |

All fields are required. Unknown fields are rejected, so a typo cannot pass silently.

### Events

Every event has a `kind`; the other fields depend on it.

| `kind` | Fields | Meaning |
|---|---|---|
| `tool_call` | `name` (string), `input_summary` (string), `ok` (boolean) | The agent called a tool. `ok` is false when the call reported an error. |
| `assistant_text` | `text` (string) | Text the agent wrote between tool calls. |
| `permission_denied` | `tool` (string), `input_summary` (string) | A tool call was refused by the permission system. |

`input_summary` is the tool input as compact JSON with sorted keys (a plain string input is kept
as is), cut to 200 characters. A cut summary ends in `…`. The summary is for diffs and invariants
such as "ran pytest before finishing"; it is not a full record of the input.

## Where the fields come from

- **Claude Code** (`claude -p --output-format stream-json --verbose`): `tool_use` blocks in
  `assistant` messages give `tool_call` name and input; the matching `tool_result` block's
  `is_error` gives `ok`. The result message's `permission_denials` list gives `permission_denied`
  events; it is the authoritative record, because the streamed `permission_denied` system
  messages are best-effort and skip denials made on the `PreToolUse` hook path. The final
  `result` message gives `final_text` (`result`), `cost_usd` (`total_cost_usd`) and `turns`
  (`num_turns`).
- **Codex** (`codex exec --json`): `item.started` and `item.completed` events carry an `item` with
  a `type`. `agent_message` items (field `text`) give `assistant_text`; `command_execution` items
  (fields `command`, `status`) give `tool_call` events. The CLI source
  ([`codex-rs/exec/src/exec_events.rs` at `f8c6026`](https://github.com/openai/codex/blob/f8c6026c38682c628e71d1ae4978ba643499250a/codex-rs/exec/src/exec_events.rs))
  also defines `file_change` and `mcp_tool_call` items, and the command statuses `in_progress`,
  `completed`, `failed` and `declined`: `failed` maps to `ok` false and `declined` to
  `permission_denied`. The [user docs](https://developers.openai.com/codex/noninteractive)
  describe file changes and MCP tool calls in prose, and their sample stream shows only the
  `in_progress` status; the exact identifiers `file_change` and `mcp_tool_call` and the statuses
  `failed` and `declined` come from the CLI source, so the Codex adapter pins them to a recorded
  sample and CLI version.

The adapters themselves are separate roadmap items; this section records the mapping they follow.

## Versioning

A change that removes or renames a field, or changes its meaning, bumps `schema_version`. Older
traces are then re-recorded rather than read with guesses.
