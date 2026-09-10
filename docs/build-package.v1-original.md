# Stretched firewall HA — CML build package

**Purpose:** build a Cisco Modeling Labs topology that demonstrates cross-site
Active/Standby FTD failover between two colocation sites separated by a
20 to 25 ms WAN link, so failover behavior can be observed before the design
is committed.

**Audience:** an LLM agent building the CML topology and device configs.

**Note:** this is the pre-verification draft (v1), kept so Section 2 of the v2
build package can be read against it. It is sanitized the same way as v2.

---

## 0. How to read this document

Everything here is either **CONFIRMED** (a premise of the scenario, or taken from
Cisco documentation) or **PROPOSED** (invented for this build and safe to change).
Section 2 lists which is which. Do not treat proposed values as requirements.

The authoritative artifact for wiring is **Section 8, the link table**. The three
diagram sections are the same information in narrative form for context. If the
link table and a diagram disagree, the link table wins.

---

## 1. Design intent

Two colocation sites, East and West. Two FTD Active/Standby failover pairs,
each split across both sites:

- **Pair A** — active unit in East, standby unit in West
- **Pair B** — active unit in West, standby unit in East

Both sites carry live traffic because each hosts one pair's active unit. This is
often described as "active/active dual site." It is active/active at the
*site* level only. Each individual pair is standard Active/Standby failover.
**Do not model this as clustering.** Clustering was ruled out because the cluster
control link requires under 20 ms round trip and these sites measure 20 to 25 ms.

Because the units of a pair are in different buildings, their data interfaces must
share subnets across sites. That means the transit (outside) VLAN and the inside
VLAN are both stretched over the inter-site layer 2 link, alongside the dedicated
failover and state links. In production this is a colocation layer 2 interconnect.
In CML it is a WAN simulator node.

**What this build is for:** proving failover timing, session preservation, and
split-brain behavior at realistic latency. Everything else is scenery.

---

## 2. Provenance

### CONFIRMED — scenario premises

| Item | Value |
| --- | --- |
| Sites | Two colocation sites, East and West |
| Inter-site latency | 20 to 25 ms round trip (a stated design premise) |
| Edge firewall platform | Cisco Secure Firewall 3100 series, Active/Standby pairs |
| Edge routers | Catalyst 8500 series, one per ISP per site, eBGP to ISP, iBGP between them |
| Management | Physical FMC, primary plus backup |
| Design driver | Connection rate and session-table behavior, not raw throughput |

### CONFIRMED — Cisco documentation

| Item | Source |
| --- | --- |
| State link latency: under 10 ms optimal, 250 ms maximum; degradation above 10 ms from retransmission of failover messages | FMC Device Configuration Guide 7.6, High Availability |
| Failover link carries: unit state, hello keep-alives, network link status, MAC address exchange, configuration replication and sync, system database updates (VDB and rules, not geolocation or Security Intelligence) | FMC / FDM configuration guides |
| State link carries: NAT translation table; TCP and UDP connections and states including HTTP; Snort connection states, inspection results and pin holes; SIP signaling sessions; static and dynamic routing tables (RIB on standby). ICMP and other IP protocols are not parsed and re-establish on the new active unit | FMC / FDM configuration guides |
| If a single switch or inter-switch link carries both failover and data interfaces, a failure of that switch or link makes both units go active | FMC Device Configuration Guide, High Availability |

### PROPOSED — invented for this build, change freely

VLAN IDs, IP addressing, HSRP group numbers, device hostnames, interface
assignments, BGP AS numbers, and the test scenario list. None of these are
scenario premises.

### OUT OF SCOPE for this build

VPN firewalls, WAN and cloud transit, DDoS scrubbing, and load balancers. They
exist in the production design but add nothing to a failover demonstration and
are omitted to keep the node count down.

---

## 3. Diagram 1 — high level

