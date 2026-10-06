#!/usr/bin/env python3
"""Apply the configs/fmc/ configuration to the FMC through its REST API, in order.
Every step is idempotent: objects are looked up by name before creation.

  fmc_apply.py objects      zones, networks, hosts (configs/fmc/objects.yaml)
  fmc_apply.py acp          access control policy and rule (configs/fmc/acp.yaml)
  fmc_apply.py register     register the four FTDs and wait (configs/fmc/devices.yaml)
  fmc_apply.py interfaces   data interfaces on each pair's primary
  fmc_apply.py ha           create both failover pairs and wait for Active/Standby (configs/fmc/ha.yaml)
  fmc_apply.py standby      standby addresses and interface monitoring on each pair
  fmc_apply.py routes       static routes on each pair
  fmc_apply.py nat          NAT policies, rules, assignment (configs/fmc/nat.yaml)
  fmc_apply.py deploy       deploy pending changes to every deployable device and wait
  fmc_apply.py status       print devices, pairs, deployable devices
"""
import os, sys, time, yaml
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lablib as L

FMC_DIR = os.path.join(L.REPO, 'configs', 'fmc')
CFG = '/api/fmc_config/v1/domain/{domain}'
PLAT = '/api/fmc_platform/v1'


def load(name):
    with open(os.path.join(FMC_DIR, name)) as f: return yaml.safe_load(f)


def log(*a): print(time.strftime('%H:%M:%S'), *a, flush=True)


def find(path, name, extra=''):
    for it in L.fmc_all(f'{CFG}/{path}{extra}'):
        if it.get('name') == name: return it
    return None


def ensure(path, name, body, extra=''):
    it = find(path, name, extra)
    if it:
        if 'value' in body and it.get('value') != body['value']:
            upd = dict(it); upd['value'] = body['value']; upd['description'] = body.get('description', it.get('description', ''))
            upd = {k: v for k, v in upd.items() if k not in ('links', 'metadata')}
            st, h, res = L.fmc('PUT', f'{CFG}/{path}/{it["id"]}', upd)
            if st != 200: raise SystemExit(f'PUT {path} {name} -> {st} {res}')
            log(f'  updated {path} {name} -> {body["value"]}'); return res
        log(f'  exists {path} {name}'); return it
    st, h, res = L.fmc('POST', f'{CFG}/{path}', body)
    if st not in (200, 201, 202): raise SystemExit(f'POST {path} {name} -> {st} {res}')
    log(f'  created {path} {name}'); return res


def wait_task(task_id, what, timeout=1800):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st, h, t = L.fmc('GET', f'{PLAT}/domain/{{domain}}/job/taskstatuses/{task_id}')
        status = (t or {}).get('status', '?') if st == 200 else f'http {st}'
        msg = (t or {}).get('message', '') if st == 200 else str(t)[:120]
        if status in ('Success', 'Deployed', 'SUCCESS'): log(f'  {what}: {status}'); return True
        if status in ('Failed', 'FAILED', 'Failure'): raise SystemExit(f'{what} failed: {msg}')
        log(f'  {what}: {status} {msg[:100]}'); time.sleep(20)
    raise SystemExit(f'{what}: timeout')


# ---------------------------------------------------------------- objects
def objects():
    o = load('objects.yaml')
    log('security zones')
    for z in o['zones']:
        ensure('object/securityzones', z['name'], {'name': z['name'], 'type': 'SecurityZone', 'interfaceMode': z['mode']})
    log('networks')
    for n in o['networks']:
        ensure('object/networks', n['name'], {'name': n['name'], 'type': 'Network', 'value': n['value'], 'description': n.get('description', '')})
    log('hosts')
    for n in o['hosts']:
        ensure('object/hosts', n['name'], {'name': n['name'], 'type': 'Host', 'value': n['value'], 'description': n.get('description', '')})


