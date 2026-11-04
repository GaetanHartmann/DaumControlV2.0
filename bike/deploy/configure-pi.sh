#!/bin/sh
set -eu
# Run with sudo. Only LAN is changed; WLAN and its default route are preserved.
nmcli connection modify netplan-eth0 connection.interface-name eth0 connection.autoconnect yes ipv4.method manual ipv4.addresses 192.168.10.2/24 ipv4.gateway '' ipv4.never-default yes ipv6.method disabled
loginctl enable-linger gha
rfkill unblock bluetooth
# BlueZ may briefly report Busy while rfkill's unblock is powering the adapter.
# Read the actual state rather than treating that transient reply as a failure.
if ! bluetoothctl show | grep -q 'Powered: yes'; then
    bluetoothctl power on || printf 'Bluetooth wird noch aktiviert; Status wird erneut geprueft.\n'
fi
attempt=0
while ! bluetoothctl show | grep -q 'Powered: yes'; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 5 ]; then
        printf 'Bluetooth ist noch ausgeschaltet. LAN und Autostart sind bereits gespeichert.\n' >&2
        exit 1
    fi
    sleep 1
done
nmcli --wait 5 connection up netplan-eth0 || printf 'LAN gespeichert; Aktivierung erfolgt, sobald ein Kabel angeschlossen ist.\n'
printf '\nPi-LAN eingerichtet: 192.168.10.2/24. Autostart aktiviert.\n'
