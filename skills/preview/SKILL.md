---
name: preview
description: Try an unreleased version of ccdeck (a PR number, branch or commit) on your own sessions, next to your normal dashboard. Use when the user wants to see a ccdeck PR or change before it's merged or released.
disable-model-invocation: true
argument-hint: "<PR number | branch | stop>"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/ccdeck *)
---

!`python3 ${CLAUDE_PLUGIN_ROOT}/ccdeck preview $ARGUMENTS 2>&1`

Tell the user, in one or two short lines, the preview URL printed above (or the problem it reports), and that `/ccdeck:preview stop` stops it. Don't do anything else.
