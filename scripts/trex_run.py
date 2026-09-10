#!/usr/bin/env python3
"""Drive the two TRex nodes over the management network (ASTF mode).

  trex_run.py status [A|B]              server mode, ports, running state
  trex_run.py start A|B [cps] [hold]    load configs/trex/http_nat.py and start (default cps 100, hold 30 s)
  trex_run.py stop A|B
  trex_run.py stats A|B                 active/opened flows, tx/rx, errors
  trex_run.py watch A|B [seconds]       print stats every 2 s for the given time (default 60)

Run with the TRex client environment:
  TREX_EXT_LIBS=$PWD/vendor/trex-ext-libs .venv-trex/bin/python scripts/trex_run.py ...
"""
import os, sys, time, json
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('TREX_EXT_LIBS', os.path.join(REPO, 'vendor', 'trex-ext-libs'))
sys.path.insert(0, os.path.join(REPO, 'vendor', 'trex-core', 'scripts', 'automation', 'trex_control_plane', 'interactive'))
from trex.astf.api import ASTFClient

NODES = {
    'A': {'ip': '198.18.129.45', 'client_start': '192.0.2.33', 'client_end': '192.0.2.62',
          'server_start': '198.51.100.33', 'server_end': '198.51.100.46'},
    'B': {'ip': '198.18.129.46', 'client_start': '192.0.2.161', 'client_end': '192.0.2.190',
          'server_start': '198.51.100.97', 'server_end': '198.51.100.110'},
}
PROFILE = os.path.join(REPO, 'configs', 'trex', 'http_nat.py')


def client(key):
    n = NODES[key]
    c = ASTFClient(server=n['ip'], sync_port=4501, async_port=4500, verbose_level='error')
    c.connect(); return c


def status(keys):
    for k in keys:
        try:
            c = client(k); v = c.get_server_version(); info = c.get_server_system_info()
            try: running = c.is_traffic_active()
            except Exception: running = 'n/a (ports not acquired)'
            print(f"TREX-{k} {NODES[k]['ip']}: TRex {v.get('version')} mode={v.get('mode')} ports={info.get('port_count')} traffic_active={running}")
            c.disconnect()
        except Exception as e:
            print(f'TREX-{k}: {type(e).__name__}: {str(e)[:200]}')


def start(k, cps=100, hold=30, keep=False):
    """Start the profile. With keep=True the connected client is returned (it owns the ports,
    which get_stats requires); otherwise the client disconnects and traffic keeps running."""
    n = NODES[k]; c = client(k)
    c.reset(); c.clear_stats()
    kw = {kk: n[kk] for kk in ('client_start', 'client_end', 'server_start', 'server_end')}
    kw.update(cps=float(cps), hold=int(hold))
    c.load_profile(PROFILE, tunables=kw)
    c.start(mult=1, duration=-1, nc=True)
    time.sleep(2)
    print(f'TREX-{k}: started {os.path.basename(PROFILE)} cps={cps} hold={hold}s clients {kw["client_start"]}-{kw["client_end"]} -> {kw["server_start"]}-{kw["server_end"]}')
    if keep: return c
    c.disconnect(stop_traffic=False)


def stop(k):
    c = client(k); c.stop(); c.disconnect(stop_traffic=False); print(f'TREX-{k}: stopped')


def snapshot(c):
    s = c.get_stats(); g = s.get('global', {}); t = s.get('traffic', {})
    cs, ss = t.get('client', {}), t.get('server', {})
    return {
        'time': time.strftime('%H:%M:%S'),
        'active_flows': g.get('active_flows'), 'open_flows': g.get('open_flows'),
        'tx_cps': round(g.get('tx_cps', 0)), 'rx_pps': round(g.get('rx_pps', 0)),
        'tx_bps': round(g.get('tx_bps', 0)), 'rx_bps': round(g.get('rx_bps', 0)),
        'c_tcps_connects': cs.get('tcps_connects'), 'c_tcps_closed': cs.get('tcps_closed'),
        'c_tcps_conndrops': cs.get('tcps_conndrops'), 'c_tcps_rexmttimeo': cs.get('tcps_rexmttimeo'),
        'c_tcps_timeoutdrop': cs.get('tcps_timeoutdrop'), 'c_err_no_syn': cs.get('err_no_syn'),
        's_tcps_accepts': ss.get('tcps_accepts'), 's_tcps_closed': ss.get('tcps_closed'),
        's_tcps_rexmttimeo': ss.get('tcps_rexmttimeo'),
    }


def stats(k):
    c = client(k); c.acquire(force=True); print(json.dumps(snapshot(c))); c.disconnect(stop_traffic=False)


def watch(k, seconds=60):
    c = client(k); c.acquire(force=True); t0 = time.time()
    while time.time() - t0 < seconds:
        print(json.dumps(snapshot(c)), flush=True); time.sleep(2)
    c.disconnect(stop_traffic=False)


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a: raise SystemExit(__doc__)
    cmd = a[0]
    if cmd == 'status': status(a[1:] or ['A', 'B'])
    elif cmd == 'start': start(a[1], *(a[2:4]))
    elif cmd == 'stop': stop(a[1])
    elif cmd == 'stats': stats(a[1])
    elif cmd == 'watch': watch(a[1], int(a[2]) if len(a) > 2 else 60)
    else: raise SystemExit(__doc__)