def obj_ref(name):
    """Resolve an object name to {'id','type','name'} across networks, hosts, and built-ins."""
    for path, typ in (('object/networks', 'Network'), ('object/hosts', 'Host')):
        it = find(path, name)
        if it: return {'id': it['id'], 'type': it.get('type', typ), 'name': name}
    raise SystemExit(f'object not found: {name}')


def zone_ref(name):
    z = find('object/securityzones', name)
    if not z: raise SystemExit(f'zone not found: {name}')
    return {'id': z['id'], 'type': 'SecurityZone', 'name': name}


# ---------------------------------------------------------------- ACP
def acp():
    a = load('acp.yaml')
    pol = ensure('policy/accesspolicies', a['name'], {'type': 'AccessPolicy', 'name': a['name'],
                 'defaultAction': {'action': a['default_action'], 'logBegin': False, 'logEnd': False, 'sendEventsToFMC': False}})
    for r in a['rules']:
        ensure(f'policy/accesspolicies/{pol["id"]}/accessrules', r['name'],
               {'type': 'AccessRule', 'name': r['name'], 'action': r['action'], 'enabled': True,
                'logBegin': False, 'logEnd': bool(r.get('log_end')), 'sendEventsToFMC': True})
    return pol


# ---------------------------------------------------------------- devices
def devices_list():
    return L.fmc_all(f'{CFG}/devices/devicerecords?expanded=true')


def device(name):
    for d in devices_list():
        if d['name'] == name: return d
    return None


def register():
    d = load('devices.yaml')
    pol = find('policy/accesspolicies', d['access_policy'])
    if not pol: raise SystemExit('run acp first')
    tasks = {}
    for dev in d['devices']:
        if device(dev['name']): log(f'  exists device {dev["name"]}'); continue
        body = {'name': dev['name'], 'hostName': dev['mgmt'], 'regKey': d['registration_key'], 'type': 'Device',
                'license_caps': d['license_caps'], 'performanceTier': d['performance_tier'],
                'accessPolicy': {'id': pol['id'], 'type': 'AccessPolicy'}}
        st, h, res = L.fmc('POST', f'{CFG}/devices/devicerecords', body)
        if st == 400 and 'ESSENTIALS' in str(res):
            body['license_caps'] = ['BASE']
            st, h, res = L.fmc('POST', f'{CFG}/devices/devicerecords', body)
        if st not in (200, 201, 202): raise SystemExit(f'register {dev["name"]} -> {st} {res}')
        tid = (res.get('metadata') or {}).get('task', {}).get('id')
        log(f'  registration started {dev["name"]} task {tid}'); tasks[dev['name']] = tid
    if tasks:
        t0 = time.time()
        while time.time() - t0 < 1800:
            recs = {d['name']: d.get('deploymentStatus') for d in devices_list()}
            pending = [n for n in tasks if recs.get(n) not in ('DEPLOYED',)]
            log('  registration:', {n: recs.get(n, 'not yet') for n in tasks})
            if not pending: break
            time.sleep(30)
    for dev in d['devices']:
        rec = device(dev['name'])
        log(f'  {dev["name"]}: {rec.get("model") if rec else "MISSING"} {rec.get("sw_version") if rec else ""} health={ (rec or {}).get("healthStatus") }')


def phys_ifaces(dev_id):
    return L.fmc_all(f'{CFG}/devices/devicerecords/{dev_id}/physicalinterfaces')


