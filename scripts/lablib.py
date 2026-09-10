#!/usr/bin/env python3
"""Shared helpers for the lab scripts: credentials, CML REST, FMC REST.

Credentials come from <repo>/.lab-creds.env (FMC_HOST, FMC_USER, FMC_PASS,
CML_HOST, CML_USER, CML_PASS). Session tokens are cached under <repo>/.cache/.
"""
import base64, json, os, ssl, sys, time, urllib.error, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOPOLOGY = os.path.join(REPO, 'lab', 'topology.yaml')
CREDS = os.path.join(REPO, '.lab-creds.env')
CACHE = os.path.join(REPO, '.cache')
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE


def creds():
    kv = {}
    with open(CREDS) as f:
        for line in f:
            line = line.rstrip('\r\n')
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1); kv[k.strip()] = v.strip()
    return kv


def request(url, method='GET', data=None, headers=None, raw=False, timeout=180):
    body = None
    if data is not None:
        body = data if isinstance(data, (bytes, str)) else json.dumps(data)
        if isinstance(body, str): body = body.encode()
    req = urllib.request.Request(url, method=method, data=body)
    if not (headers and 'Content-Type' in headers): req.add_header('Content-Type', 'application/json')
    for k, v in (headers or {}).items(): req.add_header(k, v)
    try:
        r = urllib.request.urlopen(req, context=CTX, timeout=timeout)
        txt = r.read()
        if raw: return r.status, dict(r.headers), txt
        return r.status, dict(r.headers), (json.loads(txt) if txt.strip() else None)
    except urllib.error.HTTPError as e:
        txt = e.read()
        try: j = json.loads(txt)
        except Exception: j = txt.decode(errors='replace')
        return e.code, dict(e.headers), j


def _cache_get(name, max_age):
    p = os.path.join(CACHE, name)
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < max_age:
        with open(p) as f: return json.load(f)
    return None


def _cache_put(name, obj):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, name)
    with open(p, 'w') as f: json.dump(obj, f)
    os.chmod(p, 0o600)


# ---------------------------------------------------------------- CML
def cml_session(force=False):
    s = None if force else _cache_get('cml_session.json', 25 * 60)
    if s: return s
    k = creds()
    st, h, tok = request(k['CML_HOST'].rstrip('/') + '/api/v0/authenticate', 'POST',
                         {'username': k['CML_USER'], 'password': k['CML_PASS']})
    if st != 200: raise SystemExit(f'CML auth failed: {st} {tok}')
    s = {'host': k['CML_HOST'].rstrip('/'), 'token': tok}
    _cache_put('cml_session.json', s); return s


def cml(method, path, data=None, raw=False, content_type=None, timeout=180):
    s = cml_session()
    hdr = {'Authorization': 'Bearer ' + s['token']}
    if content_type: hdr['Content-Type'] = content_type
    st, h, body = request(s['host'] + path, method, data, headers=hdr, raw=raw, timeout=timeout)
    if st in (401, 403):
        s = cml_session(force=True); hdr['Authorization'] = 'Bearer ' + s['token']
        st, h, body = request(s['host'] + path, method, data, headers=hdr, raw=raw, timeout=timeout)
    return st, h, body


def cml_find_lab(title):
    st, h, ids = cml('GET', '/api/v0/labs')
    for lid in ids or []:
        st, h, d = cml('GET', f'/api/v0/labs/{lid}')
        if st == 200 and d.get('lab_title') == title: return lid, d
    return None, None


# ---------------------------------------------------------------- FMC
def fmc_session(force=False):
    s = None if force else _cache_get('fmc_session.json', 25 * 60)
    if s: return s
    k = creds()
    auth = base64.b64encode(f"{k['FMC_USER']}:{k['FMC_PASS']}".encode()).decode()
    st, h, _ = request(f"https://{k['FMC_HOST']}/api/fmc_platform/v1/auth/generatetoken", 'POST',
                       headers={'Authorization': 'Basic ' + auth})
    if st != 204: raise SystemExit(f'FMC auth failed: {st}')
    s = {'host': k['FMC_HOST'], 'token': h['X-auth-access-token'], 'domain': h['DOMAIN_UUID']}
    _cache_put('fmc_session.json', s); return s


def fmc(method, path, data=None, timeout=180):
    s = fmc_session()
    path = path.replace('{domain}', s['domain'])
    st, h, body = request(f"https://{s['host']}{path}", method, data,
                          headers={'X-auth-access-token': s['token']}, timeout=timeout)
    if st == 401:
        s = fmc_session(force=True); path = path.replace('{domain}', s['domain'])
        st, h, body = request(f"https://{s['host']}{path}", method, data,
                              headers={'X-auth-access-token': s['token']}, timeout=timeout)
    return st, h, body


def fmc_all(path):
    """GET every item of a paged FMC collection."""
    items, offset = [], 0
    while True:
        sep = '&' if '?' in path else '?'
        st, h, body = fmc('GET', f'{path}{sep}offset={offset}&limit=100')
        if st != 200: raise RuntimeError(f'FMC GET {path} -> {st} {body}')
        items += body.get('items', [])
        paging = body.get('paging', {})
        if offset + 100 >= paging.get('count', 0): break
        offset += 100
    return items


def rendered_path():
    """lab/<title>.cml.yaml: the rendered CML import file, named after the lab title in lab/topology.yaml."""
    import yaml
    with open(TOPOLOGY) as f: title = yaml.safe_load(f)['lab']['title']
    return os.path.join(REPO, 'lab', f'{title}.cml.yaml')


def state_path(name):
    d = os.path.join(REPO, 'lab', 'state'); os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def load_state(name):
    p = state_path(name)
    with open(p) as f: return json.load(f)


def save_state(name, obj):
    with open(state_path(name), 'w') as f: json.dump(obj, f, indent=1)


if __name__ == '__main__':
    sysname, method, path = sys.argv[1], sys.argv[2], sys.argv[3]
    data = json.loads(sys.argv[4]) if len(sys.argv) > 4 else None
    st, h, body = (fmc if sysname == 'fmc' else cml)(method, path, data)
    print(f'# {st}', file=sys.stderr)
    print(json.dumps(body, indent=1) if not isinstance(body, (str, bytes)) else body)


def cml_console_tail(lab_id, node_id, n=40, console=0):
    """Return the last n non-empty, ANSI-stripped console lines of a node."""
    import re
    st, h, log = cml('GET', f'/api/v0/labs/{lab_id}/nodes/{node_id}/consoles/{console}/log')
    if st != 200: return [f'console log unavailable: {st} {str(log)[:200]}']
    text = ''.join(e.get('message', '') for e in log) if isinstance(log, list) else str(log)
    text = re.sub(r'\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][0-9A-Za-z]|\x1b\][^\x1b]*\x1b\\\\|\x1b[>=]', '', text)
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    return lines[-n:]
