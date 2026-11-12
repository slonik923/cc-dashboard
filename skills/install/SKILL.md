---
name: install
description: Install the ccdeck background service (starts the dashboard at login) and the `ccdeck` terminal command. The plugin already provides the hooks, so this skips them.
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/ccdeck *)
---

!`python3 ${CLAUDE_PLUGIN_ROOT}/ccdeck install --no-hooks 2>&1`

Summarize the output above for the user in two or three short lines: whether the background service is running and the dashboard address, and, if it says `~/.local/bin` is not on PATH, the one line they can add to their shell profile. Don't run anything else.
