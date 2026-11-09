---
name: dashboard
description: Open the ccdeck dashboard of all local Claude Code sessions in the browser. Use when the user asks to see their sessions, what needs them, or the ccdeck dashboard.
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/ccdeck *)
---

!`python3 ${CLAUDE_PLUGIN_ROOT}/ccdeck open 2>&1`

Tell the user, in one short line, the dashboard URL printed above (or the problem it reports). Don't do anything else.
