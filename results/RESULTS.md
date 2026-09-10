# Stretched HA — test results

Behavioral results from FTDv on CML. Not performance or sizing evidence.

| Scenario | Trigger | HA pre→post | Failover detect | Dual-active | Est. conns dropped | iperf3 survived | TRex flows pre→post |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T1 | none (baseline) | Acti/Stan→Acti/Stan | — | no | 0 | — | 1141→1869 |
| T2 | FMC planned failover, pair A | Acti/Stan→Stan/Acti | 5.2s | no | 0 | — | 1265→2552 |
| T3 | drop state VLAN 901, then failover | Acti/Stan→Stan/Acti | 4.8s | no | 0 | no | 1250→3601 |
| T4 | drop failover VLAN 900 (split-brain) | Acti/Stan→Acti/Fail | — | no | 0 | yes | 1278→2607 |
| T5 | stop both inter-site trunks | Acti/Stan→Fail/Acti | 16.8s | YES | 0 | yes | 1359→2622 |
| T6 | power off both East firewalls | Acti/Stan→Fail/Acti | 1.2s | YES | 324 | yes | 1288→3609 |
| T7 @lat0 | planned failover at a swept latency | Acti/Stan→Stan/Acti | 4.6s | no | 0 | yes | 1127→2183 |
| T7 @lat11 | planned failover at a swept latency | Acti/Stan→Stan/Acti | 4.6s | no | 0 | yes | 1106→2199 |
| T7 @lat18 | planned failover at a swept latency | Acti/Stan→Stan/Acti | 4.7s | no | 0 | yes | 1098→2206 |
| T7 @lat2 | planned failover at a swept latency | Acti/Stan→Stan/Acti | 4.8s | no | 0 | yes | 1112→2192 |
| T7 @lat4 | planned failover at a swept latency | Acti/Stan→Stan/Acti | 4.6s | no | 0 | yes | 1114→2200 |
| T8 @1.0%loss | inter-site loss, observe | Acti/Stan→Acti/Stan | — | no | 0 | yes | 1286→2624 |
| T8 @5.0%loss | inter-site loss, observe | Acti/Stan→Acti/Stan | — | no | 0 | yes | 1277→2559 |
| T9 | power off RTR-1 | Acti/Stan→Acti/Stan | — | no | 4475 | yes | 1334→180 |
| T9 [bfd] | power off RTR-1 | Acti/Stan→Acti/Stan | — | no | 2653 | yes | 1263→180 |
| T9 [timers] | power off RTR-1 | Acti/Stan→Acti/Stan | — | no | 193 | yes | 1274→2466 |

## Drop reasons on the unit that became active

**T2**
- FTD-A1: Interface is down=70, Dst MAC L2 Lookup Failed=1
- FTD-A2: First TCP packet not SYN=4213, Interface is down=9, Blocked or blacklisted by the stream preprocessor=1

**T3**
- FTD-A1: Interface is down=85, Dst MAC L2 Lookup Failed=4
- FTD-A2: First TCP packet not SYN=4704, Interface is down=7, TCP failed 3 way handshake=6, TCP RST/FIN out of order=4

**T4**
- FTD-A1: First TCP packet not SYN=1852, TCP failed 3 way handshake=3

**T5**
- FTD-A1: First TCP packet not SYN=3133
- FTD-A2: Interface is down=3

**T6**
- FTD-A2: First TCP packet not SYN=88, TCP failed 3 way handshake=26, TCP RST/FIN out of order=7, Blocked or blacklisted by the stream preprocessor=4

**T7 @lat0**
- FTD-A1: Interface is down=15, Dst MAC L2 Lookup Failed=2
- FTD-A2: First TCP packet not SYN=322, Interface is down=9

**T7 @lat11**
- FTD-A1: Interface is down=68
- FTD-A2: First TCP packet not SYN=320, Interface is down=9

**T7 @lat18**
- FTD-A1: Interface is down=102, Dst MAC L2 Lookup Failed=4
- FTD-A2: First TCP packet not SYN=310, Interface is down=9

**T7 @lat2**
- FTD-A1: Interface is down=26, Dst MAC L2 Lookup Failed=2
- FTD-A2: First TCP packet not SYN=312, Interface is down=9

**T7 @lat4**
- FTD-A1: Interface is down=35
- FTD-A2: First TCP packet not SYN=322, Interface is down=3

**T8 @1.0%loss**
- FTD-A1: First TCP packet not SYN=2043, TCP failed 3 way handshake=2

**T8 @5.0%loss**
- FTD-A1: First TCP packet not SYN=1871

**T9 [bfd]**
- FTD-A1: Blocked or blacklisted by the stream preprocessor=23, First TCP packet not SYN=4

**T9 [timers]**
- FTD-A1: First TCP packet not SYN=113, TCP RST/FIN out of order=29

## T7 latency sweep

| CML latency/dir | Failover detect | iperf3 survived | zero-throughput intervals | est. conns dropped |
| --- | --- | --- | --- | --- |
| 0 | 4.6s | yes | 1 | 0 |
| 2 | 4.8s | yes | 1 | 0 |
| 4 | 4.6s | yes | 1 | 0 |
| 11 | 4.6s | yes | 1 | 0 |
| 18 | 4.7s | yes | 1 | 0 |

