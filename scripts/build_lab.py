#!/usr/bin/env python3
"""Import the rendered lab into CML and record the resulting ids.

  build_lab.py                import; refuse if a lab with the same title exists
  build_lab.py --replace      stop, wipe, delete the existing lab first
  build_lab.py --record-only  do not import; refresh lab/state/ids.json for the existing lab

Writes lab/state/ids.json with the lab id and every node and link id keyed by
label and link number, for the other scripts. Nothing is started.
"""
import os, sys, time, yaml
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lablib as L

RENDERED = L.rendered_path()


def main():
    replace = '--replace' in sys.argv
    record_only = '--record-only' in sys.argv
    with open(RENDERED) as f: text = f.read()
    title = yaml.safe_load(text)['lab']['title']
    lid, d = L.cml_find_lab(title)
    if lid and record_only:
        print('recording ids for existing lab', lid)
    elif lid:
        if not replace: raise SystemExit(f'lab "{title}" already exists ({lid}); use --replace')
        print(f'replacing existing lab {lid} (state {d.get("state")})')
        L.cml('PUT', f'/api/v0/labs/{lid}/stop'); time.sleep(3)
        L.cml('PUT', f'/api/v0/labs/{lid}/wipe'); time.sleep(3)
        st, h, b = L.cml('DELETE', f'/api/v0/labs/{lid}')
        if st not in (200, 204): raise SystemExit(f'delete failed {st} {b}')
    if not (lid and record_only):
        st, h, res = L.cml('POST', '/api/v0/import', text, content_type='application/yaml')
        if st != 200: raise SystemExit(f'import failed {st} {res}')
        lid = res['id']; print('imported lab', lid, 'warnings:', res.get('warnings'))
    st, h, topo = L.cml('GET', f'/api/v0/labs/{lid}/topology')
    nodes = {n['label']: n['id'] for n in topo['nodes']}
    ifmap = {}
    for n in topo['nodes']:
        for i in n.get('interfaces', []): ifmap[i['id']] = (n['label'], i['label'])
    # CML regenerates link labels on import, so number links by matching endpoints to the source file.
    with open(L.TOPOLOGY) as f: src = yaml.safe_load(f)
    wanted = {frozenset((l['a'], l['b'])): l['n'] for l in src['links']}
    bynum = {}
    for l in topo['links']:
        a, b = ifmap[l['interface_a']], ifmap[l['interface_b']]
        key = frozenset((f'{a[0]}:{a[1]}', f'{b[0]}:{b[1]}'))
        num = wanted.get(key)
        if num is None: print('WARNING: link not in source:', key); continue
        bynum[num] = {'id': l['id'], 'a': f'{a[0]}:{a[1]}', 'b': f'{b[0]}:{b[1]}'}
    missing = sorted(set(wanted.values()) - set(bynum))
    if missing: print('WARNING: source links missing in CML:', missing)
    L.save_state('ids.json', {'lab_id': lid, 'title': title, 'nodes': nodes, 'links': bynum})
    print(f'{len(nodes)} nodes, {len(bynum)} links recorded in lab/state/ids.json')
    cond = [(k, v['a'], v['b']) for k, v in bynum.items() if k in (31, 32)]
    print('conditioned links:', cond)


if __name__ == '__main__':
    main()
