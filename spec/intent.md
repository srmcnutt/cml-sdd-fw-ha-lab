# Intent: stretched firewall HA lab

This is the **what and why** half of the spec. The **how** (topology, addressing,
device and FMC configuration, test mechanics) is in [`design.md`](design.md).
If the two disagree, fix the disagreement before building; do not guess.

Every statement in the spec carries one of three tags, defined in `design.md`
section 0: **CONFIRMED** (a scenario premise or Cisco documentation),
**DECIDED** (settled; treat as a requirement), **PROPOSED** (safe to change).

## Why this lab exists

A design puts two Cisco Secure Firewall (FTD) Active/Standby failover pairs
across two colocation sites, East and West, 20 to 25 ms apart (CONFIRMED premise).
Before buying hardware, the design owner needs to **observe**, not argue:

1. Does stateful failover preserve established sessions at that latency?
2. Where does the design actually break?

## What the network must do

- **Pair A:** active unit in East, standby in West; fronts the East-homed services.
- **Pair B:** active unit in West, standby in East; fronts the West-homed services.
- Each site backs up the other, and both sites carry live traffic in steady
  state. This is active/active at the *site* level only; each pair is standard
  Active/Standby. Call it "split Active/Standby" or "dual-site failover pairs,"
  never "active/active."
- **Not clustering** (CONFIRMED): the cluster control link needs under 20 ms
  round trip and these sites measure 20 to 25 ms.
- Each pair has its own VLANs and prefixes (DECIDED). Because a pair's two
  units sit in different buildings, its outside, inside, failover, and state
  VLANs are stretched over the inter-site layer 2 interconnect.
- Inbound traffic for each pair prefers that pair's home site and moves to the
  other site when the home site cannot carry it (DECIDED, via BGP AS-path prepending).

## Out of scope

VPN firewalls, WAN and cloud transit, DDoS scrubbing, load balancers, the site
core, a second FMC, and diverse interconnect paths. A production design has all
of them; they add nothing to a failover demonstration.

## Acceptance tests

Each test runs under traffic (TRex on both pairs plus one long-lived iperf3
session) at the 25 ms baseline unless noted. How each trigger is applied is in
`design.md` section 16; the runner is `tests/run_test.py <ID>`. **Finding** lines
record what the lab showed on 2026-09-09 (CML 2.9.0, FTDv 7.7, FMC 10.0.1); the
data is in `results/`. Lab results are behavioral, never sizing evidence.

| ID | Given | When | Then (expected) |
| --- | --- | --- | --- |
| T1 | Both pairs Active/Standby, BGP and HSRP converged | Nothing fails | Both pairs stay Active/Standby; state sync current; measured inter-site RTT is 25 ms |
| T2 | Pair A active in East, traffic flowing | FMC switches the active unit of pair A | Failover completes; established sessions survive; new connections keep flowing |
| T3 | Pair A healthy, traffic flowing | The state link (VLAN 901) is lost, then a failover is triggered | The pair stays paired but loses state sync; after failover, sessions reset (stateless) |
| T4 | Pair A healthy, traffic flowing | Only the failover link (VLAN 900) is lost | The standby keeps hearing the active over the monitored data interfaces; no split-brain |
| T5 | Both pairs healthy | The whole inter-site interconnect is lost | Split-brain on both pairs, plus dual HSRP actives: the inter-site-circuit risk, made visible |
| T6 | Both pairs healthy | Both East firewalls power off | Pair A fails over to West; pair B is unaffected; recovery time recorded |
| T7 | Pair A healthy | T2 is repeated at target RTTs of about 3, 6, 10, 25, and 40 ms | Record where behavior visibly degrades, if anywhere |
| T8 | Both pairs healthy | 25 ms plus 1%, then 5%, loss on the interconnect | No false failovers; state sync health and session survival recorded |
| T9 | Pair A active in East, inbound via RTR-1 | Edge router RTR-1 fails | Inbound traffic for pair A moves to West; outage time recorded |

### Findings that changed the spec

- **T4** (2026-09-09): the original expectation was split-brain. The lab showed
  none, because FTD also sends failover hellos over the monitored data
  interfaces. The expectation above was corrected; split-brain needs the data
  path to fail too (T5).
- **T9** (2026-09-09): with default eBGP timers the ISP kept forwarding to the
  dead router and pair A's inbound traffic blackholed for the whole window; the
  firewall never failed over because it was healthy. BFD on eBGP alone did not
  fix it. Aggressive BGP timers (`timers bgp 3 9`) on every eBGP and iBGP
  session cut the outage to about 16 s. This is now a **design requirement**:
  cross-site firewall HA must be paired with fast routing failure detection.
- **T7** (2026-09-09): failover took about 5 s and sessions survived at every
  point up to about 40 ms RTT.
