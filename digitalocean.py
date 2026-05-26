import os
from dotenv import load_dotenv
from pydo import Client
import time
import subprocess

load_dotenv("secret.env")
client = Client(token=os.getenv("DIGITALOCEAN_TOKEN"))
ssh_user = 'root'

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
            "ssh_keys": [os.getenv("ssh_fingerprint")],
            "backups": False,       
        }
    )
    print("Droplet created successfully.")

def drop_id():
    droplet_info = client.droplets.list()
    id = droplet_info['droplets'][0]['id']
    return id


def drop_ip(drop_id):
    resp = client.droplets.get(drop_id)
    ip = resp['droplet']['networks']['v4'][0]['ip_address']
    return ip


def destroy_droplet(drop_id):
    print("Destroying droplet...")
    client.droplets.destroy(drop_id)


def create_snapshot(drop_id):
    print("Creating snapshot...")
    snapshot_name = f"snapshot-{time.strftime('%Y-%m-%d-%H-%M')}"
    request_body = {
        "type": "snapshot",
        "name": snapshot_name
    }
    response = client.droplet_actions.post(droplet_id=drop_id, body=request_body)

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

def create_droplet_snapshot():
    print("Creating droplet...")
    snapshot = recent_snapshot(list_snapshots())
    client.droplets.create(
        body={
            "name": "mc-server",
            "region": "SGP1",
            "size": "s-4vcpu-8gb",
            "image": snapshot,
            "ssh_keys": [os.getenv("ssh_fingerprint")],
            "backups": False,       
        }
    )
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