```
                    ISP A                                ISP B
                      |                                    |
        +-------------|-------------+       +--------------|------------+
        |   EAST SITE               |       |   WEST SITE               |
        |                           |       |                           |
        |   FTD-A1  (pair A active) |<===== 900/901 =====>| FTD-A2  (pair A standby) |
        |                           |       |                           |
        |   FTD-B1  (pair B standby)|<===== 902/903 =====>| FTD-B2  (pair B active)  |
        |                           |       |                           |
        +---------------------------+       +---------------------------+
                      \                                    /
                       \      colocation L2 interconnect  /
                        \======  20 to 25 ms RTT  ========/
                                 (WAN simulator in CML)
```

Each site is independently connected to the internet and to its own core. The
interconnect carries the stretched data VLANs and all four HA VLANs.

---

## 4. Diagram 2 — VLAN and HA detail

```
   EAST                                          WEST

   +-------------+                                  +-------------+
   |  FTD-A1     |---- VLAN 900 (failover) ---------|  FTD-A2     |
   |  pair A     |---- VLAN 901 (state) ------------|  pair A     |
   |  ACTIVE     |                                  |  STANDBY    |
   +-------------+                                  +-------------+
         |                                                 |
         |          +-----------------------------+        |
         +----------|  VLAN 100 transit (stretched)|-------+
         +----------|  all four outside interfaces |-------+
         |          +-----------------------------+        |
         |                                                 |
   +-------------+                                  +-------------+
   |  FTD-B1     |---- VLAN 902 (failover) ---------|  FTD-B2     |
   |  pair B     |---- VLAN 903 (state) ------------|  pair B     |
   |  STANDBY    |                                  |  ACTIVE     |
   +-------------+                                  +-------------+
         |                                                 |
         |          +-----------------------------+        |
         +----------|  VLAN 110 inside (stretched) |-------+
                    |  all four inside interfaces  |
                    +-----------------------------+
```

**Why four HA VLANs and not two.** A failover link is a point-to-point segment
between the two units of one pair. If pairs A and B shared VLAN 900, all four
units would sit in the same failover broadcast domain and see each other's hellos,
which breaks the pairing. Each pair gets its own failover VLAN and its own state
VLAN.

**Why failover and state are separate.** Cisco supports combining them onto a
single link per pair. Keeping them separate is deliberate here: it allows the
state link to be failed independently of the failover link, which is what makes
test scenarios T3 and T4 (Section 13) possible.

---

## 5. Diagram 3 — connectivity

Per site, top to bottom:

```
                    +-----------------+
                    |      TREX       |  client ports
                    +--------+--------+
                       |           |
   ISP A ----------- (p0)         (p1) ----------- ISP B
     |                                                |
   RTR-1 -------------------------------------------- RTR-2
     |                                                |     (Cat 8500, eBGP up, iBGP across)
   +--------------------------------------------------------+
   |                   OUTSIDE SWITCH                        |   (VLAN 100)
   +--------------------------------------------------------+
     |                                                |
   FTD-x1                                          FTD-y1        (two firewalls, one per pair)
     |                                                |
   +--------------------------------------------------------+
   |                   INSIDE SWITCH                         |   (VLAN 110)
   +--------------------------------------------------------+
                              |
                       TREX server port
```

Both outside switches, both inside switches, and all four firewalls connect to the
WAN simulator, which is the only path between the two sites.

A single TRex node sits outside the sites. Its client ports attach to `ISP-A` and
`ISP-B`; its server ports attach to the inside switch at each site. Generated HTTP
flows therefore traverse the full path: ISP, router, outside switch, firewall,
inside switch. See Section 12.

---

## 6. Device inventory