def interfaces():
    d = load('devices.yaml')
    for pname, pair in d['pairs'].items():
        prim = next(x for x in d['devices'] if x['pair'] == pname and x['role'] == 'primary')
        rec = device(prim['name'])
        if not rec: raise SystemExit(f'{prim["name"]} not registered')
        log(f'{pname}: interfaces on {prim["name"]}')
        current = {i['name']: i for i in phys_ifaces(rec['id'])}
        for spec in pair['interfaces']:
            cur = current[spec['name']]
            st, h, full = L.fmc('GET', f'{CFG}/devices/devicerecords/{rec["id"]}/physicalinterfaces/{cur["id"]}')
            body = {'type': 'PhysicalInterface', 'id': cur['id'], 'name': spec['name'], 'ifname': spec['ifname'],
                    'enabled': True, 'mode': 'NONE', 'MTU': 1500, 'securityZone': zone_ref(spec['zone']),
                    'ipv4': {'static': {'address': spec['address'], 'netmask': str(spec['mask'])}}}
            if full.get('ifname') == spec['ifname'] and (full.get('ipv4', {}).get('static', {}).get('address') == spec['address']):
                log(f'  unchanged {spec["name"]} {spec["ifname"]} {spec["address"]}/{spec["mask"]}'); continue
            st, h, res = L.fmc('PUT', f'{CFG}/devices/devicerecords/{rec["id"]}/physicalinterfaces/{cur["id"]}', body)
            if st != 200: raise SystemExit(f'PUT interface {spec["name"]} -> {st} {res}')
            log(f'  set {spec["name"]} {spec["ifname"]} {spec["address"]}/{spec["mask"]} zone {spec["zone"]}')


# ---------------------------------------------------------------- HA
def ha_pairs():
    return L.fmc_all(f'{CFG}/devicehapairs/ftddevicehapairs?expanded=true')


def ha_pair(name):
    for p in ha_pairs():
        if p['name'] == name: return p
    return None


def ha_state(p):
    m = p.get('metadata') or {}
    return (m.get('primaryStatus') or {}).get('currentStatus'), (m.get('secondaryStatus') or {}).get('currentStatus')


def ha():
    h = load('ha.yaml')
    created = []
    for pname, spec in h['pairs'].items():
        if ha_pair(pname): log(f'  exists pair {pname}'); continue
        prim, sec = device(spec['primary']), device(spec['secondary'])
        if not (prim and sec): raise SystemExit(f'{pname}: devices not registered')
        ifs = {i['name']: i for i in phys_ifaces(prim['id'])}
        def link(s):
            i = ifs[s['interface']]
            return {'useIPv6Address': False, 'subnetMask': s['mask'], 'logicalName': s['logical'],
                    'activeIP': s['active'], 'standbyIP': s['standby'],
                    'interfaceObject': {'id': i['id'], 'type': 'PhysicalInterface', 'name': s['interface']}}
        body = {'type': 'DeviceHAPair', 'name': pname, 'primary': {'id': prim['id'], 'type': 'Device'},
                'secondary': {'id': sec['id'], 'type': 'Device'},
                'ftdHABootstrap': {'isEncryptionEnabled': bool(spec.get('encryption')), 'useSameLinkForFailovers': False,
                                   'lanFailover': link(spec['failover']), 'statefulFailover': link(spec['state'])}}
        st, hh, res = L.fmc('POST', f'{CFG}/devicehapairs/ftddevicehapairs', body)
        if st not in (200, 201, 202): raise SystemExit(f'create {pname} -> {st} {res}')
        tid = (res.get('metadata') or {}).get('task', {}).get('id')
        log(f'  HA creation started {pname} task {tid}'); created.append((pname, tid))
    wait_ha_converged(list(h['pairs'].keys()), timeout=2400)


def wait_ha_converged(names, timeout=1800):
    t0 = time.time()
    while time.time() - t0 < timeout:
        states = {}
        for n in names:
            p = ha_pair(n); states[n] = ha_state(p) if p else ('missing', 'missing')
        log('  HA states:', states)
        if all(s == ('Active', 'Standby') for s in states.values()): return
        time.sleep(30)
    raise SystemExit('HA pairs did not converge to Active/Standby')


