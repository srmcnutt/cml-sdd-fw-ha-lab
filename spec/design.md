# Design: stretched firewall HA lab

**Purpose:** build a Cisco Modeling Labs (CML) topology that demonstrates
cross-site Active/Standby FTD failover between two colocation sites
separated by a 20 to 25 ms WAN link, so failover behavior can be observed
before the design is committed.

**Audience:** an LLM agent building the CML topology, device configs, FMC
configuration, and test runbook.

**This is the how half of the spec.** The what and why, including the
acceptance tests, are in [`intent.md`](intent.md). This file is a living
document: it is edited in place, and git history keeps every earlier version
(the pre-verification v1 draft is in commit `f5719ed` as
`docs/build-package.v1-original.md`).

**Revision:** v3, 2026-10-06. Restructured into `spec/intent.md` plus this
file, and retargeted at CML 2.10 with its built-in MCP server. The design and
the measured 2026-09-09 results are unchanged from v2 (2026-09-08).

**Training copy.** This is a sanitized copy of a real engagement's build
package. The customer, its sites, and its inventory have been replaced with a
fictional enterprise that has two colocation sites, East and West. Addressing
is documentation or private space throughout. The method, the configuration,
and the measured results are unchanged.

---

## 0. How to read this document

Everything here is **CONFIRMED** (a premise of the scenario this lab models, or
Cisco documentation), **DECIDED** (settled on 2026-09-08; treat as a requirement
for this build), or **PROPOSED** (invented for this build and safe to change).

The authoritative artifact for wiring is **Section 8, the link table**. The
diagrams are the same information in narrative form. If a diagram and the link
table disagree, the link table wins.

**Portability rule.** Every configuration artifact for this lab lives in this
project folder and is pushed to the lab by script. Nothing is typed into a
console by hand. Section 17 defines the repository layout. If it is not in the
repository, it is not part of the lab.

---

## 1. Design intent

Moved to [`intent.md`](intent.md). Read it first: it says what this lab must
show, what is out of scope, and the acceptance tests every build must pass.

---

## 2. Provenance

### CONFIRMED — scenario premises

These are the requirements the lab models. In the original engagement they came
from the customer; here they define a fictional enterprise.

| Item | Value |
| --- | --- |
| Sites | Two colocation sites, East and West |
| Inter-site latency | 20 to 25 ms round trip (a stated design premise) |
| Edge firewall platform | Cisco Secure Firewall 3100 series, Active/Standby pairs |
| Edge routers | Catalyst 8500 series, one per ISP per site, eBGP to ISP, iBGP between the two routers at a site |
| Management | Physical FMC, primary plus backup, outside both sites |
| Design driver | Connection rate and session-table behavior, not raw throughput |

### CONFIRMED — Cisco documentation

| Item | Source |
| --- | --- |
| State link latency: under 10 ms optimal, 250 ms maximum; degradation above 10 ms from retransmission of failover messages | FMC Device Configuration Guide, High Availability |
| Failover link carries: unit state, hello keep-alives, network link status, MAC address exchange, configuration replication and sync, system database updates | FMC / FDM configuration guides |
| State link carries: NAT translation table; TCP and UDP connections and states including HTTP; Snort connection states, inspection results and pin holes; SIP signaling sessions; routing tables (RIB on standby). ICMP and other IP protocols are not parsed and re-establish on the new active unit | FMC / FDM configuration guides |
| If a single switch or inter-switch link carries both failover and data interfaces, a failure of that switch or link makes both units go active | FMC Device Configuration Guide, High Availability |
| FTD failover has no preemption. After a failover the new active unit stays active until another failover event | FMC Device Configuration Guide, High Availability |
| A 10.x management center manages threat defense devices from version 7.3 upward | Secure Firewall Management Center Compatibility Guide |

### CONFIRMED — CML 2.10 MCP server (Cisco documentation)

| Item | Source |
| --- | --- |
| CML 2.10 includes a built-in MCP server, reachable at the `/mcp` URI of the CML server | CML 2.10 docs, MCP Server Overview |
| The `virl2-mcp-server` service is not started by default; an administrator enables and starts it (Cockpit, Services tab) | CML 2.10 docs, MCP Server Overview |
| Clients connect through the `mcp-remote` bridge, which needs Node.js 18 or later (`npx`) | CML 2.10 docs, MCP Server Overview |
| pyATS is bundled, so the `send_cli_command` tool runs CLI commands on virtual devices | CML 2.10 docs, MCP Server Overview |
| The server is based on the open-source `cml-mcp` project | CML 2.10 docs, MCP Server Overview |

### CONFIRMED: CML 2.10 release notes (Cisco, CML 2.10 Release Notes)

| Item | Source |
| --- | --- |
| New API `GET /ai/mcp/configuration` returns the MCP client configuration for AI tools | CML 2.10 Release Notes, New APIs |
| pyATS credentials can be set per image and per node definition instead of defaulting to cisco/cisco; generated pyATS testbeds include a per-node enable password | CML 2.10 Release Notes, Summary of Changes |

### PROPOSED: verify on the CML 2.10 instance before the first build

| Item | Check | Verified |
| --- | --- | --- |
| MCP client config | Compare `.mcp.json` with `GET /api/v0/ai/mcp/configuration`. `.mcp.json` currently assumes `X-Authorization` (CML login) and `X-PyATS-Authorization` (device login), from the upstream `cml-mcp` HTTP client instructions; Cisco's docs do not name the headers. Use Cisco's version if they differ | not yet |
| `send_cli_command` | Listed under the `cml` server in Claude Code's `/mcp`; `show version` on `RTR-1` returns output. Cisco confirms the tool exists; its options are documented only in the upstream README | not yet |
| pyATS device login | IOS XE nodes use `admin` / the secret in `configs/routers/*.cfg`, not cisco/cisco. If `send_cli_command` fails on login, set pyATS credentials for `cat8000v` and `ioll2-xe` in CML | not yet |

### CONFIRMED on CML 2.9.0 — RE-VERIFY on the CML 2.10 instance before building

Everything in this table was verified on 2026-09-08 against a dCloud CML 2.9.0
instance. Treat each row as **PROPOSED** for a CML 2.10 build until it is
checked again on that instance, and record the result here.

