import os
import subprocess
import time
import json
import re
import paramiko
import threading
from datetime import datetime
from flask import Flask
from dotenv import load_dotenv
from kthcloud import Kthcloud
from random_word import RandomWords

# Setup
load_dotenv()
client = Kthcloud()
app = Flask(__name__)
start_time = datetime.now().isoformat()

# Prepare SSH key
with open("id_ed25519.pub") as f:
    ssh_key_pub = f.read().strip()

if not os.path.exists("id_ed25519"):
    command = (
        "openssl enc -aes-256-cbc -d -in id_ed25519.enc -out id_ed25519 -k "
        + os.getenv("ENC_KEY")
    )
    subprocess.run(command, shell=True, check=True)

# Set permissions for keyfile
os.chmod("id_ed25519", 0o600)


def create_many(n):
    for _ in range(n):
        client.vms.create(
            cpu_cores=2,
            disk_size=64,
            name=RandomWords().get_random_word(),
            ram=4,
            ssh_public_key=ssh_key_pub,
        )


def teardown(n):
    vms = client.vms.list()
    n = 0
    for vm in vms:
        n += 1
        client.vms.delete(vm.id)
        if n >= n:
            break
    print(f"Deleted {n} vms")


def ssh(vm):
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    match = re.search(r"ssh (\w+)@([\w\.]+) -p (\d+)", vm.ssh_connection_string)
    if not match:
        return ""

    username = match.group(1)
    hostname = match.group(2)
    port = match.group(3)
    print(f"SSH with {username}@{hostname} -p {port}")

    ssh_client.connect(
        hostname=hostname, port=int(port), username=username, key_filename="id_ed25519"
    )

    stdin, stdout, stderr = ssh_client.exec_command("uptime")
    output = stdout.read().decode().strip()

    ssh_client.close()

    return output


def print_statuses(vms):
    statuses = {}
    for vm in vms:
        status = vm.status
        if status in statuses:
            statuses[status] += 1
        else:
            statuses[status] = 1

    output = ""
    for status, count in statuses.items():
        output += f"{status}: {count}, "

    print(output)


def save_state(uptimes):
    with open("data/state.json", "w") as f:
        json.dump(uptimes, f, indent=2)


def load_state():
    try:
        with open("data/state.json") as f:
            return json.load(f)
    except:
        return {}


def main():
    vms = []
    start = time.time()
    uptimes = load_state()

    while True:
        vms = client.vms.list()

        desired = os.getenv("DESIRED_VMS")

        if desired:
            desired = int(desired)
            if len(vms) < desired:
                create_many(desired - len(vms))
                print(f"Adjust - Created {desired - len(vms)} VMs")
                time.sleep(15)
            elif len(vms) > desired:
                teardown(len(vms) - desired)
                print(f"Adjust - Deleted {len(vms) - desired} VMs")
                time.sleep(15)

        print_statuses(vms)
        print("Waiting for " + str(int(time.time() - start)) + " seconds")

        for vm in vms:
            if vm.ssh_connection_string:
                try:
                    time.sleep(5)
                    vm_uptime = ssh(vm)
                    if vm_uptime:
                        print(f"Uptime: {vm_uptime}")
                        uptimes[vm.id] = {"name": vm.name, "uptime": vm_uptime}
                except Exception as e:
                    print(e)

        save_state(uptimes)
        time.sleep(5)


@app.route("/")
def get_state():
    with open("data/state.json") as f:
        uptimes = json.load(f)
        return json.dumps(
            {
                "start_time": start_time,
                "current_time": datetime.now().isoformat(),
                "uptimes": uptimes,
            },
            indent=2,
        )


@app.route("/healthz")
def healthz():
    return "OK"


if __name__ == "__main__":
    thread = threading.Thread(target=main)
    thread.start()

    app.run(host="0.0.0.0", port=8080)
