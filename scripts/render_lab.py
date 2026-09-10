#!/usr/bin/env python3
"""Render lab/topology.yaml plus the files under configs/ into CML's native
lab import format (schema 0.3.0) at lab/<title>.cml.yaml, where <title> is the
lab title in topology.yaml.

The rendered file is the portable artifact: it imports into any CML 2.9
instance with the same node definitions, with every device config embedded.
Never edit the rendered file by hand; edit the source and re-render.
"""
import os, sys, yaml
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lablib as L

REPO = L.REPO
SRC = L.TOPOLOGY
OUT = L.rendered_path()

# Physical interface names per node definition, in slot order, as presented by CML 2.9.
PHYS = {
    'cat8000v': [f'GigabitEthernet{i}' for i in range(1, 27)],
    'ioll2-xe': [f'Ethernet{s}/{p}' for s in range(8) for p in range(4)],
    'iol-xe': [f'Ethernet{s}/{p}' for s in range(8) for p in range(4)],
    'ftdv': ['Management0/0', 'donotuse1'] + [f'GigabitEthernet0/{i}' for i in range(8)],
    'trex': ['eth0', 'eth1', 'eth2'],
    'net-tools': ['eth0', 'eth1', 'eth2', 'eth3'],
    'unmanaged_switch': [f'port{i}' for i in range(32)],
    'external_connector': ['port'],
}
# Day-0 file names each node definition expects, in the order configs are listed in the source.
CFG_FILES = {
    'cat8000v': ['iosxe_config.txt'],
    'ioll2-xe': ['ios_config.txt'],
    'iol-xe': ['ios_config.txt'],
    'ftdv': ['day0-config'],
    'trex': ['node.cfg'],
    'net-tools': ['config.json', 'boot.sh'],
    'external_connector': ['default'],
}


def render():
    with open(SRC) as f: src = yaml.safe_load(f)
    nodes, node_ids, iface_ids = [], {}, {}
    for idx, (label, n) in enumerate(src['nodes'].items()):
        nd = n['def']; nid = f'n{idx}'; node_ids[label] = nid
        names = PHYS[nd][:n['ifaces']]
        ifaces = []
        for slot, name in enumerate(names):
            iid = f'i{slot}'; iface_ids[(label, name)] = iid
            ifaces.append({'id': iid, 'label': name, 'slot': slot, 'type': 'physical'})
        conf = []
        cfg = n.get('config')
        if cfg:
            paths = cfg if isinstance(cfg, list) else [cfg]
            for fname, path in zip(CFG_FILES[nd], paths):
                with open(os.path.join(REPO, path)) as f: conf.append({'name': fname, 'content': f.read()})
        if n.get('config_inline') is not None:
            conf.append({'name': CFG_FILES[nd][0], 'content': n['config_inline']})
        node = {'id': nid, 'label': label, 'node_definition': nd, 'x': n['x'], 'y': n['y'],
                'configuration': conf, 'tags': n.get('tags', []), 'parameters': {},
                'ram': n.get('ram'), 'cpus': n.get('cpus'), 'cpu_limit': None, 'boot_disk_size': None,
                'data_volume': None, 'image_definition': None, 'hide_links': False, 'interfaces': ifaces}
        nodes.append(node)
    links = []
    for k, l in enumerate(src['links']):
        (na, ia), (nb, ib) = l['a'].split(':', 1), l['b'].split(':', 1)
        for lbl, name in ((na, ia), (nb, ib)):
            if (lbl, name) not in iface_ids:
                raise SystemExit(f'link {l["n"]}: unknown interface {lbl}:{name}')
        links.append({'id': f'l{k}', 'n1': node_ids[na], 'n2': node_ids[nb], 'i1': iface_ids[(na, ia)],
                      'i2': iface_ids[(nb, ib)], 'conditioning': dict(l.get('conditioning') or {}),
                      'label': f'{l["n"]:02d} {na}-{ia}<->{nb}-{ib}'})
    doc = {'lab': {'title': src['lab']['title'], 'description': src['lab']['description'], 'notes': '',
                   'version': '0.3.0'},
           'annotations': [], 'smart_annotations': [], 'nodes': nodes, 'links': links}
    with open(OUT, 'w') as f:
        f.write('# RENDERED FILE. Source: lab/topology.yaml + configs/. Regenerate with scripts/render_lab.py\n')
        yaml.safe_dump(doc, f, sort_keys=False, width=1000)
    print(f'rendered {len(nodes)} nodes, {len(links)} links -> {os.path.relpath(OUT, REPO)}')


if __name__ == '__main__':
    render()