| Item | Value |
| --- | --- |
| CML | 2.9.0, dCloud, 316 GB RAM, 60 vCPU, one compute host, nothing else running |
| CML API | `https://198.18.128.2`, admin-capable API account, credentials in `.lab-creds.env` |
| CML MCP server | On 2.9.0: community `cml-mcp[pyats]`. On 2.10: the built-in server above, registered in `.mcp.json` |
| FMC | 10.0.1, external to CML at `198.18.129.31`, REST API enabled, evaluation license active (expires 2026-12-06), no devices or policies configured |
| FTDv image | 7.7.0. Day-0 config supports EULA, hostname, admin password, management IP, FMC IP, registration key, NAT ID. Registration needs no console work |
| FTDv interfaces | `Management0/0`, one reserved unused port, `GigabitEthernet0/0` to `0/7`. Six interfaces must be enabled per node |
| Cat8000v image | 17.16.01a, interfaces `GigabitEthernet1` upward, day-0 via `iosxe_config.txt` |
| IOL-L2 image | XE 17.16.01a, interfaces `Ethernet0/0` to `7/3`, day-0 via `ios_config.txt` |
| TRex image | 2.87 on Alpine. Node definition allows three interfaces only: `eth0` management, `eth1`, `eth2` data |
| Link conditioning | Native, per link, persistent across lab stop/start: latency, jitter, loss, bandwidth |
| External connectors | NAT (`virbr0`), System Bridge (`bridge0` on `ens160`), Bridge 1 (`bridge1` on `ens192`). **Bridge 1 reaches `198.18.128.0/18`**; System Bridge does not. The external connector's configuration must be the device name `bridge1`, not the label (verified 2026-09-08) |

### DECIDED — 2026-09-08 design decisions

1. Separate outside and inside VLANs and prefixes per pair. Pairs never share a VLAN.
2. Inter-site connectivity is two 802.1Q trunks between the site switches with
   CML link conditioning. No WAN simulator node.
3. HA VLANs ride the inside trunk through the switches, mirroring the single
   inter-site circuit. Individual HA VLAN failures are done by pruning the VLAN
   from a trunk.
4. eBGP to both ISPs at both sites, iBGP per site, AS-path prepending so each
   ISP prefers a pair's home site. An ISP-to-ISP eBGP peering stands in for the
   rest of the internet.
5. NAT on the FTD outside interfaces: static NAT for server pools, interface PAT
   for everything else.
6. Documentation ranges for everything internet-routable, RFC 1918 inside.
7. Two TRex nodes, one per pair. Docker Net-Tools nodes provide a visible
   long-lived session.
8. FMC is external to CML. FTD management interfaces reach it through an
   external connector in bridge mode on the dCloud network.
9. All configuration is stored in this repository and pushed by script.

### PROPOSED — change freely

VLAN IDs, specific addresses within the ranges, HSRP group numbers and
priorities, BGP AS numbers, hostnames, switch port assignments, NAT pool sizes,
TRex rates, and the test scenario list beyond T1 through T9.

### OUT OF SCOPE

VPN firewalls, WAN and cloud transit, DDoS scrubbing, load balancers, the site
core, a second FMC, and diverse interconnect paths. A production design has all
of them; they add nothing to a failover demonstration.

---

## 3. Diagram 1 — high level

```
                 ISP-A (AS 64497) <---- eBGP ----> ISP-B (AS 64498)
                  |          |                       |          |
     TREX-A ------+          |                       |          +------ TREX-B
     CLIENT ------+          |                       |          |
                  |          |                       |          |
   +--------------|----------|------+   +------------|----------|--------------+
   |  EAST SITE              |      |   |            |    WEST SITE            |
   |  (AS 64496)             |      |   |            |    (AS 64496)           |
   |  RTR-1 ---iBGP--- RTR-2 |      |   |   RTR-3 ---iBGP--- RTR-4             |
   |     \             /     |      |   |      \             /                 |
   |      SW-OUT-EAST ======================== SW-OUT-WEST  VLAN 100, 200     |
   |       |       |         |      |   |       |       |                      |
   |    FTD-A1   FTD-B1      |      |   |    FTD-A2   FTD-B2                   |
   |    pair A   pair B      |      |   |    pair A   pair B                   |
   |    ACTIVE   standby     |      |   |    standby  ACTIVE                   |
   |       |       |         |      |   |       |       |                      |
   |      SW-IN-EAST  ======================== SW-IN-WEST   VLAN 110, 210,    |
   |       |     |           |      |   |       |     |         900 to 903     |
   |    TREX-A  SRV-A        |      |   |    TREX-B  SRV-B                     |
   +-----------------------------------+   +-----------------------------------+
                        ====== two conditioned trunks, 25 ms RTT ======

   Management (out of band): FTD-x1/x2 Management0/0, TREX-A/B eth0 --> MGMT-SW --> EXT-CONN --> FMC 198.18.129.31
```

---

## 4. Diagram 2 — VLAN and HA detail

```
   EAST                                              WEST

   +-------------+   VLAN 100 outside-A 198.51.100.0/26  +-------------+
   |  FTD-A1     |=======================================|  FTD-A2     |
   |  pair A     |   VLAN 110 inside-A  10.10.0.0/24     |  pair A     |
   |  PRIMARY    |=======================================|  SECONDARY  |
   |  ACTIVE     |   VLAN 900 failover-A 192.168.90.0/30 |  STANDBY    |
   |             |---------------------------------------|             |
   |             |   VLAN 901 state-A    192.168.91.0/30 |             |
   |             |---------------------------------------|             |
   +-------------+                                       +-------------+

   +-------------+   VLAN 200 outside-B 198.51.100.64/26 +-------------+
   |  FTD-B1     |=======================================|  FTD-B2     |
   |  pair B     |   VLAN 210 inside-B  10.20.0.0/24     |  pair B     |
   |  SECONDARY  |=======================================|  PRIMARY    |
   |  STANDBY    |   VLAN 902 failover-B 192.168.92.0/30 |  ACTIVE     |
   |             |---------------------------------------|             |
   |             |   VLAN 903 state-B    192.168.93.0/30 |             |
   |             |---------------------------------------|             |
   +-------------+                                       +-------------+

   Routers RTR-1..4 have a subinterface on VLAN 100 and on VLAN 200.
   HSRP group 10 on VLAN 100: East routers priority high.
   HSRP group 20 on VLAN 200: West routers priority high.
```

**Why separate VLANs per pair.** Each pair is an independent failure domain
with its own gateway, its own public block, and its own inside network. Sharing
a VLAN between pairs would make one pair's ARP, HSRP, and NAT proxy-ARP behavior
visible to the other and would blur the demonstration. This mirrors the
production intent.

