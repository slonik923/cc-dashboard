---
name: park
description: Park the current Claude Code session in ccdeck (set it aside for later), with an optional note.
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/ccdeck *)
argument-hint: "[note]"
---

!`python3 ${CLAUDE_PLUGIN_ROOT}/ccdeck park ${CLAUDE_SESSION_ID} $ARGUMENTS 2>&1`

Confirm to the user in one short line what the output above says. Don't do anything else.
