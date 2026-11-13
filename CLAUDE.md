# ccdeck

One Python file (`ccdeck`, standard library only) plus `web/`. Tests: `python3 -m unittest discover -s tests` (also run them with `CCDECK_NO_PROC=1`, the macOS code path). Bump `VERSION` in `ccdeck` and `.claude-plugin/plugin.json` together in every release.

## PR screenshots

PRs that change what the dashboard shows get before/after screenshots, made with the `pr-screenshots` skill (dev-core plugin). The project-specific parts:

- **Demo data:** `scripts/demo_data.py <dir> --pid <pid>` writes a made-up HOME: sessions in every state, hook state, marks, and a fake `gh` in `<dir>/bin` for PR states and review requests. Nothing in it is real, so images are safe to publish. Add a session there when a change needs a case it doesn't cover. Never use real names, repos or tickets.
- **Run:**
  ```bash
  <skill>/scripts/before-after.sh --spec scripts/shots/<topic>.json --base origin/main [--head origin/<branch>] \
    --prepare 'python3 scripts/demo_data.py {data} --pid $SHOTS_KEEPER_PID' \
    --serve 'HOME={data} PATH={data}/bin:$PATH CCDECK_AUTOSTART=0 CCDECK_NOTIFY=0 python3 ccdeck serve --port {port}'
  ```
  The fake `gh` answers within a second, so the defaults are enough. No login is needed.
- **Specs** live in `scripts/shots/`. `states-pr.json` is an example.
- **Selectors:**
  - cards and rows have `data-sid` (the demo ids are `d-deploy`, `d-auth`, `d-queue`, `d-flaky`, `d-csv`, `d-rate`, `d-pdf`, `d-node`, `d-dark`, `d-cache`, `d-badges`, `d-bun` and `d-tz`);
  - the Needs-you queue buttons have `data-nav`;
  - pills have `data-g` (group) and `data-k` (state);
  - the drawer is `.drawer`, and its sections are `.dsec`.
- **Upload:** `SHOTS_REPO=slonik923/ccdeck`, the repo's current name, because the origin remote may still use the old `cc-dashboard` name.