def standby():
    d = load('devices.yaml')
    for pname, pair in d['pairs'].items():
        p = ha_pair(pname)
        if not p: raise SystemExit(f'{pname} missing')
        mon = L.fmc_all(f'{CFG}/devicehapairs/ftddevicehapairs/{p["id"]}/monitoredinterfaces')
        byname = {m['name']: m for m in mon}
        for spec in pair['interfaces']:
            m = byname.get(spec['ifname'])
            if not m: log(f'  WARNING {pname}: monitored interface {spec["ifname"]} not listed ({list(byname)})'); continue
            body = {'id': m['id'], 'type': 'MonitoredInterface', 'name': spec['ifname'], 'monitorForFailures': True,
                    'ipv4Configuration': {'activeIPv4Address': spec['address'], 'activeIPv4Mask': str(spec['mask']),
                                          'standbyIPv4Address': spec['standby']}}
            st, h, res = L.fmc('PUT', f'{CFG}/devicehapairs/ftddevicehapairs/{p["id"]}/monitoredinterfaces/{m["id"]}', body)
            if st != 200: raise SystemExit(f'standby {pname} {spec["ifname"]} -> {st} {res}')
            log(f'  {pname} {spec["ifname"]}: standby {spec["standby"]}, monitored')


# ---------------------------------------------------------------- routes
def pair_device_id(pname):
    """Device-level config on an HA pair is addressed through its primary unit's record."""
    d = load('devices.yaml')
    prim = next(x for x in d['devices'] if x['pair'] == pname and x['role'] == 'primary')
    rec = device(prim['name'])
    if not rec: raise SystemExit(f'{prim["name"]} not registered')
    return rec['id']


def routes():
    d = load('devices.yaml')
    for pname, pair in d['pairs'].items():
        p = ha_pair(pname)
        if not p: raise SystemExit(f'{pname} missing')
        base = f'devices/devicerecords/{pair_device_id(pname)}/routing/ipv4staticroutes'
        existing = L.fmc_all(f'{CFG}/{base}?expanded=true')
        for r in pair['routes']:
            net = obj_ref(r['network']); gw = obj_ref(r['gateway'])
            dup = [e for e in existing if e.get('interfaceName') == r['interface'] and
                   any(n.get('id') == net['id'] for n in e.get('selectedNetworks', []))]
            if dup: log(f'  exists route {pname} {r["network"]} via {r["interface"]}'); continue
            body = {'type': 'IPv4StaticRoute', 'interfaceName': r['interface'], 'selectedNetworks': [net],
                    'gateway': {'object': gw}, 'metricValue': r.get('metric', 1), 'isTunneled': False}
            st, h, res = L.fmc('POST', f'{CFG}/{base}', body)
            if st not in (200, 201): raise SystemExit(f'route {pname} {r} -> {st} {res}')
            log(f'  route {pname}: {r["network"]} via {r["interface"]} -> {r["gateway"]}')


# ---------------------------------------------------------------- NAT
def nat():
    n = load('nat.yaml')
    for polname, spec in n['policies'].items():
        pol = ensure('policy/ftdnatpolicies', polname, {'type': 'FTDNatPolicy', 'name': polname})
        existing = {r.get('description'): r for r in L.fmc_all(f'{CFG}/policy/ftdnatpolicies/{pol["id"]}/manualnatrules?expanded=true')}
        for section in ('before_auto', 'after_auto'):
            for r in spec.get(section, []):
                if r['name'] in existing: log(f'  exists rule {polname} {r["name"]}'); continue
                body = {'type': 'FTDManualNatRule', 'natType': r['type'], 'enabled': True, 'description': r['name'],
                        'sourceInterface': zone_ref(r['src_zone']), 'destinationInterface': zone_ref(r['dst_zone']),
                        'originalSource': obj_ref(r['original']), 'unidirectional': False, 'noProxyArp': False,
                        'routeLookup': False, 'dns': False, 'interfaceInOriginalDestination': False}
                if r['type'] == 'DYNAMIC': body['unidirectional'] = True   # FMC: dynamic NAT cannot be bidirectional
                if r['translated'] == 'interface':
                    body['interfaceInTranslatedSource'] = True
                else:
                    body['interfaceInTranslatedSource'] = False
                    body['translatedSource'] = obj_ref(r['translated'])
                sec = 'before_auto' if section == 'before_auto' else 'after_auto'
                st, h, res = L.fmc('POST', f'{CFG}/policy/ftdnatpolicies/{pol["id"]}/manualnatrules?section={sec}', body)
                if st not in (200, 201): raise SystemExit(f'nat rule {polname} {r["name"]} -> {st} {res}')
                log(f'  rule {polname} [{sec}] {r["name"]}')
        p = ha_pair(spec['target'])
        if not p: raise SystemExit(f'{spec["target"]} missing')
        assigned = [a for a in L.fmc_all(f'{CFG}/assignment/policyassignments?expanded=true')
                    if a.get('policy', {}).get('id') == pol['id']]
        if assigned and any(t.get('id') == p['id'] for a in assigned for t in a.get('targets', [])):
            log(f'  assigned {polname} -> {spec["target"]}'); continue
        st, h, res = L.fmc('POST', f'{CFG}/assignment/policyassignments',
                           {'type': 'PolicyAssignment', 'policy': {'type': 'FTDNatPolicy', 'id': pol['id']},
                            'targets': [{'type': 'DeviceHAPair', 'id': p['id']}]})
        if st not in (200, 201): raise SystemExit(f'assign {polname} -> {st} {res}')
        log(f'  assigned {polname} -> {spec["target"]}')