| CML node name | Role | Site | Suggested CML image | Notes |
| --- | --- | --- | --- | --- |
| `RTR-1` | Edge router, ISP A | East | Cat8000v | Stands in for Catalyst 8500 |
| `RTR-2` | Edge router, ISP B | East | Cat8000v | |
| `RTR-3` | Edge router, ISP A | West | Cat8000v | |
| `RTR-4` | Edge router, ISP B | West | Cat8000v | |
| `SW-OUT-EAST` | Outside switch | East | IOSv-L2 or unmanaged switch | VLAN 100 |
| `SW-IN-EAST` | Inside switch | East | IOSv-L2 or unmanaged switch | VLAN 110 |
| `SW-OUT-WEST` | Outside switch | West | IOSv-L2 or unmanaged switch | VLAN 100 |
| `SW-IN-WEST` | Inside switch | West | IOSv-L2 or unmanaged switch | VLAN 110 |
| `FTD-A1` | Pair A active | East | FTDv | |
| `FTD-B1` | Pair B standby | East | FTDv | |
| `FTD-B2` | Pair B active | West | FTDv | |
| `FTD-A2` | Pair A standby | West | FTDv | |
| `WANSIM` | Inter-site link | — | Linux (Alpine or Ubuntu) with `tc netem` | See Section 11 |
| `ISP-A` | Upstream A | — | Cat8000v or IOSv | Simulated transit |
| `ISP-B` | Upstream B | — | Cat8000v or IOSv | Simulated transit |
| `TREX` | Traffic generator | — | Ubuntu with TRex, 4 interfaces | HTTP load; see Section 12 |
| `FMC` | Management | — | FMCv | Optional; see note below |

**Total: 17 nodes** (16 if the FMC is omitted).

**On FMC.** The production design uses a physical FMC pair. In CML, one FMCv can
manage all four FTDv units, which is enough to configure and demonstrate failover.
If FMCv is unavailable or too heavy for the lab, FDM on-box management can
configure Active/Standby failover, but note that FDM-managed HA is configured per
pair and some FMC-specific behaviors will not be demonstrable. FMCv is preferred.

**On platform substitution.** CML does not simulate Secure Firewall 3100 series hardware.
FTDv is the correct stand-in for behavior testing. Performance numbers from the
lab are meaningless and must not be presented as sizing evidence.
Same for Cat8000v standing in for Catalyst 8500.

---

## 7. VLAN plan

| VLAN | Name | Scope | Purpose |
| --- | --- | --- | --- |
| 100 | `TRANSIT` | Stretched, both sites | Firewall outside interfaces, router-facing, HSRP |
| 110 | `INSIDE` | Stretched, both sites | Firewall inside interfaces, core-facing |
| 900 | `FO-PAIR-A` | Stretched, both sites | Pair A failover link |
| 901 | `STATE-PAIR-A` | Stretched, both sites | Pair A stateful failover link |
| 902 | `FO-PAIR-B` | Stretched, both sites | Pair B failover link |
| 903 | `STATE-PAIR-B` | Stretched, both sites | Pair B stateful failover link |

All six VLANs traverse the WAN simulator. This is deliberate and mirrors the
production risk: in the real build, all of this rides one inter-site circuit unless
diverse paths are procured.

---

## 8. Link table

This is the authoritative wiring list. Interface names are **proposed** and must be
adjusted to whatever the chosen CML images actually present.

### East

