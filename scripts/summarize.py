#!/usr/bin/env python3
"""Read every results/T*/*.json and print a per-scenario summary, newest run per
scenario. Writes results/RESULTS.md. Use --json to emit machine-readable rows.

  .venv/bin/python scripts/summarize.py
"""
import os, sys, json, glob

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRIGGER = {
    'T1': 'none (baseline)', 'T2': 'FMC planned failover, pair A',
    'T3': 'drop state VLAN 901, then failover', 'T4': 'drop failover VLAN 900',
    'T5': 'stop both inter-site trunks', 'T6': 'power off both East firewalls',
    'T7': 'planned failover at a swept latency', 'T8': 'inter-site loss, observe',
    'T9': 'power off RTR-1',
}
# T7 runs are recorded by CML per-direction latency setting. Target round-trip
# times from build package section 13 (setting 0 is the path's own ~3 ms floor).
T7_TARGET_RTT = {0: '~3', 2: '6', 4: '10', 11: '25', 18: '40'}


def latest_per_scenario():
    rows = {}
    for f in glob.glob(os.path.join(REPO, 'results', 'T*', '*.json')):
        try: r = json.load(open(f))
        except Exception: continue
        o = r.get('opts', {}); sc = r.get('scenario'); key = (sc, o.get('latency'), o.get('loss'), o.get('tag'))
        if key not in rows or f > rows[key][0]: rows[key] = (f, r)
    return [v[1] | {'_file': os.path.relpath(v[0], REPO)} for v in sorted(rows.values(), key=lambda x: x[1].get('_sortless', '') or x[0])]


def summarize(r):
    e = r.get('events', {}); ip = e.get('iperf') or {}
    pre, post = r.get('pre', {}), r.get('post', {})
    def ha(b): f = b.get('fmc', {}); return f"{f.get('primary','?')[:4]}/{f.get('secondary','?')[:4]}"
    o = r.get('opts', {})
    label = r['scenario']
    if r['scenario'] == 'T7': label += f" @{T7_TARGET_RTT.get(o.get('latency'), '?')} ms RTT (CML {o.get('latency')}/dir)"
    if r['scenario'] == 'T8': label += f" @{o.get('loss')}%loss"
    if o.get('tag'): label += f" [{o.get('tag')}]"
    drops = {k.replace('asp_drop_delta_', ''): v for k, v in e.items() if k.startswith('asp_drop_delta_')}
    # dual-active (split-brain) detection: any timeline sample where 2+ watched units report "Active" in their own state
    dual = 0
    watched = [k for k in (r.get('timeline') or [{}])[0].keys() if k.startswith('FTD-')]
    for row in r.get('timeline', []):
        actives = [u for u in watched if isinstance(row.get(u), dict) and 'Active' in row[u].get('this', '') and 'Standby' not in row[u].get('this', '')]
        dual = max(dual, len(actives))
    dual_active = dual >= 2
    return {
        'scenario': label, 'trigger': TRIGGER.get(r['scenario'], ''),
        'ha_pre': ha(pre), 'ha_post': ha(post),
        'first_change_s': e.get('first_state_change_s'),
        'conndrops': e.get('conndrops_delta'),
        'flows_pre_post': e.get('active_flows_pre_post'),
        'iperf_survived': ip.get('survived'), 'iperf_zero': ip.get('zero_intervals'),
        'top_drops': drops, 'file': r.get('_file'), 'dual_active': dual_active,
        'latency': o.get('latency'),
    }


def main():
    rows = [summarize(r) for r in latest_per_scenario()]
    order = {s: i for i, s in enumerate(['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9'])}
    rows.sort(key=lambda x: (order.get(x['scenario'][:2], 99), x['latency'] if x['scenario'].startswith('T7') else 0, x['scenario']))
    if '--json' in sys.argv:
        print(json.dumps(rows, indent=1)); return
    lines = ['# Stretched HA — test results', '',
             'Behavioral results from FTDv on CML. Not performance or sizing evidence.', '',
             '| Scenario | Trigger | HA pre→post | Failover detect | Dual-active | Est. conns dropped | iperf3 survived | TRex flows pre→post |',
             '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for x in rows:
        fp = x['flows_pre_post'] or [None, None]
        det = f"{x['first_change_s']}s" if x['first_change_s'] is not None else '—'
        lines.append(f"| {x['scenario']} | {x['trigger']} | {x['ha_pre']}→{x['ha_post']} | {det} | "
                     f"{'YES' if x['dual_active'] else 'no'} | "
                     f"{x['conndrops'] if x['conndrops'] is not None else '—'} | "
                     f"{'yes' if x['iperf_survived'] else ('no' if x['iperf_survived'] is False else '—')} | "
                     f"{int(fp[0]) if fp[0] else '—'}→{int(fp[1]) if fp[1] else '—'} |")
    lines += ['', '## Drop reasons on the unit that became active', '']
    for x in rows:
        if x['top_drops']:
            lines.append(f"**{x['scenario']}**")
            for unit, d in x['top_drops'].items():
                top = ', '.join(f'{k.split(" (")[0]}={v}' for k, v in list(d.items())[:4])
                lines.append(f"- {unit}: {top}")
            lines.append('')
    # T7 sweep
    sweep = sorted([x for x in rows if x['scenario'].startswith('T7')], key=lambda x: int(x['latency']))
    if sweep:
        lines += ['## T7 latency sweep', '',
                  '| Target RTT | CML latency/dir | Failover detect | iperf3 survived | zero-throughput intervals | est. conns dropped |',
                  '| --- | --- | --- | --- | --- | --- |']
        for x in sweep:
            lat = x['latency']
            lines.append(f"| {T7_TARGET_RTT.get(lat, '?')} ms | {lat} | {x['first_change_s']}s | {'yes' if x['iperf_survived'] else 'no'} | {x['iperf_zero']} | {x['conndrops']} |")
        lines.append('')
    out = os.path.join(REPO, 'results', 'RESULTS.md')
    open(out, 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines)); print('\nwrote', os.path.relpath(out, REPO))


if __name__ == '__main__':
    main()
