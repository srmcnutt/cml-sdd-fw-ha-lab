# CLIENT: internet-side test host on ISP-A
ip address add dev eth0 192.0.2.10/29
ip link set dev eth0 up
ip route add default via 192.0.2.9

# keep the next line to indicate that the machine is ready
echo "READY" >/dev/console
cat /etc/motd
exit 0