| # | A end | A interface | B end | B interface | Carries |
| --- | --- | --- | --- | --- | --- |
| 1 | `ISP-A` | Gi1 | `RTR-1` | Gi1 | eBGP, ISP A transit |
| 2 | `ISP-B` | Gi1 | `RTR-2` | Gi1 | eBGP, ISP B transit |
| 3 | `RTR-1` | Gi3 | `RTR-2` | Gi3 | iBGP peering |
| 4 | `RTR-1` | Gi2 | `SW-OUT-EAST` | Gi0/1 | VLAN 100 access |
| 5 | `RTR-2` | Gi2 | `SW-OUT-EAST` | Gi0/2 | VLAN 100 access |
| 6 | `FTD-A1` | Gi0/0 | `SW-OUT-EAST` | Gi0/3 | VLAN 100 access (outside) |
| 7 | `FTD-B1` | Gi0/0 | `SW-OUT-EAST` | Gi0/4 | VLAN 100 access (outside) |
| 8 | `FTD-A1` | Gi0/1 | `SW-IN-EAST` | Gi0/1 | VLAN 110 access (inside) |
| 9 | `FTD-B1` | Gi0/1 | `SW-IN-EAST` | Gi0/2 | VLAN 110 access (inside) |
| 10 | `FTD-A1` | Gi0/2 | `WANSIM` | eth1 | VLAN 900, pair A failover |
| 11 | `FTD-A1` | Gi0/3 | `WANSIM` | eth2 | VLAN 901, pair A state |
| 12 | `FTD-B1` | Gi0/2 | `WANSIM` | eth3 | VLAN 902, pair B failover |
| 13 | `FTD-B1` | Gi0/3 | `WANSIM` | eth4 | VLAN 903, pair B state |
| 14 | `SW-OUT-EAST` | Gi0/8 | `WANSIM` | eth5 | VLAN 100 trunk, stretched |
| 15 | `SW-IN-EAST` | Gi0/8 | `WANSIM` | eth6 | VLAN 110 trunk, stretched |

### West

| # | A end | A interface | B end | B interface | Carries |
| --- | --- | --- | --- | --- | --- |
| 16 | `ISP-A` | Gi2 | `RTR-3` | Gi1 | eBGP, ISP A transit |
| 17 | `ISP-B` | Gi2 | `RTR-4` | Gi1 | eBGP, ISP B transit |
| 18 | `RTR-3` | Gi3 | `RTR-4` | Gi3 | iBGP peering |
| 19 | `RTR-3` | Gi2 | `SW-OUT-WEST` | Gi0/1 | VLAN 100 access |
| 20 | `RTR-4` | Gi2 | `SW-OUT-WEST` | Gi0/2 | VLAN 100 access |
| 21 | `FTD-A2` | Gi0/0 | `SW-OUT-WEST` | Gi0/3 | VLAN 100 access (outside) |
| 22 | `FTD-B2` | Gi0/0 | `SW-OUT-WEST` | Gi0/4 | VLAN 100 access (outside) |
| 23 | `FTD-A2` | Gi0/1 | `SW-IN-WEST` | Gi0/1 | VLAN 110 access (inside) |
| 24 | `FTD-B2` | Gi0/1 | `SW-IN-WEST` | Gi0/2 | VLAN 110 access (inside) |
| 25 | `FTD-A2` | Gi0/2 | `WANSIM` | eth7 | VLAN 900, pair A failover |
| 26 | `FTD-A2` | Gi0/3 | `WANSIM` | eth8 | VLAN 901, pair A state |
| 27 | `FTD-B2` | Gi0/2 | `WANSIM` | eth9 | VLAN 902, pair B failover |
| 28 | `FTD-B2` | Gi0/3 | `WANSIM` | eth10 | VLAN 903, pair B state |
| 29 | `SW-OUT-WEST` | Gi0/8 | `WANSIM` | eth11 | VLAN 100 trunk, stretched |
| 30 | `SW-IN-WEST` | Gi0/8 | `WANSIM` | eth12 | VLAN 110 trunk, stretched |

**30 links, 12 interfaces on the WAN simulator.** If the simulator node cannot
present 12 interfaces, collapse the four HA links per site onto one trunked
interface per site and carry VLANs 900 through 903 as tagged subinterfaces. This
reduces the simulator to 6 interfaces at the cost of not being able to fail the
state link independently of the failover link, which breaks test scenarios T3 and
T4. Prefer 12 discrete interfaces if the platform allows.

### Traffic generation

