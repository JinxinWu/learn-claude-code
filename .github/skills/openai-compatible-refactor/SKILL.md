---
name: openai-compatible-refactor
description: 'Refactor Anthropic-style agent loops to OpenAI-compatible chat completions. Use when migrating client initialization, tools schema, tool-call parsing, env vars, and validation steps for Python agent scripts.'
argument-hint: 'Target file(s) and desired compatibility provider (OpenAI/DeepSeek/Kimi/etc.)'
---

# OpenAI-Compatible Refactor

Migrate a Python agent loop from Anthropic-style messages API to OpenAI-compatible chat-completions API with minimal behavior change.

## When to Use

- Existing code uses Anthropic SDK patterns (`client.messages.create`, `tool_use`, `tool_result`).
- Runtime fails with provider mismatch (for example 404 on Anthropic endpoint shape).
- You want to keep the same agent behavior but switch to OpenAI-compatible endpoints.

## Inputs to Collect

- Target script path(s).
- Current provider and endpoint behavior.
- Desired environment variables (`OPENAI_API_KEY`, optional `OPENAI_BASE_URL`, `MODEL_ID`).
- Validation expectation (compile check only vs compile + runtime smoke test).

## Procedure

1. Inspect current call shape and tool loop.
- Locate SDK client initialization.
- Locate request call and stop condition logic.
- Locate tool schema and tool result append format.

2. Switch client initialization to OpenAI-compatible SDK.
- Replace Anthropic client setup with `OpenAI(...)`.
- Require `OPENAI_API_KEY`.
- Pass optional `OPENAI_BASE_URL` for compatible providers.

3. Convert tool schema to OpenAI function tools.
- Use `tools=[{"type":"function","function":{...}}]`.
- Keep tool names stable to avoid dispatch regressions.
- Keep JSON schema strict enough for required fields.

4. Convert loop response handling.
- Call `client.chat.completions.create(...)`.
- Read `response.choices[0].message`.
- Preserve assistant message in history.
- If no `tool_calls`, return final text.
- For each tool call:
- Parse `tool_call.function.arguments` as JSON.
- Execute local handler.
- Append `{"role":"tool","tool_call_id":...,"content":...}`.

5. Update docs/config surface.
- Update `.env.example` to OpenAI-compatible env vars.
- Update dependency list to include `openai` package.
- Keep existing model/env naming conventions unless intentionally changed.

6. Validate with fast checks.
- Compile check target scripts.
- Optional smoke test with dummy key and immediate exit path.
- Confirm no syntax errors introduced.

7. Keep readability high during edits.
- Preserve or improve blank-line layout: separate imports, globals, classes, and functions with clear spacing.
- Keep one logical step per short block inside long functions to avoid dense unreadable chunks.
- Add concise Chinese comments at key control points (request call, tool parsing, permission/guard branches, tool result injection).
- Do not add noisy comments for obvious assignments; comments should explain intent and decision points.

## Decision Points

- If multiple scripts share the same loop pattern:
- Apply the same migration in each file, or create a shared adapter module first.
- If provider supports both APIs:
- Prefer chat-completions for widest compatibility unless project standard says otherwise.
- If tool argument JSON is frequently malformed:
- Add explicit parse errors and structured fallback messages.

## Completion Criteria

- Agent loop runs with OpenAI-compatible request shape.
- Tool calls execute and tool outputs are re-injected correctly.
- Environment variables and dependencies are aligned with new client.
- Target files pass compile checks.
- Updated files keep good blank-line style and are easier to scan than before.
- Key logic paths include clear Chinese comments for maintainers.

## Common Pitfalls

- Keeping Anthropic-style tool schema (`input_schema`) after switching SDK.
- Forgetting to append `role=tool` messages with correct `tool_call_id`.
- Updating code but not `.env.example` / dependency files.
- Assuming schema guarantees perfect tool arguments; always validate at runtime.
- Over-compressing code into long blocks with poor spacing after refactor.
- Adding too many low-value comments instead of focused Chinese intent comments.

## Suggested Command Prompts

- `/openai-compatible-refactor migrate agents/s02_tool_use.py to OpenAI-compatible endpoints`
- `/openai-compatible-refactor refactor all agents s01-s05 and keep behavior unchanged`
- `/openai-compatible-refactor only update env/deps/docs after code migration`