# ---------------------------------------------------------------- deploy
def deploy():
    items = L.fmc_all(f'{CFG}/deployment/deployabledevices?expanded=true')
    if not items: log('  nothing to deploy'); return
    version = max(i['version'] for i in items)
    ids = [i['device']['id'] if isinstance(i.get('device'), dict) else i['id'] for i in items]
    log('  deploying to', [i.get('name') for i in items], 'version', version)
    st, h, res = L.fmc('POST', f'{CFG}/deployment/deploymentrequests',
                       {'type': 'DeploymentRequest', 'version': version, 'forceDeploy': False, 'ignoreWarning': True, 'deviceList': ids})
    if st not in (200, 202): raise SystemExit(f'deploy -> {st} {res}')
    names = [i.get('name') for i in items]
    wait_deployed(names)


def wait_deployed(names, timeout=2400):
    """Poll device records until none of the named devices is mid-deployment."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        recs = {d['name']: d for d in devices_list()}
        pairs = {p['name']: p for p in ha_pairs()}
        states = {}
        for n in names:
            r = recs.get(n) or pairs.get(n) or {}
            states[n] = r.get('deploymentStatus') or (r.get('metadata') or {}).get('deploymentStatus') or '?'
        pending = {i.get('name') for i in L.fmc_all(f'{CFG}/deployment/deployabledevices?expanded=true')}
        for n in names:
            if states[n] == '?': states[n] = 'PENDING' if n in pending else 'DEPLOYED'
        log('  deployment:', states)
        if all(s in ('DEPLOYED', 'DEPLOYMENT_FAILED', 'FAILED') for s in states.values()):
            if any(s != 'DEPLOYED' for s in states.values()): raise SystemExit(f'deployment failed: {states}')
            return
        time.sleep(30)
    raise SystemExit('deployment timeout')


def status():
    for d in devices_list():
        m = d.get('metadata') or {}
        print(f"device {d['name']:<8} {d.get('model','?'):<12} {d.get('sw_version','?'):<8} health={d.get('healthStatus')} "
              f"container={m.get('containerDetails', {}).get('name') if m.get('containerDetails') else '-'} deploy={d.get('deploymentStatus')}")
    for p in ha_pairs():
        print(f"pair {p['name']}: id={p['id']} state={ha_state(p)}")
    items = L.fmc_all(f'{CFG}/deployment/deployabledevices?expanded=true')
    print('deployable:', [(i.get('name'), i.get('version')) for i in items])


STEPS = {'objects': objects, 'acp': acp, 'register': register, 'interfaces': interfaces, 'ha': ha,
         'standby': standby, 'routes': routes, 'nat': nat, 'deploy': deploy, 'status': status}

if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in STEPS: raise SystemExit(__doc__)
    for step in sys.argv[1:]:
        log(f'== {step}'); STEPS[step]()
