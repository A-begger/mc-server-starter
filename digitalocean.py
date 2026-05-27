import os
import json
from dotenv import load_dotenv
from pydo import Client
import time
import subprocess
from urllib import request, error
from cloudflare import Cloudflare

load_dotenv("secret.env")
client = Client(token=os.getenv("DIGITALOCEAN_TOKEN"))
ssh_user = 'root'
cloudflare_api_token = os.getenv("cloudflare_api_token")
zone_name = "ticklerstavern.bar"
mc_record_name = f"mc.{zone_name}"


def _cloudflare_headers():
    if not cloudflare_api_token:
        raise RuntimeError("Missing cloudflare_api_token in secret.env")

    return {
        "Authorization": f"Bearer {os.getenv('cloudflare_api_token')}",
        "Content-Type": "application/json",
    }


def _cloudflare_request(method, url, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, method=method, headers=_cloudflare_headers())
    try:
        with request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"Cloudflare API request failed: {exc.code} {body}") from exc


def _extract_droplet_id(response):
    if isinstance(response, dict):
        if "droplet" in response and isinstance(response["droplet"], dict):
            return response["droplet"].get("id")
        return response.get("id")

    droplet = getattr(response, "droplet", None)
    if droplet is not None:
        return getattr(droplet, "id", None)

    return None

def get_balance():
    balance = client.balance.get()
    return balance
#print(get_balance())

def create_droplet():
    print("Creating droplet...")
    response = client.droplets.create(
        body={
            "name": "mc-server",
            "region": "SGP1",
            "size": "s-4vcpu-8gb",
            "image": "ubuntu-24-04-x64",
            "ssh_keys": [os.getenv("ssh_fingerprint")],
            "backups": False,       
        }
    )
    droplet_id = _extract_droplet_id(response) or drop_id()
    bind_cloudflare_record(droplet_id)
    print("Droplet created successfully.")
    return droplet_id

def drop_id():
    droplet_info = client.droplets.list()
    id = droplet_info['droplets'][0]['id']
    return id


def drop_ip(drop_id, retries=30, delay=10):
    for attempt in range(retries):
        resp = client.droplets.get(drop_id)
        v4_networks = resp['droplet']['networks'].get('v4', [])
        public_ipv4 = next(
            (network['ip_address'] for network in v4_networks if network.get('type') == 'public'),
            None,
        )
        if public_ipv4:
            return public_ipv4

        if attempt < retries - 1:
            time.sleep(delay)

    raise RuntimeError(f"Unable to find a public IPv4 for droplet {drop_id}")


def bind_cloudflare_record(drop_id):
    droplet_ip = drop_ip(drop_id)

    zone_lookup = _cloudflare_request(
        "GET",
        f"https://api.cloudflare.com/client/v4/zones?name={zone_name}&status=active&per_page=1",
    )
    if not zone_lookup.get("success") or not zone_lookup.get("result"):
        raise RuntimeError(f"Cloudflare zone not found: {zone_name}")

    #zone_id = zone_lookup["result"][0]["id"]
    zone_id = 'c56218dbcc6c69d572703fb60e1ed809'
    all_records = _cloudflare_request(
        "GET",
        f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records?name={mc_record_name}&per_page=100",
    )

    if all_records.get("success") and all_records.get("result"):
        for record in all_records["result"]:
            if record.get("type") != "A":
                _cloudflare_request(
                    "DELETE",
                    f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record['id']}",
                )

    record_lookup = _cloudflare_request(
        "GET",
        f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records?type=A&name={mc_record_name}&per_page=1",
    )

    payload = {
        "type": "A",
        "name": mc_record_name,
        "content": droplet_ip,
        "ttl": 1,
        "proxied": False,
    }

    if record_lookup.get("success") and record_lookup.get("result"):
        record_id = record_lookup["result"][0]["id"]
        _cloudflare_request(
            "PUT",
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}",
            payload,
        )
    else:
        _cloudflare_request(
            "POST",
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
            payload,
        )

    print(f"Bound {mc_record_name} to {droplet_ip}.")
    return droplet_ip


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
    droplet_id = drop_id()
    print("Droplet created from snapshot successfully.")
    return droplet_id

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

def start_server():
    create_droplet_snapshot()
    time.sleep(30)
    droplet_id = drop_id()
    #some kind of startup script - using ssh

def stop_server():
    droplet_id = drop_id()
    #probably run some exit script for mc
    shutdown(droplet_id, ssh_user)
    time.sleep(25)
    create_snapshot(droplet_id)
    time.sleep(30)
    prune_snapshots()
    destroy_droplet(droplet_id)

cl_client = Cloudflare(api_token=os.getenv("cloudflare_api_token"))
def zone_test():
    zone = cl_client.zones.create(
        account={"id": "c56218dbcc6c69d572703fb60e1ed809"},
        name="ticklerstavern.bar",
        type="full",
    )

bind_cloudflare_record(drop_id())