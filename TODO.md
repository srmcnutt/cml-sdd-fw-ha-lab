# Stretched HA lab — task tracker

Legend: `[ ]` not started, `[~]` in progress, `[x]` done, `[!]` blocked.
Update this file as work progresses. Dates are absolute.

Phases 0 to 8 are the original build on CML 2.9.0 (2026-09-08 and 09). Paths in
them are as they were then: the build package was `docs/build-package.md` (now
`spec/intent.md` plus `spec/design.md`), the FMC YAML was `fmc/` (now
`configs/fmc/`), and the test scripts were in `scripts/` (now `tests/`).

## Phase 0 — prerequisites (2026-09-08)
- [x] Read original build package and verify CML platform facts (link conditioning, TRex, FTDv day-0)
- [x] dCloud CML 2.9.0 confirmed: 316 GB RAM, 60 vCPU, nothing running
- [x] FMC 10.0.1 at 198.18.129.31, REST API reachable, evaluation license started (89 days)
- [x] Credentials file `.lab-creds.env` with FMC and CML entries, both logins verified
- [x] CML MCP server registered in `.mcp.json` (pyATS-backed CLI tool available)
- [x] Design review decisions recorded (see build package section 2)
- [x] Restart Claude Code session so the CML MCP server loads

## Phase 1 — documentation
- [x] Rewrite build package to agreed design (`docs/build-package.md`)
- [x] Generate per-device configs into `configs/`
- [x] TRex day-0 switches TRex to ASTF mode at boot (configs/trex/*.node.cfg); profile configs/trex/http_nat.py; control via scripts/trex_run.py

## Phase 2 — CML lab build (no lab created yet)
- [x] Create lab `FW-HA-LAB`
- [x] Create 21 nodes with correct interface counts
- [x] Create 43 links per the link table
- [x] Load day-0 configs (routers, switches, FTD, TRex, Docker), embedded in the import
- [x] Apply link conditioning to the two inter-site trunks (25 ms set, unit to be verified)
- [x] External connector must use `bridge1` (device name, not the label). System Bridge does not reach 198.18.128.0/18

## Phase 3 — management plane and FTD registration
- [x] MGMT-SW, EXT-CONN, all FTDs started; FTD management reaches gateway and FMC
- [x] All four FTDs registered in FMC (7.7.0, health green)
- [x] Licenses assigned at registration (ESSENTIALS, evaluation)

## Phase 4 — FMC configuration (REST API)
- [x] Security zones, network and host objects (re-addressed: enterprise public is 198.51.100.0/24, FTD reserves 203.0.113.0/24 internally)
- [x] Interfaces on the two primaries (FTD-A1, FTD-B2); HA replicates to secondaries
- [x] HA pair A (FTD-A1 primary, FTD-A2 secondary) and pair B (FTD-B2 primary, FTD-B1 secondary): Active/Standby
- [x] Standby addresses, monitored interfaces
- [x] Static routes (default to HSRP VIP, server ranges to TRex)
- [x] NAT policies per pair (static server NAT, interface PAT)
- [x] Access control policy LAB-ACP (permit, log at end of connection)
- [x] Deploy and verify HA state Active/Standby on both pairs

## Phase 5 — network bring-up and verification (pyATS via MCP)
- [x] Routers and switches booted, configs applied (re-addressed once: enterprise public moved to 198.51.100.0/24)
- [x] Verify STP (rapid-pvst), trunks, VLANs on the switches
- [x] Verify BGP sessions and prepend policy (ISP-A prefers East for pair A, West for pair B)
- [x] Verify HSRP groups 10 and 20 active in home site
- [x] Measured inter-site RTT 25 ms with CML latency 11 per direction (CML latency is per direction)
- [x] End-to-end: CLIENT to SRV-A (pair A) and SRV-B (pair B, enters via West) through static NAT; SRV-A outbound via PAT; iperf3 through pair A

## Phase 6 — traffic generation
- [x] TREX-A and TREX-B: ports, gateways, ASTF mode verified from the workstation
- [x] ASTF confirmed through static NAT (NAT translate_hits climbed and flows established in every traffic run)
- [x] iperf3 server on SRV-A and SRV-B; 5 s test run CLIENT to SRV-A OK

## Phase 7 — test scenarios (see build package section 16), runner: scripts/run_test.py
- [x] T1 baseline health (results/T1/): both pairs Active/Standby, ~1.8k TRex flows per pair, iperf3 18 Mbit/s, 25 ms RTT
- [x] T2 planned failover (results/T2/): FMC switch ~5 s, 0 established connections dropped, iperf3 session survived, new connections kept flowing; ~30-40 s throughput dip and TCP retransmits while Snort rebuilt inspection on the new active unit
- [x] T3 state link failure: failover ~5s but session RESET (stateless) — proves the state link preserves sessions
- [x] T4 failover-link-only: NO split-brain (hellos also cross data interfaces); session unaffected — corrects the naive expectation
- [x] T5 full interconnect: split-brain on BOTH pairs at ~17s (the real inter-site-circuit case)
- [x] T6 site failure: pair A -> West in ~1s detect, ~30-40s full recovery, long session held; pair B unaffected
- [x] T7 latency sweep (target RTT ~3/6/10/25/40 ms = CML per-direction settings 0/2/4/11/18, build package Section 13): failover ~5s and session survived at EVERY point — latency up to 40ms does not degrade planned stateful failover
- [x] T8 degraded link 1% and 5% loss: NO false failover at either; sessions held
- [x] T9 router failure: default timers blackhole pair A inbound (no recovery, ~4475 conns lost); FIX = BGP timers 3/9 -> ~16s recovery, ~193 conns lost (BFD alone insufficient). Configs in repo; applied live for the test

## Phase 8 — wrap-up
- [x] Export lab YAML to `lab/topology.exported.yaml` and drift check (scripts/check_drift.py): no drift
- [x] Results in results/RESULTS.md (auto from JSON via scripts/summarize.py); findings folded into the build package

## Phase 9: restructure and retarget at CML 2.10 (started 2026-10-06)
- [x] Fix doc drifts: T4 label in summarize.py; T7 sweep stated as targets and CML settings
- [x] Split the spec into spec/intent.md (what, why, acceptance tests) and spec/design.md (how)
- [x] Move FMC YAML to configs/fmc/, test scripts to tests/; add CLAUDE.md
- [x] .mcp.json points at the CML 2.10 built-in MCP server through mcp-remote
- [ ] Enable virl2-mcp-server on the CML 2.10 controller (Cockpit, Services) and confirm the MCP connection and header names
- [ ] Re-verify the section 2 platform facts on the 2.10 instance; record them in spec/design.md
- [ ] Build on 2.10 (design.md section 17 build sequence) and run T1 to T9
- [ ] tests/summarize.py and tests/check_drift.py; fold findings into the spec