| # | A end | A interface | B end | B interface | Carries |
| --- | --- | --- | --- | --- | --- |
| 31 | `TREX` | p0 (client) | `ISP-A` | Gi3 | HTTP client traffic, ISP A path |
| 32 | `TREX` | p1 (client) | `ISP-B` | Gi3 | HTTP client traffic, ISP B path |
| 33 | `TREX` | p2 (server) | `SW-IN-EAST` | Gi0/5 | HTTP server side, East |
| 34 | `TREX` | p3 (server) | `SW-IN-WEST` | Gi0/5 | HTTP server side, West |

**34 links total.** See Section 12 for why TRex needs server-side ports and not
just the two ISP-side connections.

---

## 9. Addressing plan (proposed)

Documentation ranges only. Substitute real space if it is available.

| Segment | Subnet | Notes |
| --- | --- | --- |
| VLAN 100 transit | `203.0.113.0/25` | TEST-NET-3, stands in for enterprise public space |
| VLAN 110 inside | `10.10.0.0/24` | |
| VLAN 900 pair A failover | `192.168.90.0/30` | |
| VLAN 901 pair A state | `192.168.91.0/30` | |
| VLAN 902 pair B failover | `192.168.92.0/30` | |
| VLAN 903 pair B state | `192.168.93.0/30` | |
| ISP A transit links | `198.51.100.0/30`, `198.51.100.4/30` | TEST-NET-2 |
| ISP B transit links | `198.51.100.8/30`, `198.51.100.12/30` | |
| TRex client pool, ISP A | `198.51.100.128/26` | Simulated internet clients |
| TRex client pool, ISP B | `198.51.100.192/26` | Simulated internet clients |
| TRex server pool | `10.10.0.128/25` | Simulated inside web servers, VLAN 110 |

| Device | VLAN 100 address | VLAN 110 address |
| --- | --- | --- |
| `RTR-1` | `203.0.113.2` | — |
| `RTR-2` | `203.0.113.3` | — |
| `RTR-3` | `203.0.113.4` | — |
| `RTR-4` | `203.0.113.5` | — |
| HSRP group 10 VIP | `203.0.113.1` | — |
| HSRP group 20 VIP | `203.0.113.6` | — |
| `FTD-A1` / `FTD-A2` (pair A) | `203.0.113.10` | `10.10.0.10` |
| `FTD-B1` / `FTD-B2` (pair B) | `203.0.113.11` | `10.10.0.11` |

A failover pair shares one address per interface; the active unit owns it. Assign
standby addresses from the same subnets (for example `203.0.113.20` and
`203.0.113.21`) so both units are reachable for monitoring.

**HSRP design (proposed).** VLAN 100 is stretched, so all four routers share one
layer 2 domain. Run two HSRP groups on it:

- **Group 10**, VIP `203.0.113.1`, priority high on `RTR-1` and `RTR-2` (East).
  Pair A's default gateway.
- **Group 20**, VIP `203.0.113.6`, priority high on `RTR-3` and `RTR-4` (West).
  Pair B's default gateway.

This keeps each active firewall pointed at a local gateway in steady state. A
single HSRP group would be simpler to build but would permanently send one site's
egress traffic across the interconnect.

**Note this creates a second split-brain surface.** HSRP hellos cross the WAN
simulator. An interconnect failure can produce dual HSRP actives and dual firewall
actives simultaneously. That interaction is worth demonstrating, see test T5.

---

## 10. HA pair configuration

Configure both pairs as standard Active/Standby failover.

| Setting | Pair A | Pair B |
| --- | --- | --- |
| Primary unit | `FTD-A1` (East) | `FTD-B2` (West) |
| Secondary unit | `FTD-A2` (West) | `FTD-B1` (East) |
| Failover link | `Gi0/2`, VLAN 900 | `Gi0/2`, VLAN 902 |
| State link | `Gi0/3`, VLAN 901 | `Gi0/3`, VLAN 903 |
| Monitored interfaces | outside (`Gi0/0`), inside (`Gi0/1`) | same |

