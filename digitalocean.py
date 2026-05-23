import os
from dotenv import load_dotenv
from pydo import Client
import time
load_dotenv("secret.env")
client = Client(token=os.getenv("DIGITALOCEAN_TOKEN"))

def get_balance():
    balance = client.balance.get()
    return balance
#print(get_balance())

def create_droplet():
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

def drop_id():
    droplets = client.droplets.list()
    id = droplets['droplets'][0]['id']
    return id

def destroy_droplet(drop_id):
    client.droplets.destroy(drop_id)
