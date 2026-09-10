#!/usr/bin/env python3
"""Drive a node console through CML's SSH console server (port 22, CML user).

  console.py <node-label> [--login user:pass] [--prompt REGEX] -- 'cmd1' 'cmd2' ...

Opens /<lab title>/<node>/0, handles a login prompt if credentials are given,
sends each command, and prints what came back. Used for nodes the pyATS tool
cannot drive (FTD, TRex, Docker hosts).
"""
import os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lablib as L
import pexpect

DEFAULT_PROMPT = r'(?m)^[^\r\n]*[>#\$] ?$'


def open_console(lab_title, node_label, timeout=30, interrupt=True):
    k = L.creds(); host = k['CML_HOST'].replace('https://', '').replace('http://', '').split('/')[0]
    ch = pexpect.spawn(f"ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p 22 {k['CML_USER']}@{host}",
                       timeout=timeout, encoding='utf-8', codec_errors='replace')
    ch.expect(r'[Pp]assword:'); ch.sendline(k['CML_PASS'])
    ch.expect(r'consoles>'); ch.sendline(f'open /{lab_title}/{node_label}/0')
    ch.expect(r'Escape character', timeout=15)
    time.sleep(1)
    if interrupt: ch.send('\x03'); time.sleep(0.5)   # interrupt anything left running
    ch.send('\r')
    return ch


def run(node_label, commands, login=None, prompt=DEFAULT_PROMPT, timeout=30, lab_title=None, settle=0.5, interrupt=True):
    lab_title = lab_title or L.load_state('ids.json')['title']
    ch = open_console(lab_title, node_label, interrupt=interrupt)
    out = {}
    try:
        # settle: reach a prompt, logging in if asked
        for _ in range(6):
            i = ch.expect([r'(?i)login:\s*$', r'(?i)password:\s*$', prompt, pexpect.TIMEOUT], timeout=8)
            if i == 0 and login: ch.send(login.split(':', 1)[0] + '\r')
            elif i == 1 and login: ch.send(login.split(':', 1)[1] + '\r')
            elif i == 2: break
            else: ch.send('\r')
        while True:                                   # drain any queued prompts before the first command
            try: ch.read_nonblocking(4096, timeout=0.7)
            except (pexpect.TIMEOUT, pexpect.EOF): break
        for cmd in commands:
            ch.send(cmd + '\r')          # IOS consoles need CR; Linux and FTD accept it too
            chunks = []
            while True:
                j = ch.expect([r'--More--', prompt, pexpect.TIMEOUT], timeout=timeout)
                chunks.append(ch.before)
                if j == 0: ch.send(' '); continue          # pager: keep going
                if j == 1: chunks.append(ch.after)
                break
            time.sleep(settle)
            text = re.sub(r'\x1b\[[0-9;?]*[A-Za-z]', '', ''.join(chunks))
            text = text.replace('\r', '')
            out[cmd] = text
    finally:
        try: ch.close(force=True)
        except Exception: pass
    return out


if __name__ == '__main__':
    args = sys.argv[1:]
    if '--' not in args: raise SystemExit(__doc__)
    i = args.index('--'); head, cmds = args[:i], args[i + 1:]
    node = head[0]; login = None; prompt = DEFAULT_PROMPT
    if '--login' in head: login = head[head.index('--login') + 1]
    if '--prompt' in head: prompt = head[head.index('--prompt') + 1]
    for cmd, text in run(node, cmds, login=login, prompt=prompt).items():
        print(f'===== {node}: {cmd}\n{text.strip()}\n')


class Session:
    """Persistent console session for repeated commands (tests poll devices often).

        with Session('FTD-A1', login='admin:pw', prompt=r'(?m)^> ?$') as s:
            out = s.run('show failover state')
    """
    def __init__(self, node_label, login=None, prompt=DEFAULT_PROMPT, timeout=30, lab_title=None, interrupt=True):
        self.node, self.login, self.prompt, self.timeout = node_label, login, prompt, timeout
        self.lab_title = lab_title or L.load_state('ids.json')['title']; self.interrupt = interrupt; self.ch = None

    def __enter__(self):
        self.ch = open_console(self.lab_title, self.node, interrupt=self.interrupt)
        ch = self.ch
        for _ in range(6):
            i = ch.expect([r'(?i)login:\s*$', r'(?i)password:\s*$', self.prompt, pexpect.TIMEOUT], timeout=8)
            if i == 0 and self.login: ch.send(self.login.split(':', 1)[0] + '\r')
            elif i == 1 and self.login: ch.send(self.login.split(':', 1)[1] + '\r')
            elif i == 2: break
            else: ch.send('\r')
        self._drain(); return self

    def _drain(self):
        while True:
            try: self.ch.read_nonblocking(4096, timeout=0.5)
            except (pexpect.TIMEOUT, pexpect.EOF): break

    def run(self, cmd, timeout=None):
        ch = self.ch; ch.send(cmd + '\r'); chunks = []
        while True:
            j = ch.expect([r'--More--', self.prompt, pexpect.TIMEOUT], timeout=timeout or self.timeout)
            chunks.append(ch.before)
            if j == 0: ch.send(' '); continue
            if j == 1: chunks.append(ch.after)
            break
        text = re.sub(r'\x1b\[[0-9;?]*[A-Za-z]', '', ''.join(chunks)).replace('\r', '')
        return text

    def __exit__(self, *a):
        try: self.ch.close(force=True)
        except Exception: pass
