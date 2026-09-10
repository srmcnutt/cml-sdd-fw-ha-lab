#!/usr/bin/env python3
"""Re-apply day-0 configuration to existing nodes from the rendered lab file.

  push_configs.py NODE [NODE ...]      stop, wipe, load config, start each node
  push_configs.py --all                every node that has a configuration
  push_configs.py --no-start NODE ...  leave the node stopped after loading

Reads the rendered lab file (run render_lab.py first) and the lab id
from lab/state/ids.json. Wiping discards the node's disk state, so the node
boots fresh from the repository config, exactly as a new import would.
"""
import os, sys, time, yaml
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lablib as L


def node_state(lid, nid):
    st, h, n = L.cml('GET', f'/api/v0/labs/{lid}/nodes/{nid}?data=true'); return n.get('state')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    start = '--no-start' not in sys.argv
    ids = L.load_state('ids.json'); lid = ids['lab_id']
    with open(L.rendered_path()) as f: rendered = yaml.safe_load(f)
    cfgs = {n['label']: n['configuration'] for n in rendered['nodes'] if n.get('configuration')}
    labels = list(cfgs) if '--all' in sys.argv else args
    for label in labels:
        nid = ids['nodes'][label]; conf = cfgs[label]
        st, h, b = L.cml('PUT', f'/api/v0/labs/{lid}/nodes/{nid}/state/stop')
        for _ in range(40):
            if node_state(lid, nid) in ('STOPPED', 'DEFINED_ON_CORE'): break
            time.sleep(3)
        st, h, b = L.cml('PUT', f'/api/v0/labs/{lid}/nodes/{nid}/wipe_disks')
        time.sleep(2)
        # single-file configs are sent as a string, multi-file as the list of {name, content}
        payload = conf[0]['content'] if len(conf) == 1 else conf
        st, h, b = L.cml('PATCH', f'/api/v0/labs/{lid}/nodes/{nid}', {'configuration': payload})
        if st != 200: raise SystemExit(f'{label}: config load failed {st} {b}')
        print(f'{label}: config loaded ({len(conf)} file(s))', end='')
        if start:
            st, h, b = L.cml('PUT', f'/api/v0/labs/{lid}/nodes/{nid}/state/start'); print(f', start {st}')
        else: print(', left stopped')


if __name__ == '__main__':
    main()