**Why four HA VLANs and not two.** A failover link is a point-to-point segment
between the two units of one pair. If pairs A and B shared a failover VLAN, all
four units would see each other's hellos, which breaks the pairing.

**Why failover and state are separate.** Cisco supports combining them. Keeping
them separate lets the state link fail independently of the failover link, which
is what makes T3 and T4 possible.

**Why the HA VLANs ride the inside trunk.** In production every stretched VLAN
rides one inter-site circuit. Cisco documents that a single link carrying both
failover and data makes both units go active when it fails. That is exactly the
production risk the lab exists to show, so it reproduces the risk rather than
designing around it. T5 demonstrates it.

---

## 5. Diagram 3 — connectivity per site

```
   ISP-A ---------------------------- ISP-B           (Cat8000v, one per ISP,
     |  Gi1                        Gi1 |               each with a link to both sites)
   RTR-1 Gi3 --------- Gi3 RTR-2                      (Cat8000v, eBGP up, iBGP across)
     |  Gi2 (trunk 100,200)   Gi2 (trunk 100,200)
   +------------------------------------------------+
   |  SW-OUT-EAST  e0/0   e0/1   e0/2   e0/3   e1/0  |  IOL-L2
   +------------------------------------------------+
                            |      |         \
                     FTD-A1 Gi0/0  FTD-B1 Gi0/0  \___ e1/0 trunk to SW-OUT-WEST (conditioned)
                     (VLAN 100)    (VLAN 200)
                     FTD-A1 Gi0/1  FTD-B1 Gi0/1
                     (VLAN 110)    (VLAN 210)
                     FTD-A1 Gi0/2, Gi0/3 (VLAN 900, 901)
                     FTD-B1 Gi0/2, Gi0/3 (VLAN 902, 903)
                            |      |
   +------------------------------------------------+
   |  SW-IN-EAST e0/0 e0/1 e0/2 e0/3 e1/0 e1/1 e1/2 e1/3 e2/0 |  IOL-L2
   +------------------------------------------------+
                                        |     |      \
                                   TREX-A    SRV-A    \___ e2/0 trunk to SW-IN-WEST (conditioned)
                                   eth2      eth0
                                  (VLAN 110) (VLAN 110)
```

West is the mirror image with RTR-3, RTR-4, SW-OUT-WEST, SW-IN-WEST, FTD-A2,
FTD-B2, TREX-B on VLAN 210, and SRV-B on VLAN 210.

---

## 6. Device inventory

| CML label | Role | Site | Node definition | Interfaces to enable | RAM |
| --- | --- | --- | --- | --- | --- |
| `ISP-A` | Upstream A, AS 64497 | — | `cat8000v` | 5 (Gi1 to Gi5) | 4 GB |
| `ISP-B` | Upstream B, AS 64498 | — | `cat8000v` | 4 (Gi1 to Gi4) | 4 GB |
| `RTR-1` | Edge router, ISP A | East | `cat8000v` | 3 | 4 GB |
| `RTR-2` | Edge router, ISP B | East | `cat8000v` | 3 | 4 GB |
| `RTR-3` | Edge router, ISP A | West | `cat8000v` | 3 | 4 GB |
| `RTR-4` | Edge router, ISP B | West | `cat8000v` | 3 | 4 GB |
| `SW-OUT-EAST` | Outside switch | East | `ioll2-xe` | 8 | under 1 GB |
| `SW-IN-EAST` | Inside switch | East | `ioll2-xe` | 12 | under 1 GB |
| `SW-OUT-WEST` | Outside switch | West | `ioll2-xe` | 8 | under 1 GB |
| `SW-IN-WEST` | Inside switch | West | `ioll2-xe` | 12 | under 1 GB |
| `FTD-A1` | Pair A primary, active | East | `ftdv` | 6 | 8 GB |
| `FTD-B1` | Pair B secondary, standby | East | `ftdv` | 6 | 8 GB |
| `FTD-A2` | Pair A secondary, standby | West | `ftdv` | 6 | 8 GB |
| `FTD-B2` | Pair B primary, active | West | `ftdv` | 6 | 8 GB |
| `TREX-A` | Traffic generator, pair A | — | `trex` | 3 | 4 GB |
| `TREX-B` | Traffic generator, pair B | — | `trex` | 3 | 4 GB |
| `CLIENT` | Internet-side test host | — | `net-tools` | 1 | negligible |
| `SRV-A` | Inside test host, pair A | East | `net-tools` | 1 | negligible |
| `SRV-B` | Inside test host, pair B | West | `net-tools` | 1 | negligible |
| `MGMT-SW` | Management switch | — | `unmanaged_switch` | 8 | none |
| `EXT-CONN` | Bridge to dCloud network | — | `external_connector` | 1 | none |

**21 nodes, about 70 GB RAM, about 36 vCPU.** The host has 316 GB and 60 vCPU.

**Platform substitution.** CML does not simulate Secure Firewall 3100 series or Catalyst 8500
hardware. FTDv and Cat8000v are behavioral stand-ins. Performance numbers from
this lab are meaningless as sizing evidence and must not be presented as such.

---

## 7. VLAN plan

| VLAN | Name | Pair | Prefix | Home site | Trunk |
| --- | --- | --- | --- | --- | --- |
| 100 | `OUTSIDE-A` | A | `198.51.100.0/26` | East | outside trunk |
| 200 | `OUTSIDE-B` | B | `198.51.100.64/26` | West | outside trunk |
| 110 | `INSIDE-A` | A | `10.10.0.0/24` | East | inside trunk |
| 210 | `INSIDE-B` | B | `10.20.0.0/24` | West | inside trunk |
| 900 | `FO-A` | A | `192.168.90.0/30` | stretched | inside trunk |
| 901 | `STATE-A` | A | `192.168.91.0/30` | stretched | inside trunk |
| 902 | `FO-B` | B | `192.168.92.0/30` | stretched | inside trunk |
| 903 | `STATE-B` | B | `192.168.93.0/30` | stretched | inside trunk |

All eight VLANs cross the inter-site trunks. Router-to-switch links are 802.1Q
trunks carrying VLANs 100 and 200. Every FTD, TRex, and server port is an access
port.

---

## 8. Link table

Authoritative wiring list. Interface names are the ones the CML node
definitions present.

### East

