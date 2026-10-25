# SearXNG recovery

Watchtower continues to update `searxng` and `gluetun-searxng`. The recovery
job checks both containers every 30 minutes. If Watchtower replaced either one,
the job restarts Gluetun when needed, waits for its VPN health check, and
recreates SearXNG in Gluetun's current network namespace. It also recovers
when either health check fails without a container replacement.

From `setup_coreVMs/docker_main`, deploy the Compose change and recovery script
with your existing single-container script, then install the 30-minute schedule:

```sh
./deploy_single_container.sh searxng
ansible-playbook -i docker_inventory.yml containers/searxng/deploy-recovery.yml --ask-become-pass
```

The single-container deployment script is unchanged. It copies the recovery
script from this directory to `docker_main` at
`/home/fenkil/pcData/searxng/recover-searxng-stack.sh`. Root's cron runs it at
minute 0 and 30 of every hour. The installed Compose project must be at
`/home/fenkil/pcData/searxng/docker-compose.yml`.

To run a recovery check immediately on the host:

```sh
sudo bash /home/fenkil/pcData/searxng/recover-searxng-stack.sh
```

Review `/var/log/recover-searxng-stack.log` for recovery attempts and errors.
The first run records healthy container IDs; if either service is unhealthy, it
attempts recovery immediately.
