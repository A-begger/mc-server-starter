import os
from dotenv import load_dotenv
from pydo import Client
import time
import subprocess
from cloudflare import Cloudflare

load_dotenv("secret.env")
client = Client(token=os.getenv("DIGITALOCEAN_TOKEN"))
ssh_user = 'root'

cf_client = Cloudflare(
    api_email=os.environ.get("CLOUDFLARE_EMAIL"),
    api_key=os.environ.get("CLOUDFLARE_API_TOKEN"), 
)
zone_id = '298177d402e015062784b88b0314ea6e'
cf_id = 'c56218dbcc6c69d572703fb60e1ed809'
CF_ZONE_NAME = "ticklerstavern.bar"
CF_RECORD_NAME = "mc.ticklerstavern.bar"
CF_RECORD_NAME_DASHBOARD = "dashboard.ticklerstavern.bar"
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 1800


def _unwrap(mapping, key):
    if isinstance(mapping, dict) and key in mapping:
        return mapping[key]
    return mapping


def _wait_for_action(drop_id, action_id, description):
    deadline = time.time() + POLL_TIMEOUT_SECONDS

    while True:
        action = _unwrap(client.droplet_actions.get(drop_id, action_id), "action")
        status = action.get("status")

        if status == "completed":
            return action

        if status == "errored":
            raise RuntimeError(f"{description} failed: {action}")

        if time.time() >= deadline:
            raise TimeoutError(f"Timed out waiting for {description} to finish")

        time.sleep(POLL_INTERVAL_SECONDS)


def _wait_for_droplet_status(drop_id, expected_status, description):
    deadline = time.time() + POLL_TIMEOUT_SECONDS

    while True:
        droplet = _unwrap(client.droplets.get(drop_id), "droplet")
        status = droplet.get("status")

        if status == expected_status:
            return droplet

        if time.time() >= deadline:
            raise TimeoutError(f"Timed out waiting for {description} to finish")

        time.sleep(POLL_INTERVAL_SECONDS)


def _wait_for_droplet_deletion(drop_id, description):
    deadline = time.time() + POLL_TIMEOUT_SECONDS

    while True:
        droplets = _unwrap(client.droplets.list(), "droplets")
        if not any(droplet.get("id") == drop_id for droplet in droplets):
            return

        if time.time() >= deadline:
            raise TimeoutError(f"Timed out waiting for {description} to finish")

        time.sleep(POLL_INTERVAL_SECONDS)

def get_balance():
    balance = client.balance.get()
    return balance
#print(get_balance())

def create_droplet():
    print("Creating droplet...")
    client.droplets.create(
        body={
            "name": "mc-server",
            "region": "SGP1",
            "size": "s-4vcpu-8gb",
            "image": "ubuntu-24-04-x64",
            "ssh_keys": [os.getenv("ssh_fingerprint"), os.getenv("ssh_fingerprint_repl")],
            "backups": False,       
        }
    )
    print("Droplet created successfully.")
    #bind_mc_dns(drop_id())

def drop_id():
    droplet_info = client.droplets.list()
    id = droplet_info['droplets'][0]['id']
    return id


def drop_ip(drop_id):
    resp = client.droplets.get(drop_id)
    ip = resp['droplet']['networks']['v4'][0]['ip_address']
    return ip


def bind_mc_dns(drop_id):
    droplet_ip = drop_ip(drop_id)

    records = cf_client.dns.records.list(
        zone_id=zone_id,
        name=CF_RECORD_NAME,
        type="A",
    )
    record = next(iter(records), None)

    if record is not None:
        cf_client.dns.records.update(
            record.id,
            zone_id=zone_id,
            name=CF_RECORD_NAME,
            type="A",
            content=droplet_ip,
            ttl=1,
            proxied=False,
        )
    else:
        cf_client.dns.records.create(
            zone_id=zone_id,
            name=CF_RECORD_NAME,
            type="A",
            content=droplet_ip,
            ttl=1,
            proxied=False,
        )

    print(f"Bound {CF_RECORD_NAME} to {droplet_ip}.")