| # | A end | A interface | B end | B interface | Carries |
| --- | --- | --- | --- | --- | --- |
| 1 | `ISP-A` | Gi1 | `RTR-1` | Gi1 | eBGP, `203.0.113.0/30` |
| 2 | `ISP-B` | Gi1 | `RTR-2` | Gi1 | eBGP, `203.0.113.8/30` |
| 3 | `RTR-1` | Gi3 | `RTR-2` | Gi3 | iBGP, `10.255.1.0/30` |
| 4 | `RTR-1` | Gi2 | `SW-OUT-EAST` | Ethernet0/0 | 802.1Q trunk, VLAN 100, 200 |
| 5 | `RTR-2` | Gi2 | `SW-OUT-EAST` | Ethernet0/1 | 802.1Q trunk, VLAN 100, 200 |
| 6 | `FTD-A1` | Gi0/0 | `SW-OUT-EAST` | Ethernet0/2 | access VLAN 100, outside-A |
| 7 | `FTD-B1` | Gi0/0 | `SW-OUT-EAST` | Ethernet0/3 | access VLAN 200, outside-B |
| 8 | `FTD-A1` | Gi0/1 | `SW-IN-EAST` | Ethernet0/0 | access VLAN 110, inside-A |
| 9 | `FTD-B1` | Gi0/1 | `SW-IN-EAST` | Ethernet0/1 | access VLAN 210, inside-B |
| 10 | `FTD-A1` | Gi0/2 | `SW-IN-EAST` | Ethernet0/2 | access VLAN 900, pair A failover |
| 11 | `FTD-A1` | Gi0/3 | `SW-IN-EAST` | Ethernet0/3 | access VLAN 901, pair A state |
| 12 | `FTD-B1` | Gi0/2 | `SW-IN-EAST` | Ethernet1/0 | access VLAN 902, pair B failover |
| 13 | `FTD-B1` | Gi0/3 | `SW-IN-EAST` | Ethernet1/1 | access VLAN 903, pair B state |
| 14 | `TREX-A` | eth2 | `SW-IN-EAST` | Ethernet1/2 | access VLAN 110, TRex server side |
| 15 | `SRV-A` | eth0 | `SW-IN-EAST` | Ethernet1/3 | access VLAN 110 |

### West

| # | A end | A interface | B end | B interface | Carries |
| --- | --- | --- | --- | --- | --- |
| 16 | `ISP-A` | Gi2 | `RTR-3` | Gi1 | eBGP, `203.0.113.4/30` |
| 17 | `ISP-B` | Gi2 | `RTR-4` | Gi1 | eBGP, `203.0.113.12/30` |
| 18 | `RTR-3` | Gi3 | `RTR-4` | Gi3 | iBGP, `10.255.2.0/30` |
| 19 | `RTR-3` | Gi2 | `SW-OUT-WEST` | Ethernet0/0 | 802.1Q trunk, VLAN 100, 200 |
| 20 | `RTR-4` | Gi2 | `SW-OUT-WEST` | Ethernet0/1 | 802.1Q trunk, VLAN 100, 200 |
| 21 | `FTD-A2` | Gi0/0 | `SW-OUT-WEST` | Ethernet0/2 | access VLAN 100, outside-A |
| 22 | `FTD-B2` | Gi0/0 | `SW-OUT-WEST` | Ethernet0/3 | access VLAN 200, outside-B |
| 23 | `FTD-A2` | Gi0/1 | `SW-IN-WEST` | Ethernet0/0 | access VLAN 110, inside-A |
| 24 | `FTD-B2` | Gi0/1 | `SW-IN-WEST` | Ethernet0/1 | access VLAN 210, inside-B |
| 25 | `FTD-A2` | Gi0/2 | `SW-IN-WEST` | Ethernet0/2 | access VLAN 900, pair A failover |
| 26 | `FTD-A2` | Gi0/3 | `SW-IN-WEST` | Ethernet0/3 | access VLAN 901, pair A state |
| 27 | `FTD-B2` | Gi0/2 | `SW-IN-WEST` | Ethernet1/0 | access VLAN 902, pair B failover |
| 28 | `FTD-B2` | Gi0/3 | `SW-IN-WEST` | Ethernet1/1 | access VLAN 903, pair B state |
| 29 | `TREX-B` | eth2 | `SW-IN-WEST` | Ethernet1/2 | access VLAN 210, TRex server side |
| 30 | `SRV-B` | eth0 | `SW-IN-WEST` | Ethernet1/3 | access VLAN 210 |

### Inter-site (link conditioning applied here)

| # | A end | A interface | B end | B interface | Carries |
| --- | --- | --- | --- | --- | --- |
| 31 | `SW-OUT-EAST` | Ethernet1/0 | `SW-OUT-WEST` | Ethernet1/0 | 802.1Q trunk, VLAN 100, 200. **25 ms RTT** |
| 32 | `SW-IN-EAST` | Ethernet2/0 | `SW-IN-WEST` | Ethernet2/0 | 802.1Q trunk, VLAN 110, 210, 900 to 903. **25 ms RTT** |

### Internet side

| # | A end | A interface | B end | B interface | Carries |
| --- | --- | --- | --- | --- | --- |
| 33 | `ISP-A` | Gi3 | `TREX-A` | eth1 | `192.0.2.0/29`, TRex client side |
| 34 | `ISP-B` | Gi3 | `TREX-B` | eth1 | `192.0.2.128/29`, TRex client side |
| 35 | `ISP-A` | Gi4 | `ISP-B` | Gi4 | eBGP ISP to ISP, `203.0.113.16/30` |
| 36 | `ISP-A` | Gi5 | `CLIENT` | eth0 | `192.0.2.8/29` |

### Management

| # | A end | A interface | B end | B interface | Carries |
| --- | --- | --- | --- | --- | --- |
| 37 | `FTD-A1` | Management0/0 | `MGMT-SW` | port0 | `198.18.129.41/18` |
| 38 | `FTD-A2` | Management0/0 | `MGMT-SW` | port1 | `198.18.129.42/18` |
| 39 | `FTD-B1` | Management0/0 | `MGMT-SW` | port2 | `198.18.129.43/18` |
| 40 | `FTD-B2` | Management0/0 | `MGMT-SW` | port3 | `198.18.129.44/18` |
| 41 | `TREX-A` | eth0 | `MGMT-SW` | port4 | `198.18.129.45/18` |
| 42 | `TREX-B` | eth0 | `MGMT-SW` | port5 | `198.18.129.46/18` |
| 43 | `EXT-CONN` | port | `MGMT-SW` | port6 | bridge to dCloud `198.18.128.0/18` |

**43 links.** Per-link failures in the test plan use CML's link stop. Per-VLAN
failures use trunk pruning on a switch.

---

## 9. Addressing plan

