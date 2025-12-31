#!/bin/bash
# Run this on Proxmox host to enable SSH access to LXC 104

CTID=104
PUBKEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMLeazfy9Cm9XLmON3Ne/QIhN8bG66Gz9aRdMo3GV8gR richard@mac-mini"

echo "Setting up SSH access to LXC $CTID..."

pct exec $CTID -- mkdir -p /root/.ssh
pct exec $CTID -- bash -c "echo '$PUBKEY' >> /root/.ssh/authorized_keys"
pct exec $CTID -- chmod 700 /root/.ssh
pct exec $CTID -- chmod 600 /root/.ssh/authorized_keys
pct exec $CTID -- apt-get update
pct exec $CTID -- apt-get install -y openssh-server
pct exec $CTID -- systemctl enable ssh
pct exec $CTID -- systemctl start ssh

IP=$(pct exec $CTID -- hostname -I | awk '{print $1}')
echo ""
echo "Done! SSH to: root@$IP"
