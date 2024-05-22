import os
import subprocess
import time
import json
import re
import paramiko
from dotenv import load_dotenv
from kthcloud import Kthcloud
from random_word import RandomWords

# Setup
load_dotenv()
client = Kthcloud()

# Prepare SSH key
with open("id_ed25519.pub") as f:
    ssh_key_pub = f.read().strip()

if not os.path.exists("id_ed25519"):
    command = (
        "openssl enc -aes-256-cbc -d -in id_ed25519.enc -out id_ed25519 -k "
        + os.getenv("ENC_KEY")
    )
    subprocess.run(command, shell=True, check=True)


def create_many(n):
    for _ in range(n):
        client.vms.create(
            cpu_cores=1,
            disk_size=10,
            name=RandomWords().get_random_word(),
            ram=1,
            ssh_public_key=ssh_key_pub,
        )


def teardown():
    vms = client.vms.list()
    for vm in vms:
        client.vms.delete(vm.id)
        print(f"Deleted {vm.id}")


def ssh(vm):
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    match = re.search(r"ssh (\w+)@([\w\.]+) -p (\d+)", vm.sshConnectionString)
    if not match:
        return ""

    username = match.group(1)
    hostname = match.group(2)
    port = match.group(3)
    print(f"SSH with {username}@{hostname} -p {port}")

    private_key = paramiko.Ed25519Key(filename="id_ed25519")

    ssh_client.connect(
        hostname=hostname, port=int(port), username=username, pkey=private_key
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


def main():
    # Clean
    teardown()

    # Create VMs
    create_many(1)

    vms = []
    done = False
    start = time.time()
    while not done:
        vms = client.vms.list()
        print_statuses(vms)
        print("Waiting for " + str(int(time.time() - start)) + " seconds")

        for vm in vms:
            if vm.status == "resourceRunning":
                try:
                    time.sleep(5)
                    print(ssh(vm))
                    done = True
                    break
                except Exception as e:
                    print(e)
                    break

        time.sleep(5)

    # Clean again
    teardown()


if __name__ == "__main__":
    main()