Documentation ranges for everything internet-routable, RFC 1918 inside.
Management uses the dCloud range because the FMC lives there.

**Why enterprise public space is TEST-NET-2 and not TEST-NET-3.** Threat Defense 7.7
in converged management mode reserves a block inside `203.0.113.0/24` for its
internal management-to-data-plane path, and the FMC refuses any data interface
address that overlaps it (`203.0.113.12/29` on `FTD-A1`, discovered
2026-09-08). So `203.0.113.0/24` is used only on router-to-router links and
`198.51.100.0/24` carries the enterprise public prefixes.

### Blocks

| Block | Range | Use |
| --- | --- | --- |
| TEST-NET-1 | `192.0.2.0/24` | Internet clients. ISP-A side `192.0.2.0/25`, ISP-B side `192.0.2.128/25` |
| TEST-NET-2 | `203.0.113.0/24` | ISP transit links |
| TEST-NET-3 | `198.51.100.0/24` | enterprise public space. Pair A `198.51.100.0/26`, pair B `198.51.100.64/26` |
| RFC 1918 | `10.10.0.0/16` | Pair A inside |
| RFC 1918 | `10.20.0.0/16` | Pair B inside |
| RFC 1918 | `10.255.0.0/24`, `10.255.1.0/30`, `10.255.2.0/30` | Router loopbacks and iBGP links |
| RFC 1918 | `192.168.90.0/30` to `192.168.93.0/30` | HA links |
| dCloud | `198.18.128.0/18`, gateway `198.18.128.1` | Management |

### VLAN 100, outside-A, `198.51.100.0/26`

| Address | Owner |
| --- | --- |
| `.1` | HSRP group 10 VIP, pair A default gateway |
| `.2` `.3` `.4` `.5` | `RTR-1` `RTR-2` `RTR-3` `RTR-4` subinterface Gi2.100 |
| `.10` | Pair A outside, active unit |
| `.11` | Pair A outside, standby unit |
| `.32/28` (`.32` to `.47`) | Static NAT pool for pair A server range |
| `.50` | Static NAT for `SRV-A` |

### VLAN 200, outside-B, `198.51.100.64/26`

| Address | Owner |
| --- | --- |
| `.65` | HSRP group 20 VIP, pair B default gateway |
| `.66` `.67` `.68` `.69` | `RTR-1` `RTR-2` `RTR-3` `RTR-4` subinterface Gi2.200 |
| `.74` | Pair B outside, active unit |
| `.75` | Pair B outside, standby unit |
| `.96/28` (`.96` to `.111`) | Static NAT pool for pair B server range |
| `.114` | Static NAT for `SRV-B` |

### Inside

| Segment | Address | Owner |
| --- | --- | --- |
| VLAN 110 `10.10.0.0/24` | `.1` | Pair A inside, active unit |
| | `.2` | Pair A inside, standby unit |
| | `.50` | `SRV-A`, gateway `.1` |
| | `.129` | `TREX-A` eth2 port address, gateway `.1` |
| Routed via `10.10.0.129` | `10.10.1.0/28` | Pair A TRex server range, `10.10.1.1` to `.14` |
| VLAN 210 `10.20.0.0/24` | `.1` | Pair B inside, active unit |
| | `.2` | Pair B inside, standby unit |
| | `.50` | `SRV-B`, gateway `.1` |
| | `.129` | `TREX-B` eth2 port address, gateway `.1` |
| Routed via `10.20.0.129` | `10.20.1.0/28` | Pair B TRex server range, `10.20.1.1` to `.14` |

TRex only answers ARP for its port address, so the server range sits on its own
prefix and the FTD carries a static route to it via the TRex port. Same pattern
on the client side.

### HA links

| Segment | Primary | Secondary |
| --- | --- | --- |
| VLAN 900 failover-A `192.168.90.0/30` | `FTD-A1` `.1` | `FTD-A2` `.2` |
| VLAN 901 state-A `192.168.91.0/30` | `FTD-A1` `.1` | `FTD-A2` `.2` |
| VLAN 902 failover-B `192.168.92.0/30` | `FTD-B2` `.1` | `FTD-B1` `.2` |
| VLAN 903 state-B `192.168.93.0/30` | `FTD-B2` `.1` | `FTD-B1` `.2` |

### Routers

| Router | Loopback0 | ISP link | iBGP link | Gi2.100 | Gi2.200 |
| --- | --- | --- | --- | --- | --- |
| `RTR-1` | `10.255.0.1/32` | `203.0.113.2/30` to ISP-A `.1` | `10.255.1.1/30` | `198.51.100.2` | `198.51.100.66` |
| `RTR-2` | `10.255.0.2/32` | `203.0.113.10/30` to ISP-B `.9` | `10.255.1.2/30` | `198.51.100.3` | `198.51.100.67` |
| `RTR-3` | `10.255.0.3/32` | `203.0.113.6/30` to ISP-A `.5` | `10.255.2.1/30` | `198.51.100.4` | `198.51.100.68` |
| `RTR-4` | `10.255.0.4/32` | `203.0.113.14/30` to ISP-B `.13` | `10.255.2.2/30` | `198.51.100.5` | `198.51.100.69` |

### ISPs and internet side

| Device | Interface | Address | Notes |
| --- | --- | --- | --- |
| `ISP-A` | Gi1 | `203.0.113.1/30` | to `RTR-1` |
| `ISP-A` | Gi2 | `203.0.113.5/30` | to `RTR-3` |
| `ISP-A` | Gi3 | `192.0.2.1/29` | to `TREX-A` eth1 at `192.0.2.2` |
| `ISP-A` | Gi4 | `203.0.113.17/30` | to `ISP-B` |
| `ISP-A` | Gi5 | `192.0.2.9/29` | to `CLIENT` at `192.0.2.10` |
| `ISP-A` | static | `192.0.2.32/27` via `192.0.2.2` | TRex A client range |
| `ISP-B` | Gi1 | `203.0.113.9/30` | to `RTR-2` |
| `ISP-B` | Gi2 | `203.0.113.13/30` | to `RTR-4` |
| `ISP-B` | Gi3 | `192.0.2.129/29` | to `TREX-B` eth1 at `192.0.2.130` |
| `ISP-B` | Gi4 | `203.0.113.18/30` | to `ISP-A` |
| `ISP-B` | static | `192.0.2.160/27` via `192.0.2.130` | TRex B client range |

### Management

