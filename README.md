# cml-sdd-fw-ha-lab: stretched firewall HA, built from a spec

A Cisco Modeling Labs (CML) lab that demonstrates cross-site Active/Standby
Secure Firewall (FTD) failover between two colocation sites, East and West,
separated by a 25 ms WAN. Two FTDv pairs are each split across both sites. The
lab answers one question: does stateful failover preserve sessions at that
latency, and where does the design actually break?

It is the large demo for the Cisco U. Spotlight session *Spec-Driven Network
Design with Cisco Modeling Labs*. Its small companion,
[`cml-sdd-starter-lab`](../cml-sdd-starter-lab), uses the same layout.

This is a **sanitized copy of a real engagement**. The customer, its sites, and
its inventory are replaced with a fictional enterprise, and every address is
documentation or private space. The method, configuration, code, and measured
results are unchanged.

## How it is organized

The lab is built by Claude Code from a written spec, through the CML 2.10
built-in MCP server and the CML and FMC REST APIs. Nothing is typed into a
console by hand.

| Path | What it is |
| --- | --- |
| `CLAUDE.md` | Rules Claude Code loads every session |
| `spec/intent.md` | What and why, plus the acceptance tests T1 to T9 and what they found |
| `spec/design.md` | The how: topology, link table, addressing, FMC config, test mechanics |
| `lab/topology.yaml` | The lab as code; rendered to `lab/FW-HA-LAB.cml.yaml` |
| `configs/` | Day-0 configs per node, and `configs/fmc/` for the FMC policy |
| `tests/` | The test runner, the results summarizer, and the drift check |
| `results/` | Generated: JSON per run, `RESULTS.md`, and the written-up report |
| `scripts/` | Build tooling: render, import, push configs, FMC apply, console, TRex |
| `HOW-IT-WORKS.md` | A walkthrough of the method and what was learned the hard way |
| `TODO.md` | The build log, phase by phase |

## Prerequisites

- **CML 2.10** with the `virl2-mcp-server` service enabled and started
  (Cockpit, Services tab; it is off by default), and the node definitions this
  lab uses: `cat8000v`, `ioll2-xe`, `ftdv`, `trex`, `net-tools`,
  `unmanaged_switch`, `external_connector`.
- **An FMC 7.x or 10.x** reachable from the FTD management segment, REST API
  enabled, evaluation or Smart licensing active.
- **Claude Code**, **Node.js 18 or later** (for `mcp-remote`), and **uv** for the
  two Python environments.
- The management addressing (`198.18.128.0/18`) and the `bridge1` external
  connector assume a Cisco dCloud instance. They are the first things to change
  elsewhere (`spec/design.md` sections 2 and 9).

## Stand it up

```sh
uv venv -p 3.14 .venv && uv pip install -p .venv/bin/python -r requirements.txt
uv venv -p 3.10 .venv-trex && uv pip install -p .venv-trex/bin/python -r requirements-trex.txt
cp .lab-creds.env.example .lab-creds.env         # fill in the real values
claude                                           # then: /mcp to confirm the cml server is connected
```

Then follow the build sequence in `spec/design.md` section 17, or ask Claude
Code to do it: it will read `CLAUDE.md` and the spec first.

## Run the acceptance tests

```sh
export TREX_EXT_LIBS=$PWD/vendor/trex-ext-libs
.venv-trex/bin/python tests/run_test.py T2 --pair A     # one test
./tests/run_all.sh                                      # T3 to T9 in sequence
.venv/bin/python tests/summarize.py                     # rebuild results/RESULTS.md
.venv/bin/python tests/check_drift.py                   # live lab still matches the repo?
```

## Caveat

FTDv on CML is a behavioral stand-in for a hardware Secure Firewall. Results
answer "does it work and where does it degrade," never "how fast is the
firewall." Do not present lab numbers as sizing evidence, and do not call the
design "active/active"; it is split Active/Standby.

The results in `results/` were measured on CML 2.9.0 (2026-09-09). The repo
now targets CML 2.10; see `TODO.md` Phase 9 for what must be re-verified there.
