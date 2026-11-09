---
name: done
description: Mark the current Claude Code session as done in ccdeck, with an optional note (e.g. /ccdeck:done merged in #42).
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/ccdeck *)
argument-hint: "[note]"
---

!`python3 ${CLAUDE_PLUGIN_ROOT}/ccdeck done ${CLAUDE_SESSION_ID} $ARGUMENTS 2>&1`

Confirm to the user in one short line what the output above says. Don't do anything else.