| Device | Address |
| --- | --- |
| FMC | `198.18.129.31` |
| `FTD-A1` | `198.18.129.41/18` |
| `FTD-A2` | `198.18.129.42/18` |
| `FTD-B1` | `198.18.129.43/18` |
| `FTD-B2` | `198.18.129.44/18` |
| `TREX-A` | `198.18.129.45/18` |
| `TREX-B` | `198.18.129.46/18` |
| Gateway | `198.18.128.1` |

---

## 10. Routing design

### BGP

| Item | Value |
| --- | --- |
| Enterprise AS | 64496 |
| ISP-A AS | 64497 |
| ISP-B AS | 64498 |
| eBGP sessions | `RTR-1` to `ISP-A`, `RTR-2` to `ISP-B`, `RTR-3` to `ISP-A`, `RTR-4` to `ISP-B`, `ISP-A` to `ISP-B` |
| iBGP sessions | `RTR-1` to `RTR-2`, `RTR-3` to `RTR-4`, over the Gi3 links, next-hop-self |
| The enterprise advertises | `198.51.100.0/26` and `198.51.100.64/26` from all four edge routers, as connected networks |
| East outbound policy | Prepend `64496 64496 64496` on `198.51.100.64/26` (pair B, West-homed) |
| West outbound policy | Prepend `64496 64496 64496` on `198.51.100.0/26` (pair A, East-homed) |
| ISP-A advertises | `192.0.2.0/25` (aggregate, null route) |
| ISP-B advertises | `192.0.2.128/25` (aggregate, null route) |

Result in steady state: both ISPs deliver pair A traffic to East and pair B
traffic to West. Failing an East router moves pair A's inbound path from
that ISP to West, where it crosses the stretched VLAN 100 to the still-active
`FTD-A1`. That trombone is real production behavior and is what T9 records.

The edge routers need **no routes to the inside networks**. NAT hides them, and
every address the internet talks to is on a connected VLAN.

### HSRP

| Group | VLAN | VIP | `RTR-1` | `RTR-2` | `RTR-3` | `RTR-4` |
| --- | --- | --- | --- | --- | --- | --- |
| 10 | 100 | `198.51.100.1` | 120 | 110 | 100 | 90 |
| 20 | 200 | `198.51.100.65` | 90 | 100 | 110 | 120 |

Preempt on. Timers default. HSRP hellos cross the inter-site trunk, so an
interconnect failure produces dual HSRP actives alongside dual firewall actives.
T5 shows both at once.

**Post-failover tromboning.** After pair A fails over to West, `FTD-A2`
still uses `198.51.100.1`, which stays active in East. All of pair A's egress
then crosses the interconnect until the pair is failed back. There is no
preemption in FTD failover, so it stays that way until someone acts. This is
worth showing, not hiding.

### Static routes on the FTDs

| Pair | Route | Next hop |
| --- | --- | --- |
| A | `0.0.0.0/0` | `198.51.100.1` via outside |
| A | `10.10.1.0/28` | `10.10.0.129` via inside |
| B | `0.0.0.0/0` | `198.51.100.65` via outside |
| B | `10.20.1.0/28` | `10.20.0.129` via inside |

### Spanning tree

IOL-L2 runs PVST+ by default. The outside switches and the inside switches form
two separate layer 2 domains, each spanning both sites over one trunk, so there
is no loop. BPDUs cross the interconnect, which is a production consideration
worth raising in a design review.

---

## 11. NAT design

One NAT policy per pair, assigned to that pair's HA device.

| Pair | Rule | Original | Translated | Direction |
| --- | --- | --- | --- | --- |
| A | Static, server range | `10.10.1.0/28` | `198.51.100.32/28` | bidirectional |
| A | Static, `SRV-A` | `10.10.0.50` | `198.51.100.50` | bidirectional |
| A | Dynamic PAT | any inside-A source | outside interface `198.51.100.10` | inside to outside |
| B | Static, server range | `10.20.1.0/28` | `198.51.100.96/28` | bidirectional |
| B | Static, `SRV-B` | `10.20.0.50` | `198.51.100.114` | bidirectional |
| B | Dynamic PAT | any inside-B source | outside interface `198.51.100.74` | inside to outside |

Static rules go in the manual section before the auto NAT PAT. Proxy ARP stays
enabled on the static rules, so the active unit answers ARP for the translated
addresses on the outside VLAN and the new active takes them over on failover.
The state link replicates the translation table; T3 shows what happens to the
NAT'd sessions when it doesn't.

---

## 12. HA pair configuration

| Setting | Pair A | Pair B |
| --- | --- | --- |
| Primary unit | `FTD-A1` (East) | `FTD-B2` (West) |
| Secondary unit | `FTD-A2` (West) | `FTD-B1` (East) |
| Failover link | Gi0/2, VLAN 900, `192.168.90.1` and `.2` | Gi0/2, VLAN 902, `192.168.92.1` and `.2` |
| State link | Gi0/3, VLAN 901, `192.168.91.1` and `.2` | Gi0/3, VLAN 903, `192.168.93.1` and `.2` |
| Outside | Gi0/0, `198.51.100.10`, standby `.11`, zone `OUTSIDE-A` | Gi0/0, `198.51.100.74`, standby `.75`, zone `OUTSIDE-B` |
| Inside | Gi0/1, `10.10.0.1`, standby `.2`, zone `INSIDE-A` | Gi0/1, `10.20.0.1`, standby `.2`, zone `INSIDE-B` |
| Monitored interfaces | outside, inside | outside, inside |
| Encryption on failover link | off for the baseline | off for the baseline |

Both units of a pair must match on firewall mode (routed), software version
(7.7.0), FMC domain, and NTP. Neither may have DHCP on any interface. All
changes must be deployed before HA will form.

**Timers.** Leave hello and hold timers at defaults for the first run so the
baseline reflects out-of-the-box behavior at 25 ms. Tuning them is a legitimate
mitigation to explore afterward.

**Access control.** A single policy per pair that permits everything and logs
at end of connection, so FMC connection events can be used to count sessions
across a failover.

**Registration.** Each FTD's day-0 config carries the FMC address, a
registration key, and its management addressing. The FMC side of the
registration is done through the REST API. No console work.

---

## 13. WAN latency: link conditioning

CML applies conditioning per link, natively, and the values persist across lab
stop and start. Apply it to links 31 and 32 only.

| Parameter | Baseline | Sweep values |
| --- | --- | --- |
| Latency | set so measured RTT across the trunk is 25 ms | 2, 6, 10, 25, 40 ms RTT |
| Jitter | 0 | 0 |
| Loss | 0% | 1%, 5% |
| Bandwidth | unlimited | unlimited |

