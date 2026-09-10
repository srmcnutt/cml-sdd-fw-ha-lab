#!/usr/bin/env python3
"""Portability round-trip: export the live lab and compare it with the rendered file.

Reports differences in node definitions, resources, interfaces, configs, links,
and conditioning. Trailing whitespace per line is ignored (CML strips it), and
Docker nodes' config.json is ignored (CML exports only the boot script).
Writes lab/topology.exported.yaml. Exit code 1 when drift is found.
"""
import os, sys, yaml
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lablib as L


def norm_cfg(s): return '\n'.join(l.rstrip() for l in s.strip().splitlines())


def norm(doc):
    nodes = {}
    for n in doc['nodes']:
        cfg = n.get('configuration') or []
        if isinstance(cfg, str): cfg = [{'name': 'config', 'content': cfg}]
        files = {c['name']: norm_cfg(c['content'] or '') for c in cfg if c['name'] != 'config.json'}
        nodes[n['label']] = {'def': n['node_definition'], 'ram': n.get('ram'), 'cpus': n.get('cpus'),
                             'phys': [i['label'] for i in n.get('interfaces', []) if i.get('type') == 'physical'], 'cfg': files}
    byid = {n['id']: n for n in doc['nodes']}
    links, cond = set(), {}
    for l in doc['links']:
        a, b = byid[l['n1']], byid[l['n2']]
        ia = next(i['label'] for i in a['interfaces'] if i['id'] == l['i1']); ib = next(i['label'] for i in b['interfaces'] if i['id'] == l['i2'])
        links.add(frozenset((f"{a['label']}:{ia}", f"{b['label']}:{ib}")))
        c = {k: v for k, v in (l.get('conditioning') or {}).items() if k in ('latency', 'loss', 'jitter', 'bandwidth')}
        if c: cond[f"{a['label']}<->{b['label']}"] = c
    return nodes, links, cond


def main():
    ids = L.load_state('ids.json'); lid = ids['lab_id']
    st, h, body = L.cml('GET', f'/api/v0/labs/{lid}/download', raw=True)
    out = os.path.join(L.REPO, 'lab', 'topology.exported.yaml')
    with open(out, 'w') as f: f.write(body.decode())
    exp = yaml.safe_load(body.decode())
    with open(L.rendered_path()) as f: ren = yaml.safe_load(f)
    en, el, ec = norm(exp); rn, rl, rc = norm(ren)
    drift = []
    for k in sorted(set(en) | set(rn)):
        if k not in en: drift.append(f'node only in rendered: {k}'); continue
        if k not in rn: drift.append(f'node only in CML: {k}'); continue
        for f in ('def', 'ram', 'cpus', 'phys'):
            if en[k][f] != rn[k][f]: drift.append(f'{k}: {f} CML={en[k][f]} rendered={rn[k][f]}')
        for name in sorted(set(en[k]['cfg']) | set(rn[k]['cfg'])):
            if en[k]['cfg'].get(name) != rn[k]['cfg'].get(name): drift.append(f'{k}: config {name} differs')
    if el != rl: drift.append(f'links differ: only in CML {sorted(map(sorted, el - rl))}, only in rendered {sorted(map(sorted, rl - el))}')
    if ec != rc: drift.append(f'conditioning differs: CML={ec} rendered={rc}')
    print(f'exported {len(en)} nodes, {len(el)} links -> lab/topology.exported.yaml')
    if drift:
        print('DRIFT:'); [print('  ' + d) for d in drift]; sys.exit(1)
    print(f'no drift: the live lab matches {os.path.relpath(L.rendered_path(), L.REPO)}')


if __name__ == '__main__':
    main()
