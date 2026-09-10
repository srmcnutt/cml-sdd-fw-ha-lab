#!/usr/bin/env python3
"""Apply the BFD lines already present in configs/routers/*.cfg to the running
routers via the console (no reboot). Keeps the live config in step with the repo
so the T9b mitigation can run without a full re-push. A fresh import from the
rendered file already includes BFD; this just makes the running lab match.
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import console as C

ROUTERS = ['ISP-A', 'ISP-B', 'RTR-1', 'RTR-2', 'RTR-3', 'RTR-4']


def bfd_delta(path):
    """Return (list of interfaces needing bfd, bgp_asn, list of neighbors needing fall-over)."""
    ifaces, neighbors, asn, cur_if = [], [], None, None
    for ln in open(path):
        mi = re.match(r'^interface (\S+)', ln)
        if mi: cur_if = mi.group(1)
        if 'bfd interval' in ln and cur_if: ifaces.append(cur_if)
        ma = re.match(r'^router bgp (\d+)', ln)
        if ma: asn = ma.group(1)
        mn = re.match(r'^ neighbor (\S+) fall-over bfd', ln)
        if mn: neighbors.append(mn.group(1))
    return ifaces, asn, neighbors


def main():
    for name in ROUTERS:
        ifaces, asn, neighbors = bfd_delta(f'configs/routers/{name}.cfg')
        cmds = ['configure terminal']
        for i in ifaces:
            cmds += [f'interface {i}', 'bfd interval 300 min_rx 300 multiplier 3', 'exit']
        cmds += [f'router bgp {asn}']
        for n in neighbors:
            cmds.append(f'neighbor {n} fall-over bfd')
        cmds += ['end']
        prompt = rf'(?m)^{re.escape(name)}(\([^)]*\))?[>#] ?$'
        with C.Session(name, prompt=prompt, timeout=25) as s:
            for c in cmds:
                s.run(c)
            out = s.run('show bfd neighbors')
        up = len(re.findall(r'\bUp\b', out))
        print(f'{name}: applied bfd to {ifaces}, fall-over on {neighbors} -> bfd neighbors Up={up}')


if __name__ == '__main__':
    main()
