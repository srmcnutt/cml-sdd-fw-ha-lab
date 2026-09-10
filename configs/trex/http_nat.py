"""ASTF profile: simple HTTP, one request/response per connection.

Clients are simulated internet hosts behind the ISP; they connect to the PUBLIC
static-NAT addresses of the TRex server range. The firewall translates those to
the private server range, which is routed to TRex's server-side port. The
server side accepts connections by destination port, so NAT needs no learn
mode. Parameters are set per node by scripts/trex_run.py (see NODES there).

Tunables (kwargs from the client):
  client_start/client_end  source range on port 0
  server_start/server_end  the PUBLIC addresses the clients target
  cps                      new connections per second for this template
  hold                     seconds each connection stays open after the exchange
"""
from trex.astf.api import *


class Prof1:
    def get_profile(self, client_start='192.0.2.33', client_end='192.0.2.62',
                    server_start='198.51.100.33', server_end='198.51.100.46',
                    cps=100, hold=30, **kw):
        http_req = (b'GET /index.html HTTP/1.1\r\nHost: ha-lab\r\nConnection: Keep-Alive\r\n'
                    b'User-Agent: trex-astf\r\nAccept: */*\r\n\r\n')
        body = b'<html>failover lab</html>\n\n'
        http_resp = (b'HTTP/1.1 200 OK\r\nServer: ha-lab\r\nContent-Type: text/html\r\n'
                     b'Content-Length: %d\r\nConnection: Keep-Alive\r\n\r\n' % len(body) + body)
        # client: send request, receive response, hold the connection open, then close
        prog_c = ASTFProgram()
        prog_c.send(http_req)
        prog_c.recv(len(http_resp))
        prog_c.delay(int(hold) * 1_000_000)
        # server: receive request, send response, wait for the client to close
        prog_s = ASTFProgram()
        prog_s.recv(len(http_req))
        prog_s.send(http_resp)
        prog_s.delay(int(hold) * 1_000_000 + 2_000_000)

        ip_gen_c = ASTFIPGenDist(ip_range=[client_start, client_end], distribution='seq')
        ip_gen_s = ASTFIPGenDist(ip_range=[server_start, server_end], distribution='seq')
        ip_gen = ASTFIPGen(glob=ASTFIPGenGlobal(ip_offset='1.0.0.0'), dist_client=ip_gen_c, dist_server=ip_gen_s)

        temp_c = ASTFTCPClientTemplate(program=prog_c, ip_gen=ip_gen, cps=float(cps), port=80)
        temp_s = ASTFTCPServerTemplate(program=prog_s, assoc=ASTFAssociationRule(port=80))
        template = ASTFTemplate(client_template=temp_c, server_template=temp_s)
        return ASTFProfile(default_ip_gen=ip_gen, templates=template)


def register():
    return Prof1()
