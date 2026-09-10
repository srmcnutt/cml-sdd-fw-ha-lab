#!/usr/bin/env python3
"""Execute one failover scenario from build package section 16 and record results.

  run_test.py T1|T2|T3|T4|T5|T6|T7|T8|T9 [options]
  run_test.py restore                      put the lab back to baseline and exit

Options:
  --pair A|B          pair under test for T2/T3/T4 (default A)
  --latency N         T7: CML per-direction latency for both trunks (11 = 25 ms RTT)
  --loss PCT          T8: loss percent on both trunks
  --then-failover     T3/T8: after the impairment settles, also switch the active peer (stateless failover demo)
  --settle S          seconds of traffic before the trigger (default 30)
  --hold S            observation window after the trigger (default 120)
  --cps N             TRex new connections per second per node (default 50)
  --flow-hold S       seconds each TRex connection stays open (default 90)
  --no-traffic        run without TRex and iperf3
  --keep              do not restore the baseline afterwards

Run with the TRex client environment:
  TREX_EXT_LIBS=$PWD/vendor/trex-ext-libs .venv-trex/bin/python scripts/run_test.py T2
"""
import os, sys, time, json, re, subprocess
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'scripts'))
import lablib as L, console as C, trex_run as T

IDS = L.load_state('ids.json'); LAB = IDS['lab_id']
# the FTD admin password is whatever the day-0 config set; read it from there rather than repeating it
with open(os.path.join(REPO, 'configs', 'ftd', 'FTD-A1.day0.json')) as _f: FTD_LOGIN = 'admin:' + json.load(_f)['AdminPassword']
FTD_PROMPT = r'(?m)^> ?$'
BASE_COND = {'latency': 11, 'jitter': 0, 'loss': 0.0, 'bandwidth': 0}
TRUNK_LINKS = (31, 32)
INSIDE_TRUNK_VLANS = '110,210,900-903'
PAIRS = {'A': {'name': 'PAIR-A', 'primary': 'FTD-A1', 'secondary': 'FTD-A2', 'fo_vlan': 900, 'state_vlan': 901, 'public': '198.51.100.50', 'trex': 'A'},
         'B': {'name': 'PAIR-B', 'primary': 'FTD-B2', 'secondary': 'FTD-B1', 'fo_vlan': 902, 'state_vlan': 903, 'public': '198.51.100.114', 'trex': 'B'}}

LOG = []
def log(*a):
    line = time.strftime('%H:%M:%S ') + ' '.join(str(x) for x in a)
    print(line, flush=True); LOG.append(line)


# ---------------------------------------------------------------- CML primitives
def node_id(label): return IDS['nodes'][label]
def link_id(num): return IDS['links'][str(num)]['id']

def node_state(label):
    st, h, n = L.cml('GET', f'/api/v0/labs/{LAB}/nodes/{node_id(label)}?data=true'); return n.get('state')

def node_op(label, op):
    st, h, b = L.cml('PUT', f'/api/v0/labs/{LAB}/nodes/{node_id(label)}/state/{op}'); log(f'node {label} {op}: {st}')

def link_op(num, op):
    st, h, b = L.cml('PUT', f'/api/v0/labs/{LAB}/links/{link_id(num)}/state/{op}'); log(f'link {num} {op}: {st}')

def link_state(num):
    st, h, l = L.cml('GET', f'/api/v0/labs/{LAB}/links/{link_id(num)}'); return l.get('state')

def condition(num, **kw):
    body = dict(BASE_COND); body.update(kw)
    st, h, c = L.cml('PATCH', f'/api/v0/labs/{LAB}/links/{link_id(num)}/condition', body)
    log(f'link {num} conditioning: {st} latency={c.get("latency")} loss={c.get("loss")}')