**Measured 2026-09-08: CML applies the latency value per direction,** and the
virtual path adds about 1.5 ms each way. Pinging across VLAN 100 from `RTR-4`
to `RTR-1`: a setting of 25 measured 54 ms round trip, 12 measured 27 ms, and
11 measured 25 ms. **The baseline setting is therefore 11**, and the sweep
values map as follows.

| Target RTT | CML latency setting per trunk |
| --- | --- |
| 2 ms | 0 (the path's own overhead is about 3 ms, so 2 ms is not reachable; record the measured floor) |
| 6 ms | 2 |
| 10 ms | 4 |
| 25 ms | 11 |
| 40 ms | 18 |

Re-measure after every change; the mapping is for this host and may differ
elsewhere.

The sweep brackets the design point: 2 and 6 ms represent metro-distance
sites, 10 ms is Cisco's documented "optimal" ceiling, 25 ms is the design
point, 40 ms is headroom.

---

## 14. Traffic generation

### TRex, one node per pair

TRex in CML is limited to two data ports, and TRex pairs ports as client and
server in the order 0 with 1. So each pair gets its own node.

| Node | Port 0 (client), eth1 | Port 1 (server), eth2 | Exercises |
| --- | --- | --- | --- |
| `TREX-A` | on `ISP-A`, port address `192.0.2.2`, gateway `192.0.2.1`, clients `192.0.2.33` to `.62` | on VLAN 110, port address `10.10.0.129`, gateway `10.10.0.1`, servers `10.10.1.1` to `.14` | Pair A via ISP-A, East entry |
| `TREX-B` | on `ISP-B`, port address `192.0.2.130`, gateway `192.0.2.129`, clients `192.0.2.161` to `.190` | on VLAN 210, port address `10.20.0.129`, gateway `10.20.0.1`, servers `10.20.1.1` to `.14` | Pair B via ISP-B, West entry |

**How the node is switched to stateful mode (verified 2026-09-08).** The
CML TRex image regenerates `/etc/trex_cfg.yaml` and launches TRex stateless in
a tmux window on every boot, after the day-0 script has run. So the day-0
`node.cfg` (in `configs/trex/`) sets the management address and launches a
detached job from a script file that waits for the launcher's tmux session,
appends `port_info` gateways to the config, kills the stateless TRex, removes
the stale `/var/run/dpdk` runtime directory (otherwise the next start fails at
EAL init), and respawns the TREX window with `--astf`. Two things learned the
hard way: an extra `/etc/local.d` script written by day-0 never runs on that
boot because the init system lists the scripts before day-0 executes, and a
`pkill -f` pattern inside an inline `sh -c` job matches the job itself.

**Control.** The image has no SSH daemon. TRex is driven from the workstation
over the management network with the TRex 2.87 Python client, vendored under
`vendor/trex-core` and run from a Python 3.10 environment (`.venv-trex`)
because the vendored scapy does not load on newer interpreters. See
`scripts/trex_run.py`.

**Profile.** `configs/trex/http_nat.py`: advanced stateful mode, one HTTP
request and response per connection, then the connection is held open for a
configurable time so that established sessions exist when a failover happens.
Clients target the **public** static NAT addresses (`198.51.100.33` to `.46`
for pair A, `198.51.100.97` to `.110` for pair B). The server side accepts
connections by destination port, which is what lets TRex's stateful mode work
through NAT without a learn mode.

| Parameter | Value |
| --- | --- |
| Connection rate | Start at 500 per second, raise only while stable |
| Concurrent flows | A few thousand held open |
| Flow duration | Long enough to span a failover plus recovery |
| Direction | Bidirectional |

**Long-lived flows matter more than volume.** The question is whether
established sessions survive a failover at 25 ms.

### Docker hosts

| Node | Attached to | Address | Role |
| --- | --- | --- | --- |
| `CLIENT` | `ISP-A` Gi5 | `192.0.2.10/29`, gateway `192.0.2.9` | Runs one long-lived iperf3 session and periodic curl checks |
| `SRV-A` | VLAN 110 | `10.10.0.50/24`, gateway `10.10.0.1` | iperf3 server and HTTP server, public `198.51.100.50` |
| `SRV-B` | VLAN 210 | `10.20.0.50/24`, gateway `10.20.0.1` | iperf3 server and HTTP server, public `198.51.100.114` |

The iperf3 session from `CLIENT` to `SRV-A` is the thing an observer watches
during a failover. It either keeps counting or it resets.

### Measurement

For each run record from TRex and from FMC connection events:

- Active flow count before, during, and after failover
- TCP errors and retransmissions during the transition
- Time from trigger to traffic recovery
- Whether flows opened before the failover were still open after it
- Whether the `CLIENT` iperf3 session survived

The fourth item is the headline number.

---

## 15. Management plane

- `MGMT-SW` is an unmanaged switch. `EXT-CONN` is an external connector in
  bridge mode with configuration `bridge1` (Bridge 1, the CML host's second
  NIC), which is the connector that carries `198.18.128.0/18` on this dCloud
  instance. Verified 2026-09-08: with System Bridge nothing answered; with
  `bridge1` every management address answered from the dCloud VPN and the FTD
  reached its gateway and the FMC.
- FTD management addressing is in Section 9. Gateway `198.18.128.1`.
- TRex management ports are on the same segment so TRex can be driven from the
  dCloud workstation over SSH as well as from the CML console.
- Docker hosts have no management address. They are driven through the CML
  console.
- The FMC's own management of the standby units crosses no conditioned link,
  which matches an out-of-band FMC in production.

---

## 16. Test mechanics

The acceptance tests, with their Given / When / Then and the findings, are in
[`intent.md`](intent.md). This table says only how `tests/run_test.py` applies
each trigger. Every run restores the baseline before and after, runs TRex on
both pairs and the `CLIENT` iperf3 session, and saves `results/<ID>/<timestamp>.json`.

| ID | Mechanism in the lab |
| --- | --- |
| T1 | Nothing failed; snapshots only |
| T2 | FMC REST: switch active on pair A |
| T3 | Prune VLAN 901 from `SW-IN-EAST` trunk Ethernet2/0, then (with `--then-failover`) switch active |
| T4 | Prune VLAN 900 from `SW-IN-EAST` trunk Ethernet2/0 |
| T5 | CML: stop links 31 and 32 |
| T6 | CML: stop nodes `FTD-A1` and `FTD-B1` |
| T7 | CML conditioning on links 31 and 32 at per-direction settings 0, 2, 4, 11, 18 (target RTTs about 3, 6, 10, 25, 40 ms; section 13), then T2 |
| T8 | CML conditioning on links 31 and 32: latency 11 plus 1%, then 5%, loss |
| T9 | CML: stop node `RTR-1`. Variants: `--tag bfd` (BFD lines applied live) and `--tag timers` (BGP 3/9 timers) |

Capture for every run: failover detection time, total convergence time,
session survival, iperf3 outcome, and drop reasons on the unit that became active.

---

## 17. Repository layout and build sequence

### Layout

```
cml-sdd-fw-ha-lab/
  README.md                start here
  CLAUDE.md                standing rules Claude Code loads every session
  HOW-IT-WORKS.md          walkthrough of the method for readers new to the project
  TODO.md                  build log and task tracker
  spec/
    intent.md              what and why, acceptance tests T1 to T9, findings
    design.md              this document: the how
  lab/
    topology.yaml          nodes, interfaces, links, positions, conditioning (source)
    FW-HA-LAB.cml.yaml     rendered import file; generated, never edited by hand
    state/                 ids of the live lab (git-ignored)
  configs/
    routers/ switches/ ftd/ trex/ docker/   day-0 configs per node
    fmc/                   zones, objects, devices, HA pairs, NAT, access policy (YAML)
  tests/
    run_test.py            runs one acceptance test (T1 to T9) and records JSON
    run_all.sh             runs T3 to T9 back to back
    summarize.py           results/T*/*.json -> results/RESULTS.md
    check_drift.py         exports the live lab and diffs it against the rendered file
  results/                 JSON and logs per run, RESULTS.md, written-up report, figures
  scripts/                 build tooling: lablib, render_lab, build_lab, push_configs,
                           fmc_apply, console, trex_run, apply_bfd_live
  vendor/                  TRex 2.87 client library (see vendor/README.md)
  .mcp.json                CML 2.10 built-in MCP server registration for Claude Code
  .lab-creds.env.example   template for .lab-creds.env (never committed)
  requirements*.txt        Python 3.14 for the scripts, Python 3.10 for the TRex client
```

### Operating the lab

All commands run from the repository root. `PY=.venv/bin/python`, and for
the TRex client `PYT="env TREX_EXT_LIBS=$PWD/vendor/trex-ext-libs .venv-trex/bin/python"`.

| Task | Command |
| --- | --- |
| Re-render the CML lab file after editing a config | `$PY scripts/render_lab.py` |
| Import into a fresh CML (or `--replace` an existing lab) | `$PY scripts/build_lab.py` |
| Refresh `lab/state/ids.json` for an existing lab | `$PY scripts/build_lab.py --record-only` |
| Re-push a node's day-0 (stop, wipe, load, start) | `$PY scripts/push_configs.py RTR-1 SW-IN-EAST` |
| FMC, one step or several, idempotent | `$PY scripts/fmc_apply.py objects acp register interfaces deploy ha standby routes nat deploy` |
| FMC state | `$PY scripts/fmc_apply.py status` |
| Any node console | `$PY scripts/console.py FTD-A1 --login 'admin:...' --prompt '(?m)^> ?$' -- 'show failover'` |
| TRex status, start, stats, stop | `$PYT scripts/trex_run.py status` / `start A 50 90` / `stats A` / `stop A` |
| Run an acceptance test | `$PYT tests/run_test.py T2 --pair A --hold 120` |
| Put the lab back to baseline | `$PYT tests/run_test.py restore` |
| Rebuild the results table | `$PY tests/summarize.py` |
| Drift check against the live lab | `$PY tests/check_drift.py` |

### Build sequence

1. Re-verify the CML 2.10 platform facts in section 2 on the target instance
   (node definitions and interface names, day-0 file names, external connector,
   latency mapping) and record the results there.
2. `render_lab.py`, then `build_lab.py`: create the lab, nodes, links, and
   day-0 configs. Apply conditioning. Do not start anything.
3. Start `MGMT-SW`, `EXT-CONN`, `FTD-A1`. Confirm it reaches the FMC. If not,
   switch `EXT-CONN` to the other bridge.
4. Start the remaining FTDs. `fmc_apply.py` registers all four and waits.
5. `fmc_apply.py` continues: objects, interfaces, HA pairs, routes, NAT, access
   policy, deploy. Confirm both pairs show Active/Standby.
6. Start routers, switches, TRex, Docker hosts. Verify through the MCP server's
   `send_cli_command`: trunks, spanning tree, BGP, HSRP, measured RTT,
   end-to-end reachability through NAT.
7. Start TRex and the iperf3 session. Run T1.
8. Run T2 through T9 with `tests/run_test.py`, one at a time.
9. `tests/summarize.py`, then `tests/check_drift.py`. Fold any finding back
   into `intent.md` or this file.

---

## 18. Constraints and open items

1. **Resolved 2026-09-08:** the external connector must use `bridge1`. On
   another CML instance this must be re-verified; the topology source carries
   it as `config_inline` on `EXT-CONN`.
2. **Resolved 2026-09-08:** CML link conditioning latency is per direction.
   Setting 11 on each trunk measures 25 ms round trip. See Section 13.
3. **Not verified:** TRex stateful mode through static NAT on this image.
   Resolved on the first traffic run. Fallback is the Docker hosts alone, which
   still answer the session survival question.
4. **Not verified:** the 20 to 25 ms figure is a design premise. In a real
   engagement, confirm it against the circuit provider's SLA.
4a. **FMC health shows red for the FMC itself,** because the dCloud FMC cannot
   reach Cisco's Security Intelligence feeds, the Talos agent, or NTP. The FTDs
   are green. Ignore the FMC-level alerts during the demo or disable the feeds.
5. **Lab results are behavioral, not performance.** FTDv on CML says nothing
   about hardware throughput or session capacity. Do not present lab numbers as
   sizing data.
6. **Diverse paths not modeled.** Everything crosses two trunks that fail
   together in T5, which mirrors a single inter-site circuit. If diverse circuits are
   procured, a follow-up build with the HA VLANs on a separate
   conditioned path is worthwhile.
7. **Naming.** When presenting results, avoid calling this
   "active/active." Use "dual-site failover pairs" or "split Active/Standby."
8. **FMC evaluation license** expires 2026-12-06. The lab must be finished, or
   re-licensed, before then.
9. **CML 2.10 retarget (2026-10-06):** the platform facts in section 2 were
   verified on CML 2.9.0. Re-verify them on the 2.10 instance before the first
   build, and confirm the `.mcp.json` header names on first connect.
