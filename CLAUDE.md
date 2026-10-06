# Rules for Claude Code in this repository

Read `spec/intent.md`, then `spec/design.md`, before changing anything.

## The three rules
1. **The repository is the lab.** Every device config, the topology, the link
   conditioning, and the FMC policy live in files. If a value is not in the
   repository, it is not part of the lab. Never type configuration into a
   console or GUI by hand.
2. **Scripts are idempotent and talk to APIs.** Re-running any step must be safe.
   Use the scripts in `scripts/` and `tests/`; extend them rather than working around them.
3. **Every test run restores the baseline and records everything.** Results are
   generated from `results/T*/*.json` by `tests/summarize.py`, never typed.

## Evidence
- Every fact in the spec is CONFIRMED, DECIDED, or PROPOSED (`spec/design.md`
  section 0). Do not change CONFIRMED or DECIDED items without asking. PROPOSED
  items are yours to change; say what you changed.
- Verify platform facts against the live CML instance before relying on them,
  and write what you verified back into `spec/design.md` section 2 with the date.
- When a test contradicts an expectation, record the finding in
  `spec/intent.md` and fix the spec, not just the config.

## Tools
- The CML 2.10 built-in MCP server is registered in `.mcp.json` as `cml`. Use it
  to inspect the lab and to run show commands (`send_cli_command`). Build and
  test through the scripts, so the run is repeatable without the agent.
- Credentials live in `.lab-creds.env` (git-ignored). Never print them or commit them.

## Words
- Call the design "split Active/Standby" or "dual-site failover pairs," never "active/active."
- Lab numbers are behavioral evidence, never sizing or performance evidence.

## Housekeeping
- Track work in `TODO.md`, phase by phase, with the evidence next to each item.
- After changing configs: `scripts/render_lab.py`, then `tests/check_drift.py` against the live lab.