def bind_dashboard_dns(drop_id):
    droplet_ip = drop_ip(drop_id)

    records = cf_client.dns.records.list(
        zone_id=zone_id,
        name=CF_RECORD_NAME_DASHBOARD,
        type="A",
    )
    record = next(iter(records), None)

    if record is not None:
        cf_client.dns.records.update(
            record.id,
            zone_id=zone_id,
            name=CF_RECORD_NAME_DASHBOARD,
            type="A",
            content=droplet_ip,
            ttl=1,
            proxied=True,
        )
    else:
        cf_client.dns.records.create(
            zone_id=zone_id,
            name=CF_RECORD_NAME_DASHBOARD,
            type="A",
            content=droplet_ip,
            ttl=1,
            proxied=True,
        )

    print(f"Bound {CF_RECORD_NAME_DASHBOARD} to {droplet_ip}.")

def destroy_droplet(drop_id):
    print("Destroying droplet...")
    client.droplets.destroy(drop_id)
    _wait_for_droplet_deletion(drop_id, "droplet destruction")
    print("Droplet destroyed successfully.")


def create_snapshot(drop_id):
    print("Creating snapshot...")
    snapshot_name = f"snapshot-{time.strftime('%Y-%m-%d-%H-%M')}"
    request_body = {
        "type": "snapshot",
        "name": snapshot_name
    }
    response = client.droplet_actions.post(droplet_id=drop_id, body=request_body)
    action = _unwrap(response, "action")
    _wait_for_action(drop_id, action["id"], "snapshot creation")
    print("Snapshot created successfully.")

def list_snapshots():
    snapshots = client.snapshots.list()
    return snapshots

def ssh(drop_id, ssh_user):
    droplet_ip = drop_ip(drop_id)

    subprocess.run([
        'ssh',
        f'{ssh_user}@{droplet_ip}',
    ], check=True)

def shutdown(drop_id, ssh_user):
    droplet_ip = drop_ip(drop_id)

    subprocess.run([
        'ssh',
        f'{ssh_user}@{droplet_ip}',
        'poweroff',
    ], check=True)
    print("Droplet shutdown initiated.")
    _wait_for_droplet_status(drop_id, "off", "droplet shutdown")
    print("Droplet shutdown completed.")

def create_droplet_snapshot():
    print("Creating droplet...")
    snapshot = recent_snapshot(list_snapshots())
    response = client.droplets.create(
        body={
            "name": "mc-server",
            "region": "SGP1",
            "size": "s-4vcpu-8gb",
            "image": snapshot,
            "ssh_keys": [os.getenv("ssh_fingerprint")],
            "backups": False,       
        }
    )
    droplet = _unwrap(response, "droplet")
    _wait_for_droplet_status(droplet["id"], "active", "droplet creation")
    print("Droplet created from snapshot successfully.")

def recent_snapshot(list_snapshots):
    snapshots = list_snapshots['snapshots']

    # Find the dictionary with the newest 'created_at' date
    most_recent = max(snapshots, key=lambda x: x['created_at'])

    # Extract the IDs
    recent_resource_id = most_recent['resource_id']
    recent_snapshot_id = most_recent['id']

    return recent_snapshot_id

def prune_list(list_snapshots):
    snapshots = list_snapshots['snapshots']
    
    # 1. Sort the snapshots by 'created_at' in descending order (newest first)
    sorted_snapshots = sorted(snapshots, key=lambda x: x['created_at'], reverse=True)

    # 2. Slice the list to skip the first 2 (the ones we want to keep)
    snapshots_to_delete = sorted_snapshots[2:]

    # 3. Extract just the 'id' field for the ones we are deleting
    ids_to_delete = [snap['id'] for snap in snapshots_to_delete]
    
    print(f"Snapshot IDs to delete: {ids_to_delete}")
    return ids_to_delete

def prune_snapshots():
    snapshots = list_snapshots()
    ids_to_delete = prune_list(snapshots)
    for id in ids_to_delete:
        client.snapshots.delete(id)

def start():
    create_droplet_snapshot()
    bind_dashboard_dns(drop_id())
    bind_mc_dns(drop_id())
    #run startup script here
def stop():
    #run exit script here
    drop_id()
    shutdown(drop_id(), ssh_user)
    create_snapshot(drop_id())
    destroy_droplet(drop_id())
    prune_snapshots()