Both units of a pair must match on: firewall mode (routed), software version, FMC
domain or group, and NTP configuration. Neither may have DHCP or PPPoE on any
interface. Configuration changes must be fully deployed before HA will form.

**Timers.** Leave hello and hold timers at defaults for the first test run so the
baseline reflects out-of-the-box behavior at 25 ms. Tuning them is a legitimate
mitigation to explore afterward, but establish the default baseline first so the
results show an honest starting point.

---

## 11. WAN simulator

The simulator sits between the two sites and is the only cross-site path.

**Baseline:** 25 ms round trip, no loss.

**Required capabilities:**

1. Adjustable one-way delay (12.5 ms each direction for a 25 ms RTT baseline)
2. Adjustable packet loss
3. Ability to drop individual links, not just the whole node

**Implementation.** A CML unmanaged switch will not inject latency. Use a Linux
node bridging the interfaces with `tc netem` applied per interface, for example:

```
tc qdisc add dev eth1 root netem delay 12.5ms
tc qdisc change dev eth1 root netem delay 12.5ms loss 1%
tc qdisc del dev eth1 root
```

Bridge the paired interfaces (eth1 with eth7 for VLAN 900, eth2 with eth8 for
VLAN 901, and so on) and apply netem symmetrically on both members of each pair.

**Verify before building:** confirm the CML version in use supports a Linux node
with enough interfaces, and confirm `tc netem` is present in the chosen image. I
have not verified either. If the platform cannot do per-interface delay, an
external hardware impairment generator is the alternative.

