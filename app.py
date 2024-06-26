import os
import subprocess
import time
import json
import re
import paramiko
import threading
from datetime import datetime
from flask import Flask, abort
from flask_cors import CORS
from dotenv import load_dotenv
from kthcloud import Kthcloud
from random_word import RandomWords

# Setup
load_dotenv()
client = Kthcloud()
app = Flask(__name__)
CORS(app)
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


def main():
    vms = []
    start = time.time()
    uptimes = []

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

                        components = vm_uptime.split("up")
                        last_fetch = components[0].strip()
                        uptime = components[1].split(",")[0].strip()

                        new_status = {
                            "name": vm.name,
                            "id": vm.id,
                            "created_at": vm.created_at,
                            "status": vm.status,
                            "last_fetch": last_fetch,
                            "uptime": uptime,
                        }

                        index = next(
                            (
                                index
                                for (index, d) in enumerate(uptimes)
                                if d["id"] == vm.id
                            ),
                            None,
                        )

                        if index is not None:
                            uptimes[index] = new_status
                        else:
                            uptimes.append(new_status)
                except Exception as e:
                    print(e)

        save_state(uptimes)
        time.sleep(5)


@app.route("/")
def get_state():
    try:
        with open("data/state.json") as f:
            uptimes = json.load(f)
            uptimes.sort(key=lambda u: u["created_at"]),
            return json.dumps(
                {
                    "start_time": start_time,
                    "current_time": datetime.now().isoformat(),
                    "uptimes": uptimes,
                },
                indent=2,
            )
    except:
        abort(404)


@app.route("/healthz")
def healthz():
    return "OK"


if __name__ == "__main__":
    thread = threading.Thread(target=main)
    thread.start()

    app.run(host="0.0.0.0", port=8080)
