import os
import time
import subprocess
import requests
from dotenv import load_dotenv
from cloudflare import Cloudflare
import paramiko

load_dotenv("secret.env")

# Vultr Setup
VULTR_API_KEY = os.getenv("VULTR_API_KEY")
VULTR_URL = "https://api.vultr.com/v2"
HEADERS = {
    "Authorization": f"Bearer {VULTR_API_KEY}",
    "Content-Type": "application/json"
}

ssh_user = 'root'
# Assuming you store comma-separated Vultr SSH Key UUIDs in your env
VULTR_SSH_KEYS = os.getenv("VULTR_SSH_KEY_IDS", "").split(",")

# Cloudflare Setup
cf_client = Cloudflare(
    api_email=os.environ.get("CLOUDFLARE_EMAIL"),
    api_key=os.environ.get("CLOUDFLARE_API_TOKEN"), 
)
zone_id = '298177d402e015062784b88b0314ea6e'
CF_ZONE_NAME = "ticklerstavern.bar"
CF_RECORD_NAME = "mc.ticklerstavern.bar"
CF_RECORD_NAME_DASHBOARD = "dashboard.ticklerstavern.bar"
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 1800

# --- Vultr API Helpers ---

def vultr_get(endpoint):
    response = requests.get(f"{VULTR_URL}/{endpoint}", headers=HEADERS)
    response.raise_for_status()
    return response.json()

def vultr_post(endpoint, payload):
    response = requests.post(f"{VULTR_URL}/{endpoint}", headers=HEADERS, json=payload)
    response.raise_for_status()
    return response.json()

def vultr_delete(endpoint):
    response = requests.delete(f"{VULTR_URL}/{endpoint}", headers=HEADERS)
    response.raise_for_status()
    return response.status_code

# --- Wait Helpers ---

def _wait_for_instance_status(instance_id, expected_status, expected_power_status, description):
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    while True:
        data = vultr_get(f"instances/{instance_id}")
        instance = data.get("instance", {})
        status = instance.get("status")
        power_status = instance.get("power_status")

        if status == expected_status and power_status == expected_power_status:
            return instance

        if time.time() >= deadline:
            raise TimeoutError(f"Timed out waiting for {description} to finish")

        time.sleep(POLL_INTERVAL_SECONDS)

def _wait_for_snapshot_completion(snapshot_id, description):
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    while True:
        data = vultr_get(f"snapshots/{snapshot_id}")
        snapshot = data.get("snapshot", {})
        
        if snapshot.get("status") == "complete":
            return snapshot

        if time.time() >= deadline:
            raise TimeoutError(f"Timed out waiting for {description} to finish")

        time.sleep(POLL_INTERVAL_SECONDS)

def _wait_for_instance_deletion(instance_id, description):
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    while True:
        data = vultr_get("instances")
        instances = data.get("instances", [])
        if not any(inst.get("id") == instance_id for inst in instances):
            return

        if time.time() >= deadline:
            raise TimeoutError(f"Timed out waiting for {description} to finish")

        time.sleep(POLL_INTERVAL_SECONDS)

# --- Server Management ---

def get_balance():
    data = vultr_get("account")
    return data.get("account", {}).get("balance")

def get_instance_id():
    data = vultr_get("instances")
    instances = data.get("instances", [])
    if not instances:
        raise RuntimeError("No instances found.")
    return instances[0]["id"]

def get_instance_ip(instance_id):
    data = vultr_get(f"instances/{instance_id}")
    return data["instance"]["main_ip"]

def create_instance():
    print("Creating instance...")
    payload = {
        "region": "sgp",
        "plan": "vhf-3c-8gb", # Verify this plan ID with Vultr
        "os_id": 2284,        # Vultr's ID for Ubuntu 24.04 x64
        "label": "mc-server",
        "sshkey_id": VULTR_SSH_KEYS,
        "backups": "disabled"
    }
    response = vultr_post("instances", payload)
    instance = response["instance"]
    _wait_for_instance_status(instance["id"], "active", "running", "instance creation")
    print("Instance created successfully.")

def destroy_instance(instance_id):
    print("Destroying instance...")
    vultr_delete(f"instances/{instance_id}")
    _wait_for_instance_deletion(instance_id, "instance destruction")
    print("Instance destroyed successfully.")

# --- DNS Management ---

def bind_mc_dns(instance_id):
    instance_ip = get_instance_ip(instance_id)
    records = cf_client.dns.records.list(zone_id=zone_id, name=CF_RECORD_NAME, type="A")
    record = next(iter(records), None)

    if record is not None:
        cf_client.dns.records.update(
            record.id, zone_id=zone_id, name=CF_RECORD_NAME, type="A",
            content=instance_ip, ttl=1, proxied=False,
        )
    else:
        cf_client.dns.records.create(
            zone_id=zone_id, name=CF_RECORD_NAME, type="A",
            content=instance_ip, ttl=1, proxied=False,
        )
    print(f"Bound {CF_RECORD_NAME} to {instance_ip}.")