def wait_node(label, state='BOOTED', timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if node_state(label) == state: return True
        time.sleep(10)
    return False


# ---------------------------------------------------------------- switch VLAN pruning
def trunk_vlans(switch, action, vlan):
    with C.Session(switch, prompt=rf'(?m)^{re.escape(switch)}(\(config[^)]*\))?[>#] ?$') as s:
        s.run('configure terminal'); s.run('interface Ethernet2/0')
        s.run(f'switchport trunk allowed vlan {action} {vlan}'); s.run('end')
        out = s.run('show interfaces trunk | include Et2/0')
    log(f'{switch} Et2/0 allowed vlan {action} {vlan} ->', ' '.join(out.split()[-8:]))


# ---------------------------------------------------------------- FMC
def ha_pair(name):
    for p in L.fmc_all('/api/fmc_config/v1/domain/{domain}/devicehapairs/ftddevicehapairs?expanded=true'):
        if p['name'] == name: return p
    return None

def ha_status(name):
    p = ha_pair(name) or {}; m = p.get('metadata') or {}
    return {'primary': (m.get('primaryStatus') or {}).get('currentStatus'), 'secondary': (m.get('secondaryStatus') or {}).get('currentStatus')}

def fmc_switch_active(name):
    p = ha_pair(name)
    body = {'id': p['id'], 'type': 'DeviceHAPair', 'name': p['name'], 'action': 'SWITCH',
            'primary': {'id': p['primary']['id'], 'type': 'Device'}, 'secondary': {'id': p['secondary']['id'], 'type': 'Device'}}
    st, h, r = L.fmc('PUT', f"/api/fmc_config/v1/domain/{{domain}}/devicehapairs/ftddevicehapairs/{p['id']}", body)
    log(f'FMC switch active {name}: {st} {str(r)[:160] if st not in (200, 202) else "accepted"}')
    return st in (200, 202)


# ---------------------------------------------------------------- FTD observation
class FtdWatch:
    def __init__(self, labels):
        self.sessions = {l: C.Session(l, login=FTD_LOGIN, prompt=FTD_PROMPT, timeout=20).__enter__() for l in labels}
    def state(self, label):
        try:
            out = self.sessions[label].run('show failover | include This host|Other host', timeout=15)
            this = re.search(r'This host:\s*(.*)', out); other = re.search(r'Other host:\s*(.*)', out)
            return {'this': this.group(1).strip() if this else '?', 'other': other.group(1).strip() if other else '?'}
        except Exception as e:
            return {'this': f'err {type(e).__name__}', 'other': ''}
    def cmd(self, label, cmd):
        return self.sessions[label].run(cmd, timeout=30)
    def diag(self, label):
        """Drop reasons, stateful replication counters, and connection count on one unit."""
        d = {}
        try:
            asp = self.cmd(label, 'show asp drop')
            d['asp_drop'] = [l.strip() for l in asp.splitlines() if re.search(r'\)\s+\d+\s*$', l)][:40]
            fo = self.cmd(label, 'show failover | begin Stateful Failover Logical Update')
            d['stateful'] = [l.strip() for l in fo.splitlines() if re.search(r'^\s*(General|sys cmd|up time|RPC services|TCP conn|UDP conn|ARP tbl|Xlate_Timeout|Logical Update Queue|Recv Q|Xmit Q|Stateful Failover Logical|\s*Cur\s|\s*Max|Total)', l)][:30]
            cc = self.cmd(label, 'show conn count'); d['conn_count'] = cc.strip().splitlines()[1].strip() if len(cc.strip().splitlines()) > 1 else cc.strip()
        except Exception as e:
            d['error'] = f'{type(e).__name__}: {str(e)[:80]}'
        return d
    def close(self):
        for s in self.sessions.values():
            try: s.__exit__(None, None, None)
            except Exception: pass


# ---------------------------------------------------------------- traffic
class Traffic:
    def __init__(self, cps, flow_hold, enabled=True):
        self.enabled = enabled; self.cps = cps; self.flow_hold = flow_hold; self.clients = {}; self.client_host = None
    def start(self):
        if not self.enabled: return
        for k in ('A', 'B'):
            try:
                self.clients[k] = T.start(k, self.cps, self.flow_hold, keep=True)
            except Exception as e: log(f'TRex {k} start failed: {e}')
        self.client_host = C.Session('CLIENT', prompt=r'(?m)^[^\r\n]*[\$#] ?$').__enter__()
        self.client_host.run('pkill iperf3; rm -f /tmp/iperf-A.log; nohup stdbuf -oL -eL iperf3 -c 198.51.100.50 -t 3600 -i 2 -f k > /tmp/iperf-A.log 2>&1 &')
        log('traffic started: TRex A+B, iperf3 CLIENT -> 198.51.100.50 (pair A)')
    def snapshot(self):
        snap = {}
        for k, c in self.clients.items():
            try: snap['trex_' + k] = T.snapshot(c)
            except Exception as e: snap['trex_' + k] = {'error': str(e)[:80]}
        if self.client_host:
            try:
                out = self.client_host.run('tail -3 /tmp/iperf-A.log', timeout=8)
                lines = [l for l in out.splitlines() if ('sec' in l and 'Bytes' in l) or 'error' in l.lower() or 'reset' in l.lower() or 'refused' in l.lower()]
                snap['iperf'] = lines[-1].strip()[:90] if lines else 'no iperf output yet'
            except Exception as e: snap['iperf'] = f'err {type(e).__name__}'
        return snap
    def stop(self):
        summary = {}
        if not self.enabled: return summary
        for k, c in self.clients.items():
            try: c.stop(); c.disconnect(stop_traffic=False)
            except Exception: pass
        if self.client_host:
            try:
                out = self.client_host.run('pkill iperf3; sleep 1; '
                    'echo IPERF_INTERVALS=$(grep -cE " sec .*Bytes" /tmp/iperf-A.log); '
                    'echo IPERF_ZERO=$(grep -cE "0.00 (Bytes|Kbits)" /tmp/iperf-A.log); '
                    'echo IPERF_RESET=$(grep -ciE "reset|broken pipe|refused|timed out|unable to connect" /tmp/iperf-A.log)', timeout=12)
                for key, pat in (('intervals', 'IPERF_INTERVALS='), ('zero_intervals', 'IPERF_ZERO='), ('resets', 'IPERF_RESET=')):
                    m = re.search(pat + r'(\d+)', out)
                    if m: summary[key] = int(m.group(1))
                summary['survived'] = summary.get('resets', 1) == 0 and summary.get('intervals', 0) > 0
                log('iperf3:', json.dumps(summary))
                self.client_host.__exit__(None, None, None)
            except Exception as e: log('iperf3 summary failed:', type(e).__name__); 
        return summary


def clear_ftd_tables():
    """Stale connections from a previous TRex run stay in the FTD table for the idle timeout and
    collide with the next run's SYNs (TRex reuses the same source ports). Clear before each run."""
    for label in ('FTD-A1', 'FTD-A2', 'FTD-B2', 'FTD-B1'):
        try:
            with C.Session(label, login=FTD_LOGIN, prompt=FTD_PROMPT, timeout=20) as s:
                s.run('clear conn'); s.run('clear asp drop'); cc = s.run('show conn count')
                log(f'{label}: cleared connections and drop counters; now {cc.strip().splitlines()[1].strip() if len(cc.strip().splitlines()) > 1 else cc.strip()[:40]}')
        except Exception as e:
            log(f'{label}: clear failed {type(e).__name__}')


# ---------------------------------------------------------------- baseline
def restore_baseline():
    log('== restore baseline')
    for num in TRUNK_LINKS:
        if link_state(num) != 'STARTED': link_op(num, 'start')
        condition(num)
    for label in ('FTD-A1', 'FTD-B1', 'RTR-1', 'RTR-4'):
        if node_state(label) != 'BOOTED':
            node_op(label, 'start')
    with C.Session('SW-IN-EAST', prompt=r'(?m)^SW-IN-EAST(\(config[^)]*\))?[>#] ?$') as s:
        s.run('configure terminal'); s.run('interface Ethernet2/0'); s.run(f'switchport trunk allowed vlan {INSIDE_TRUNK_VLANS}'); s.run('end')
    for label in ('FTD-A1', 'FTD-B1', 'RTR-1', 'RTR-4'):
        if node_state(label) != 'BOOTED': log(f'waiting for {label} to boot'); wait_node(label)
    # Bring both pairs back to primary-active. A single switch right after the state
    # link returns is often ignored because the standby is still bulk-syncing, so
    # retry the switch inside the loop (every ~75 s) until it takes.
    t0 = time.time(); last_switch = {}
    while time.time() - t0 < 480:
        sts = {k: ha_status(p['name']) for k, p in PAIRS.items()}
        if all(s == {'primary': 'Active', 'secondary': 'Standby'} for s in sts.values()):
            log('baseline HA:', sts); return
        for k, p in PAIRS.items():
            s = sts[k]
            if s == {'primary': 'Active', 'secondary': 'Active'}:
                log(f'{p["name"]}: split-brain still resolving (both active)')
            elif s.get('secondary') == 'Active' and 'Standby' in (s.get('primary') or ''):
                if time.time() - last_switch.get(k, 0) > 75:
                    log(f'{p["name"]}: {s}, re-issuing switch to primary'); fmc_switch_active(p['name']); last_switch[k] = time.time()
        log('waiting for HA baseline:', sts); time.sleep(20)
    log('WARNING: HA did not return to primary-active baseline')


# ---------------------------------------------------------------- scenarios
def run(scenario, opts):
    pair = PAIRS[opts.get('pair', 'A')]
    traffic = Traffic(opts.get('cps', 50), opts.get('flow_hold', 90), enabled=not opts.get('no_traffic'))
    watch_labels = [pair['primary'], pair['secondary']]
    if scenario in ('T5', 'T6'): watch_labels = ['FTD-A1', 'FTD-A2', 'FTD-B2', 'FTD-B1']
    result = {'scenario': scenario, 'opts': opts, 'started': time.strftime('%Y-%m-%d %H:%M:%S'), 'timeline': [], 'events': {}}
    os.makedirs(os.path.join(REPO, 'results', scenario), exist_ok=True)
    restore_baseline()
    if scenario == 'T7': [condition(n, latency=int(opts['latency'])) for n in TRUNK_LINKS]; time.sleep(3)
    if scenario == 'T8': [condition(n, loss=float(opts['loss'])) for n in TRUNK_LINKS]; time.sleep(3)
    clear_ftd_tables()
    watch = FtdWatch(watch_labels)
    traffic.start()
    log(f'settling {opts.get("settle", 30)} s')
    time.sleep(opts.get('settle', 30))
    pre = {l: watch.state(l) for l in watch_labels}; pre['traffic'] = traffic.snapshot(); pre['fmc'] = ha_status(pair['name'])
    pre['diag'] = {l: watch.diag(l) for l in watch_labels[:2]}
    result['pre'] = pre; log('pre:', json.dumps({k: v for k, v in pre.items() if k != 'diag'})[:600])

    # trigger
    t0 = time.time(); result['t0'] = time.strftime('%H:%M:%S')
    if scenario == 'T1': log('T1: no trigger, observing baseline')
    elif scenario in ('T2', 'T7'):
        fmc_switch_active(pair['name'])
    elif scenario == 'T3':
        trunk_vlans('SW-IN-EAST', 'remove', pair['state_vlan'])
    elif scenario == 'T4':
        trunk_vlans('SW-IN-EAST', 'remove', pair['fo_vlan'])
    elif scenario == 'T5':
        for n in TRUNK_LINKS: link_op(n, 'stop')
    elif scenario == 'T6':
        node_op('FTD-A1', 'stop'); node_op('FTD-B1', 'stop')
    elif scenario == 'T8':
        log(f'T8: observing under {opts["loss"]}% loss')
    elif scenario == 'T9':
        node_op('RTR-1', 'stop')
    if scenario in ('T3', 'T8') and opts.get('then_failover'):
        log('waiting 45 s for the impairment to settle before switching the active peer'); time.sleep(45)
        t0 = time.time(); result['t0_failover'] = time.strftime('%H:%M:%S'); fmc_switch_active(pair['name'])

    # observe
    hold = opts.get('hold', 120); first_change = None; recovered = None; mid_done = False
    while time.time() - t0 < hold:
        if not mid_done and time.time() - t0 > min(45, hold / 2):
            result['mid'] = {'t': round(time.time() - t0, 1), 'diag': {l: watch.diag(l) for l in watch_labels[:2]}}; mid_done = True
            log('mid diag captured at t+%.1fs' % result['mid']['t'])
        row = {'t': round(time.time() - t0, 1)}
        for l in watch_labels: row[l] = watch.state(l)
        row.update(traffic.snapshot())
        result['timeline'].append(row)
        states = ' | '.join(f"{l}: {row[l]['this']}" for l in watch_labels)
        ta = row.get('trex_' + pair['trex'], {})
        log(f"t+{row['t']:>6}s  {states}  flows={ta.get('active_flows')} tx_cps={ta.get('tx_cps')} rx_pps={ta.get('rx_pps')} conndrops={ta.get('c_tcps_conndrops')} rexmt={ta.get('c_tcps_rexmttimeo')}  iperf={row.get('iperf', '')[-60:]}")
        if first_change is None and any(row[l]['this'] != pre[l]['this'] for l in watch_labels):
            first_change = row['t']; result['events']['first_state_change_s'] = first_change; log(f'** failover state change observed at t+{first_change}s')
        if first_change is not None and recovered is None and ta.get('rx_pps', 0) and ta.get('rx_pps', 0) > 0:
            recovered = row['t']; result['events']['traffic_seen_after_change_s'] = recovered
        time.sleep(5)
    post = {l: watch.state(l) for l in watch_labels}; post['traffic'] = traffic.snapshot(); post['fmc'] = ha_status(pair['name'])
    post['diag'] = {l: watch.diag(l) for l in watch_labels[:2]}
    result['post'] = post; log('post:', json.dumps({k: v for k, v in post.items() if k != 'diag'})[:600])
    # drop-reason deltas on the unit that became active
    for l in watch_labels[:2]:
        def counts(d): return {re.sub(r'\s+\d+$', '', x): int(x.rsplit(None, 1)[-1]) for x in d.get('asp_drop', []) if x.rsplit(None, 1)[-1].isdigit()}
        b, a = counts(pre['diag'].get(l, {})), counts(post['diag'].get(l, {}))
        delta = {k: a[k] - b.get(k, 0) for k in a if a[k] - b.get(k, 0) > 0}
        if delta: result['events'][f'asp_drop_delta_{l}'] = dict(sorted(delta.items(), key=lambda kv: -kv[1])[:8]); log(f'{l} asp drop deltas:', result['events'][f'asp_drop_delta_{l}'])
    if traffic.enabled:
        pre_t, post_t = pre['traffic'].get('trex_' + pair['trex'], {}), post['traffic'].get('trex_' + pair['trex'], {})
        result['events']['conndrops_delta'] = (post_t.get('c_tcps_conndrops') or 0) - (pre_t.get('c_tcps_conndrops') or 0)
        result['events']['rexmt_delta'] = (post_t.get('c_tcps_rexmttimeo') or 0) - (pre_t.get('c_tcps_rexmttimeo') or 0)
        result['events']['active_flows_pre_post'] = (pre_t.get('active_flows'), post_t.get('active_flows'))
    result['events']['iperf'] = traffic.stop(); watch.close()
    if not opts.get('keep'): restore_baseline()
    result['log'] = LOG
    d = os.path.join(REPO, 'results', scenario); os.makedirs(d, exist_ok=True)
    fn = os.path.join(d, time.strftime('%Y%m%d-%H%M%S') + '.json')
    with open(fn, 'w') as f: json.dump(result, f, indent=1)
    log('events:', json.dumps(result['events'])); log('saved', os.path.relpath(fn, REPO))
    return result


def parse(argv):
    opts = {}; i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--pair', '--latency', '--loss', '--settle', '--hold', '--cps', '--flow-hold', '--tag'):
            v = argv[i + 1]; i += 2
            opts[a[2:].replace('-', '_')] = v if a in ('--pair', '--tag') else (float(v) if a == '--loss' else int(v))
        elif a in ('--then-failover', '--no-traffic', '--keep'): opts[a[2:].replace('-', '_')] = True; i += 1
        else: raise SystemExit(f'unknown option {a}\n{__doc__}')
    return opts


if __name__ == '__main__':
    if len(sys.argv) < 2: raise SystemExit(__doc__)
    what = sys.argv[1]; opts = parse(sys.argv[2:])
    if what == 'restore': restore_baseline()
    elif what in ('T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9'): run(what, opts)
    else: raise SystemExit(__doc__)
