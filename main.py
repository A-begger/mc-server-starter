import os
from dotenv import load_dotenv
from pydo import Client
import time
import subprocess
from cloudflare import Cloudflare
import digitalocean as do

load_dotenv()
client = Client(token=os.getenv("DIGITALOCEAN_TOKEN"))
ssh_user = 'root'
cf_client = Cloudflare(
    api_email=os.environ.get("CLOUDFLARE_EMAIL"),
    api_key=os.environ.get("CLOUDFLARE_API_TOKEN"), 
)
zone_id = '298177d402e015062784b88b0314ea6e'
cf_id = 'c56218dbcc6c69d572703fb60e1'
CF_ZONE_NAME = "ticklerstavern.bar"
CF_RECORD_NAME = "mc.ticklerstavern.bar"
CF_RECORD_NAME_DASHBOARD = "dashboard.ticklerstavern.bar"
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 1800

intel_prem = "s-2vcpu-8gb-160gb-intel"
shared_cpu = "s-4vcpu-8gb"
slug = shared_cpu
def main():
    #do.start()
    #do.stop()
    drop_id = do.drop_id()
    #do.create_snapshot(drop_id)
    print("Done")
main()