def bind_dashboard_dns(instance_id):
    instance_ip = get_instance_ip(instance_id)
    records = cf_client.dns.records.list(zone_id=zone_id, name=CF_RECORD_NAME_DASHBOARD, type="A")
    record = next(iter(records), None)

    if record is not None:
        cf_client.dns.records.update(
            record.id, zone_id=zone_id, name=CF_RECORD_NAME_DASHBOARD, type="A",
            content=instance_ip, ttl=1, proxied=True,
        )
    else:
        cf_client.dns.records.create(
            zone_id=zone_id, name=CF_RECORD_NAME_DASHBOARD, type="A",
            content=instance_ip, ttl=1, proxied=True,
        )
    print(f"Bound {CF_RECORD_NAME_DASHBOARD} to {instance_ip}.")

# --- Snapshot Management ---

def list_snapshots():
    return vultr_get("snapshots")

def create_snapshot(instance_id):
    print("Creating snapshot...")
    snapshot_description = f"snapshot-{time.strftime('%Y-%m-%d-%H-%M')}"
    payload = {
        "instance_id": instance_id,
        "description": snapshot_description
    }
    response = vultr_post("snapshots", payload)
    snapshot = response["snapshot"]
    
    _wait_for_snapshot_completion(snapshot["id"], "snapshot creation")
    print("Snapshot created successfully.")

def recent_snapshot(snapshots_data):
    snapshots = snapshots_data.get('snapshots', [])
    if not snapshots:
        raise RuntimeError("No snapshots found.")
        
    most_recent = max(snapshots, key=lambda x: x['date_created'])
    return most_recent['id']

def prune_list(snapshots_data):
    snapshots = snapshots_data.get('snapshots', [])
    sorted_snapshots = sorted(snapshots, key=lambda x: x['date_created'], reverse=True)
    
    # Keep the newest 2
    snapshots_to_delete = sorted_snapshots[2:]
    ids_to_delete = [snap['id'] for snap in snapshots_to_delete]
    
    print(f"Snapshot IDs to delete: {ids_to_delete}")
    return ids_to_delete

def prune_snapshots():
    snapshots = list_snapshots()
    ids_to_delete = prune_list(snapshots)
    for snap_id in ids_to_delete:
        vultr_delete(f"snapshots/{snap_id}")

def create_instance_snapshot():
    print("Creating instance from snapshot...")
    snapshot_id = recent_snapshot(list_snapshots())
    payload = {
        "region": "sgp",
        "plan": "vc2-4c-8gb",
        "snapshot_id": snapshot_id,
        "label": "mc-server",
        "sshkey_id": VULTR_SSH_KEYS,
        "backups": "disabled"
    }
    response = vultr_post("instances", payload)
    instance = response["instance"]
    
    _wait_for_instance_status(instance["id"], "active", "running", "instance creation")
    print("Instance created from snapshot successfully.")

# --- System Commands ---

def ssh(instance_id, ssh_user):
    instance_ip = get_instance_ip(instance_id)
    subprocess.run([
        'ssh',
        f'{ssh_user}@{instance_ip}',
    ], check=True)

def shutdown(instance_id, ssh_user):
    instance_ip = get_instance_ip(instance_id)
    subprocess.run([
        'ssh',
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'UserKnownHostsFile=/dev/null',
        f'{ssh_user}@{instance_ip}',
        'poweroff',
    ], check=True)
    print("Instance shutdown initiated.")
    
    # Wait for the Vultr API to report the server as stopped
    _wait_for_instance_status(instance_id, "active", "stopped", "instance shutdown")
    print("Instance shutdown completed.")

def get_instance_password(instance_id):
    data = vultr_get(f"instances/{instance_id}")
    return data["instance"]["default_password"]

def p_shutdown(instance_id, ssh_user):
    instance_ip = get_instance_ip(instance_id)
    instance_password = get_instance_password(instance_id)

    # Initialize the SSH client
    ssh = paramiko.SSHClient()
    # Automatically add the server's host key (equivalent to StrictHostKeyChecking=no)
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print(f"Connecting to {instance_ip} via SSH...")
        # Connect using the dynamically fetched password
        ssh.connect(instance_ip, username=ssh_user, password=instance_password)
        
        print("Sending poweroff command...")
        # Execute the shutdown command
        stdin, stdout, stderr = ssh.exec_command('poweroff')
        
    except Exception as e:
        print(f"SSH connection failed: {e}")
    finally:
        ssh.close()

    print("Instance shutdown initiated. Waiting for Vultr API...")
    _wait_for_instance_status(instance_id, "active", "stopped", "instance shutdown")
    print("Instance shutdown completed.")

# --- Main Workflows ---

def start():
    create_instance_snapshot()
    inst_id = get_instance_id()
    bind_dashboard_dns(inst_id)
    bind_mc_dns(inst_id)
    # run startup script here

def stop():
    # run exit script here
    inst_id = get_instance_id()
    p_shutdown(inst_id, ssh_user)
    create_snapshot(inst_id)
    destroy_instance(inst_id)
    prune_snapshots()
stop()