# Stretched firewall HA — CML lab (training copy)

A Cisco Modeling Labs (CML) lab that demonstrates cross-site Active/Standby
Secure Firewall (FTD) failover between two colocation sites, East and West,
separated by a 25 ms WAN. Two FTDv pairs are each split across both sites. The
lab answers one question: does stateful failover preserve sessions at that
latency, and where does the design actually break?

This is a **sanitized copy of a real engagement**, kept as a teaching example.
The customer, its sites, and its inventory have been replaced with a fictional
enterprise, and every address is documentation or private space. The method,
the configuration, the code, and the measured results are unchanged.

**Everything here is repo-driven and portable.** Device configs are files under
`configs/`, the topology is `lab/topology.yaml`, and scripts render, import,
configure, and test the lab through the CML and FMC REST APIs. Nothing is typed
into a console by hand. The lab was built and tested by an LLM agent (Claude
Code) working from the build package, with a CML MCP server for lab control.

## Where to start

| Read | For |
| --- | --- |
| [`docs/HOW-IT-WORKS.md`](docs/HOW-IT-WORKS.md) | The method: how the files, scripts, and APIs fit together, and what was learned the hard way |
| [`docs/build-package.md`](docs/build-package.md) | The source of truth: design, link table, addressing, FMC configuration, test plan, platform quirks |
| [`results/RESULTS.md`](results/RESULTS.md) | The measured results, one row per scenario, generated from the run data |
| [`results/results.html`](results/results.html) | The same results written up for a design review (also as `results/failover-lab-results.docx`) |
| [`TODO.md`](TODO.md) | The build log, phase by phase |

## Layout

```
docs/                       build package (source of truth), its v1 draft, and the HOW-IT-WORKS walkthrough
lab/topology.yaml           topology source: nodes, interfaces, links, positions, link conditioning
lab/FW-HA-LAB.cml.yaml      rendered CML import file (generated, configs embedded; do not edit)
configs/                    per-device day-0 configs (routers, switches, ftd, trex, docker)
fmc/                        FMC objects, access policy, devices, HA pairs, NAT (YAML)
scripts/                    render, build, push, fmc_apply, console, trex_run, run_test, summarize, check_drift
vendor/                     TRex 2.87 client library (see vendor/README.md)
results/                    per-scenario JSON and logs, RESULTS.md, the written-up report and its figures
.lab-creds.env.example      template for .lab-creds.env: FMC and CML credentials (never committed)
.mcp.json                   CML MCP server registration for Claude Code
requirements*.txt           the two Python environments (scripts on 3.14, TRex client on 3.10)
```

## Prerequisites

- A CML 2.9 instance with the node definitions this lab uses: `cat8000v`,
  `ioll2-xe`, `ftdv` (7.7), `trex`, `net-tools`, `unmanaged_switch`,
  `external_connector`. The lab was built on a Cisco dCloud instance; the
  management addressing (`198.18.128.0/18`) and the `bridge1` external
  connector assume that environment and are the first things to change elsewhere.
- An FMC 7.x/10.x reachable from the FTD management segment, REST API enabled,
  evaluation or Smart licensing active.
- `uv` for the two Python environments, and `uvx` on `PATH` if you use the CML
  MCP server from Claude Code (`.mcp.json` sources `.lab-creds.env`).

## Stand it up

```sh
uv venv -p 3.14 .venv && uv pip install -p .venv/bin/python -r requirements.txt
uv venv -p 3.10 .venv-trex && uv pip install -p .venv-trex/bin/python -r requirements-trex.txt
cp .lab-creds.env.example .lab-creds.env         # then fill in the real values
.venv/bin/python scripts/render_lab.py           # topology.yaml + configs -> lab/FW-HA-LAB.cml.yaml
.venv/bin/python scripts/build_lab.py            # import into CML, record ids in lab/state/ids.json
# start MGMT-SW, EXT-CONN (bridge1), the four FTDs; then:
.venv/bin/python scripts/fmc_apply.py objects acp register interfaces deploy ha standby routes nat deploy
# start routers, switches, TRex, docker hosts (push_configs.py --all, or the CML UI)
```

See the operating-command table in the build package (section 17) for the full
set, including how to drive any node console from a script.

## Run the tests

```sh
export TREX_EXT_LIBS=$PWD/vendor/trex-ext-libs
.venv-trex/bin/python scripts/run_test.py T2 --pair A       # one scenario
./scripts/run_all.sh                                        # T3..T9 in sequence
.venv/bin/python scripts/summarize.py                       # rebuild results/RESULTS.md
.venv/bin/python scripts/check_drift.py                     # confirm the live lab still matches the repo
```

`run_test.py` needs `lab/state/ids.json` from `build_lab.py` and the TRex
client environment; it restores the baseline before and after every scenario.

## Adapting it

- **Lab name:** change `lab.title` in `lab/topology.yaml`; the rendered file
  name and every script follow it.
- **Passwords and keys:** the FTD admin password lives in
  `configs/ftd/*.day0.json` (`run_test.py` reads it from there), the router
  secret in `configs/routers/*.cfg`, and the FMC registration key in
  `fmc/devices.yaml`, which must match `FmcRegKey` in the day-0 files.
- **Addressing and VLANs:** the build package section 9 is the plan; the
  configs, `fmc/*.yaml`, `scripts/run_test.py` (public test addresses), and
  `scripts/trex_run.py` (client and server ranges) carry the values.

## Caveat

FTDv on CML is a behavioral stand-in for a hardware Secure Firewall. Timings and
session counts here answer "does it work and where does it degrade," never "how
fast is the firewall." Do not present lab numbers as sizing evidence, and avoid
calling the design "active/active"; it is split Active/Standby.
