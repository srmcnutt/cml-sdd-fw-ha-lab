# SRV-B: inside test host behind pair B, public 198.51.100.114
ip address add dev eth0 10.20.0.50/24
ip link set dev eth0 up
ip route add default via 10.20.0.1
command -v iperf3 >/dev/null 2>&1 && iperf3 -s -D
# keep the next line to indicate that the machine is ready
echo "READY" >/dev/console
cat /etc/motd
exit 0