**Latency sweep values for testing:** 2 ms and 6 ms (metro-distance sites),
10 ms (Cisco's documented "optimal" ceiling), 25 ms (the actual design point),
and 40 ms (headroom test).

---

## 12. Traffic generation (TRex)

One TRex node generates the load the firewalls inspect. Without it, the failover
tests measure nothing: an idle firewall pair fails over instantly and preserves
zero sessions, which proves nothing about the design.

### Why four ports and not two

TRex emulates both ends of a flow. Connecting it only to `ISP-A` and `ISP-B` gives
it clients with nowhere to talk to, because the firewalls route inbound traffic to
the inside network, not back out the other ISP. So TRex needs server-side ports on
the inside of each site:

- **p0, p1 (client side)** attach to `ISP-A` and `ISP-B`, emulating internet clients
- **p2, p3 (server side)** attach to the inside switch at each site, emulating web
  servers behind the firewalls

Each generated flow crosses the full path under test: ISP, edge router, outside
switch, firewall, inside switch. That is what makes session counts meaningful.

**Two-port alternative.** If node interfaces are scarce, run TRex with p0 on
`ISP-A` and p1 on `SW-IN-EAST` only. You lose the ability to drive both ISP paths
simultaneously, which matters for tests that involve one router or one ISP failing,
but the core failover tests still work.

### Profile

Keep it simple. TRex ASTF mode with a basic HTTP profile is sufficient: short
request and response, one transaction per connection, so connection setup and
teardown dominate. This exercises the metric that actually matters here,
which is connection rate and session table behavior, rather than raw throughput.

| Parameter | Value | Rationale |
| --- | --- | --- |
| Mode | ASTF | Stateful; needed for real TCP sessions that can be counted across a failover |
| Profile | HTTP simple (`astf/http_simple.py` or equivalent) | Ships with TRex; no custom profile work |
| Connection rate | Start low, e.g. 500 to 1,000 new connections/sec | Raise only until the topology is stable; CML is not a performance platform |
| Concurrent flows | Target a few thousand held open | Enough to make session survival visible and countable |
| Duration | Long enough to span a failover event plus recovery | Failover mid-run is the whole point |
| Direction | Bidirectional | Client to server and back |

**Long-lived flows matter more than volume.** The question being tested is whether
established sessions survive a failover at 25 ms. Configure the profile to hold
connections open across the failover window rather than churning them, or the
result will look like success regardless of what the state link did.

### Measurement

For each test run, record from TRex:

- Active flow count before, during, and after failover
- TCP connection errors and retransmissions during the transition
- Time from failover trigger to traffic recovery
- Whether flows open before the failover were still open after it

That last one is the headline number. It is the direct answer to
whether cross-site stateful failover works at this latency.

### Caveats

- **Not verified:** whether the CML version in use offers a TRex node definition,
  and whether a plain Ubuntu node in CML can run TRex acceptably. TRex normally
  expects DPDK-capable interfaces; in a virtual lab it may fall back to a software
  mode with much lower performance. Confirm before building.
- **Rates are not sizing evidence.** Whatever connection rate TRex sustains against
  FTDv on CML says nothing about a Secure Firewall 3100 series. Use TRex output to answer
  "did sessions survive," never "how fast is the firewall."

---

## 13. Test scenarios

Run each with TRex traffic active at the 25 ms baseline unless noted.

| ID | Scenario | Method | What to observe |
| --- | --- | --- | --- |
| T1 | Baseline health | Both pairs formed and stable, traffic flowing through both active units | HA state converged, no flapping, state sync current |
| T2 | Planned failover | Manual failover of pair A from FMC | Failover time, whether established sessions survive, traffic re-convergence |
| T3 | State link failure | Drop VLAN 901 only, leave 900 up | Pair should stay paired but lose state sync; a subsequent failover should drop sessions. This demonstrates the difference between stateful and stateless failover |
| T4 | Failover link failure | Drop VLAN 900 only, leave data interfaces up | **Split-brain test.** Both units are expected to go active. Record how long it takes, what an operator would see, and whether any mechanism resolves it |
| T5 | Full interconnect failure | Drop all WAN simulator links at once | Simultaneous firewall split-brain and HSRP split-brain. The realistic inter-site-circuit-failure case |
| T6 | Site failure | Power off both East firewalls | Pair A fails over to West; pair B unaffected. Measure recovery |
| T7 | Latency sweep | Repeat T2 at 2, 6, 10, 25, and 40 ms | Where does failover behavior visibly degrade? This directly answers why 25 ms is different from a metro-distance site |
| T8 | Degraded link | 25 ms plus 1% then 5% loss | The realistic WAN failure mode, which is degradation rather than a clean break. Watch for false failovers |

**T4, T5, T7, and T8 are the ones that matter for the design conversation.** T7
in particular converts an abstract argument into a chart. If failover behavior is
clean at 25 ms, that is a real result and should be reported honestly. If it
degrades, the sweep shows exactly where.

Capture for every run: failover detection time, total convergence time, session
survival count, and any log or syslog evidence of the transition.

---

## 14. Constraints and open items

1. **Not verified:** CML support for a 12-interface Linux node and `tc netem`
   availability in the chosen image.
2. **Not verified:** TRex node availability in this CML version, and whether it
   runs acceptably without DPDK-capable interfaces. See Section 12 caveats.
3. **Not verified:** the 20 to 25 ms figure is a design premise and has not
   been confirmed against a circuit provider's SLA.
4. **Lab results are behavioral, not performance.** FTDv on CML says nothing about
   hardware throughput or session capacity, and TRex connection rates in this lab are
   not a firewall benchmark. Do not present lab numbers as sizing data.
5. **Diverse paths not modeled.** Cisco documentation recommends failover links and
   data interfaces travel different paths. This build deliberately funnels
   everything through one simulator because that mirrors the single inter-site
   circuit. If diverse circuits are procured, a second simulator node modeling
   an independent path is a worthwhile follow-up build.
6. **Scope.** No WAN or cloud transit, no VPN firewalls, no DDoS scrubbing, no load balancers.
   Adding them expands the build without improving the failover demonstration.
7. **Naming.** When presenting results, avoid calling this
   "active/active." Use "dual-site failover pairs" or "split Active/Standby."
   Calling it active/active invites confusion with clustering, which was ruled out.
