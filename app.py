#!/bin/python

from flask import Flask
from flask import render_template, request, jsonify
import hashlib
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.compute.models import Disk, CreationData, DiskSku
import json
from datetime import datetime


app = Flask(__name__)

# Azure authentication
subscription_id = "bc50133c-a33a-4f60-8206-38e15e58fd00"
credential = DefaultAzureCredential()
compute_client = ComputeManagementClient(credential, subscription_id)
resource_group = "offsec-interview-environment"
# Database of admin login
database = {'offsecAdmin': '630f7fbd42a9f5dbb07a5d41c521275fd016dbb17be848a1e0225f60ead80460'}
vm_dict = {
    "kali1":"offsec-kali-vm",
    "kali2":"kali-two-vm",
    "ia1":"ubuntu-docker-vuln",
    "ia2":"docker-two-vm",
    "msubuntu":"metasploit3-ubuntu1404-vm",
    "mswin":"metasploit3-win-vm",
    "basic":"basicpen-2-vuln-vm",
    "win1":"win10-vm"
}

ip_dict = {
    "10.25.1.5":"ubuntu-docker-vuln",
    "10.25.1.7":"docker-two-vm",
    "10.129.23.5":"metasploit3-ubuntu1404-vm",
    "10.129.23.7":"metasploit3-win-vm",
    "10.129.23.6":"basicpen-2-vuln-vm",
}

def check_password(stored_hash, entered_pass):
    hashed = hashlib.sha256(entered_pass.encode())
    if hashed.hexdigest() == stored_hash:
        return True

# Home page
@app.route("/")
def index():
    return render_template("index.html")

# VM Reset page
@app.route("/reset")
def reset():
    return render_template("reset.html")

# Login page
@app.route("/login")
def login_page():
    return render_template("login.html")

# Login authentication
@app.route("/adminreset", methods=['POST'])
def login():
    user = request.form['username']
    pwd = request.form['password']

    if user not in database:
        return render_template('login.html', info='Invalid User')
    else:
        if not check_password(database[user], pwd):
            return render_template('login.html', info='Invalid Pass')
        else:
            return render_template('admin.html', name=user)

# For starting, deallocating, reverting VMs to base
@app.route('/vm', methods=['POST'])
def manage_vm():
    data = request.json
    vm_name = vm_dict[data.get("vm_name")]
    action = data.get("action")
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    if action == "start":
        # Start VM
        compute_client.virtual_machines.begin_start(resource_group, vm_name)
        print(vm_name + " started")
        return jsonify({"message": f"VM {vm_name} started successfully."})
    elif action == "stop":
        # Stop VM
        compute_client.virtual_machines.begin_deallocate(resource_group, vm_name)
        print(vm_name + " deallocated")
        return jsonify({"message": f"VM {vm_name} shut down and deallocated successfully."})
    elif action == "reset":
        if "docker" in vm_name:
            # Reboot VM
            print("Resetting now")
            compute_client.virtual_machines.begin_restart(resource_group, vm_name)
            print(vm_name + " rebooted")
            return jsonify({"message": f"VM {vm_name} resetted successfully."})
        elif "kali" in vm_name:
            # Deallocate vm
            print("Shutting down VM")
            compute_client.virtual_machines.begin_deallocate(resource_group, vm_name).result()
            print(vm_name + " deallocated.")
            # Get resource info of VM (disk id)
            vm = compute_client.virtual_machines.get(resource_group, vm_name)
            old_osdisk_id = vm.storage_profile.os_disk.managed_disk.id
            old_osdisk_name = vm.storage_profile.os_disk.name
            print(vm_name + " creating new disk")
            # Create New Managed Disk from snapshot
            snapshot_id = compute_client.snapshots.get(resource_group, "kali-base-19022025").id
            print(vm_name + " snapshot id: " + snapshot_id)
            new_osdisk_name = vm_name + "-NewOSDisk" + timestamp
            print(vm_name + " old disk id: " + old_osdisk_id)
            # Must be object
            disk_param = Disk(
                location = 'southeastasia',
                tags = {
                    'owner': 'Rong An (rong-an.su@cloudadsc.net)',
                    'engagement_code': 'Cyber Admin (I-19553828)'
                },
                zones = [1],
                sku = DiskSku(name = 'Premium_LRS'),
                creation_data = CreationData(
                    create_option ='Copy',
                    source_resource_id = snapshot_id
                )
            )
            print("Disk Params:", json.dumps(disk_param.as_dict(), indent=2))
            compute_client.disks.begin_create_or_update(resource_group, new_osdisk_name, disk_param).result()
            print(vm_name + " new disk created.")
            # Get new disk ID
            new_osdisk_id = compute_client.disks.get(resource_group, new_osdisk_name).id
            if not new_osdisk_id == old_osdisk_id:
                print("Swapping disk")
                print(vm_name + " old disk name: " + vm.storage_profile.os_disk.name)
                vm.storage_profile.os_disk.managed_disk.id = new_osdisk_id
                vm.storage_profile.os_disk.name = new_osdisk_name
                print(vm_name + " updated disk id: " + vm.storage_profile.os_disk.managed_disk.id)
                print(vm_name + " updated disk name: " + vm.storage_profile.os_disk.name)
                compute_client.virtual_machines.begin_create_or_update(resource_group, vm_name, vm).result()
                print("Disk Swap Successful")
                print("Deleting old os disk")
                compute_client.disks.begin_delete(resource_group, old_osdisk_name).result()
                print("Old Disk deleted.")
            else:
                print("Same ID. Please change the ID and name of new disk")
                return jsonify({"message": f"Unable to swap disk. Change ID and name of new disk"})
            # Start VM
            compute_client.virtual_machines.begin_start(resource_group, vm_name)
            print(vm_name + " started")
            return jsonify({"message": f"VM {vm_name} resetted and started successfully."})
        else:
            # Reset basicpen
            if vm_name == "basicpen-2-vuln-vm":
                # Deallocate vm
                compute_client.virtual_machines.begin_deallocate(resource_group, vm_name).result()
                print(vm_name + " deallocated.")
                # Get resource info of VM (disk id)
                vm = compute_client.virtual_machines.get(resource_group, vm_name)
                old_osdisk_id = vm.storage_profile.os_disk.managed_disk.id
                old_osdisk_name = vm.storage_profile.os_disk.name
                print(vm_name + " creating new disk")
                # Create New Managed Disk from restore point
                restorepoint_id = compute_client.restore_points.get(resource_group, "basicpen-restorepoint", "basicpen-base").source_metadata.storage_profile.os_disk.disk_restore_point.id
                print(vm_name + " restorepoint id: " + restorepoint_id)
                new_osdisk_name = vm_name + "-NewOSDisk" + timestamp 
                print(vm_name + " old disk id: " + old_osdisk_id)
                # Must be object
                disk_param = Disk(
                    location = 'southeastasia',
                    tags = {
                        'owner': 'Rong An (rong-an.su@cloudadsc.net)',
                        'engagement_code': 'Cyber Admin (I-19553828)'
                    },
                    sku = DiskSku(name = 'Premium_LRS'),
                    creation_data = CreationData(
                        create_option ='Restore',
                        source_resource_id = restorepoint_id
                    )
                )
                print("Disk Params:", json.dumps(disk_param.as_dict(), indent=2))
                compute_client.disks.begin_create_or_update(resource_group, new_osdisk_name, disk_param).result()
                print(vm_name + " new disk created.")
                # Get new disk ID
                new_osdisk_id = compute_client.disks.get(resource_group, new_osdisk_name).id
                if not new_osdisk_id == old_osdisk_id:
                    print("Swapping disk")
                    vm.storage_profile.os_disk.managed_disk.id = new_osdisk_id
                    vm.storage_profile.os_disk.name = new_osdisk_name
                    print(vm_name + " updated disk id: " + vm.storage_profile.os_disk.managed_disk.id)
                    print(vm_name + " updated disk name: " + vm.storage_profile.os_disk.name)
                    compute_client.virtual_machines.begin_create_or_update(resource_group, vm_name, vm).result()
                    print("Disk Swap Successful")
                    print("Deleting old os disk")
                    compute_client.disks.begin_delete(resource_group, old_osdisk_name).result()
                    print("Old Disk deleted.")
                else:
                    print("Same ID. Please change the ID and name of new disk")
                    return jsonify({"message": f"Unable to swap disk. Change ID and name of new disk"})
                # Start VM
                compute_client.virtual_machines.begin_start(resource_group, vm_name)
                print(vm_name + " started")
                return jsonify({"message": f"VM {vm_name} resetted and started successfully."})
            
            # Reset windows vm
            elif vm_name == "win10-vm":
                # Deallocate vm
                compute_client.virtual_machines.begin_deallocate(resource_group, vm_name).result()
                print(vm_name + " deallocated.")
                # Get resource info of VM (disk id)
                vm = compute_client.virtual_machines.get(resource_group, vm_name)
                old_osdisk_id = vm.storage_profile.os_disk.managed_disk.id
                old_osdisk_name = vm.storage_profile.os_disk.name
                print(vm_name + " creating new disk")
                # Create New Managed Disk from restore point
                restorepoint_id = compute_client.restore_points.get(resource_group, "win10-vm-restore", "win10-base").source_metadata.storage_profile.os_disk.disk_restore_point.id
                print(vm_name + " restorepoint id: " + restorepoint_id)
                new_osdisk_name = vm_name + "-NewOSDisk" + timestamp  
                print(vm_name + " old disk id: " + old_osdisk_id)
                print(vm_name + " new disk name to be created: " + new_osdisk_name)
                # Must be object
                disk_param = Disk(
                    location = 'southeastasia',
                    tags = {
                        'owner': 'Rong An (rong-an.su@cloudadsc.net)',
                        'engagement_code': 'Cyber Admin (I-19553828)'
                    },
                    zones = [1],
                    sku = DiskSku(name = 'Premium_LRS'),
                    creation_data = CreationData(
                        create_option ='Restore',
                        source_resource_id = restorepoint_id
                    )
                )
                print("Disk Params:", json.dumps(disk_param.as_dict(), indent=2))
                compute_client.disks.begin_create_or_update(resource_group, new_osdisk_name, disk_param).result()
                print(vm_name + " new disk created.")
                # Get new disk ID
                new_osdisk_id = compute_client.disks.get(resource_group, new_osdisk_name).id
                if not new_osdisk_id == old_osdisk_id:
                    print("Swapping disk")
                    vm.storage_profile.os_disk.managed_disk.id = new_osdisk_id
                    vm.storage_profile.os_disk.name = new_osdisk_name
                    print(vm_name + " updated disk id: " + vm.storage_profile.os_disk.managed_disk.id)
                    print(vm_name + " updated disk name: " + vm.storage_profile.os_disk.name)
                    compute_client.virtual_machines.begin_create_or_update(resource_group, vm_name, vm).result()
                    print("Disk Swap Successful")
                    print("Deleting old os disk")
                    compute_client.disks.begin_delete(resource_group, old_osdisk_name).result()
                    print("Old Disk deleted.")
                else:
                    print("Same ID. Please change the ID and name of new disk")
                    return jsonify({"message": f"Unable to swap disk. Change ID and name of new disk"})
                # Start VM
                compute_client.virtual_machines.begin_start(resource_group, vm_name)
                print(vm_name + " started")
                return jsonify({"message": f"VM {vm_name} resetted and started successfully."})
            
            # Reset metasploit ubuntu
            elif vm_name == "metasploit3-ubuntu1404-vm":
                # Deallocate vm
                compute_client.virtual_machines.begin_deallocate(resource_group, vm_name).result()
                print(vm_name + " deallocated.")
                # Get resource info of VM (disk id)
                vm = compute_client.virtual_machines.get(resource_group, vm_name)
                old_osdisk_id = vm.storage_profile.os_disk.managed_disk.id
                old_osdisk_name = vm.storage_profile.os_disk.name
                print(vm_name + " creating new disk")
                # Create New Managed Disk from restore point
                restorepoint_id = compute_client.restore_points.get(resource_group, "metasploit3-ubuntu-restorepoint", "metasploit3-ubuntu-base-rp").source_metadata.storage_profile.os_disk.disk_restore_point.id
                print(vm_name + " restorepoint id: " + restorepoint_id)
                new_osdisk_name = vm_name + "-NewOSDisk" + timestamp
                print(vm_name + " old disk id: " + old_osdisk_id)
                # Must be object
                disk_param = Disk(
                    location = 'southeastasia',
                    tags = {
                        'owner': 'Rong An (rong-an.su@cloudadsc.net)',
                        'engagement_code': 'Cyber Admin (I-19553828)'
                    },
                    zones = [2],
                    sku = DiskSku(name = 'Premium_LRS'),
                    creation_data = CreationData(
                        create_option ='Restore',
                        source_resource_id = restorepoint_id
                    )
                )
                print("Disk Params:", json.dumps(disk_param.as_dict(), indent=2))
                compute_client.disks.begin_create_or_update(resource_group, new_osdisk_name, disk_param).result()
                print(vm_name + " new disk created.")
                # Get new disk ID
                new_osdisk_id = compute_client.disks.get(resource_group, new_osdisk_name).id
                if not new_osdisk_id == old_osdisk_id:
                    print("Swapping disk")
                    vm.storage_profile.os_disk.managed_disk.id = new_osdisk_id
                    vm.storage_profile.os_disk.name = new_osdisk_name
                    print(vm_name + " updated disk id: " + vm.storage_profile.os_disk.managed_disk.id)
                    print(vm_name + " updated disk name: " + vm.storage_profile.os_disk.name)
                    compute_client.virtual_machines.begin_create_or_update(resource_group, vm_name, vm).result()
                    print("Disk Swap Successful")
                    print("Deleting old os disk")
                    compute_client.disks.begin_delete(resource_group, old_osdisk_name).result()
                    print("Old Disk deleted.")
                else:
                    print("Same ID. Please change the ID and name of new disk")
                    return jsonify({"message": f"Unable to swap disk. Change ID and name of new disk"})
                # Start VM
                compute_client.virtual_machines.begin_start(resource_group, vm_name)
                print(vm_name + " started")
                return jsonify({"message": f"VM {vm_name} resetted and started successfully."})
            
            # Reset metasploit win
            elif vm_name == "metasploit3-win-vm":
                # Deallocate vm
                compute_client.virtual_machines.begin_deallocate(resource_group, vm_name).result()
                print(vm_name + " deallocated.")
                # Get resource info of VM (disk id)
                vm = compute_client.virtual_machines.get(resource_group, vm_name)
                old_osdisk_id = vm.storage_profile.os_disk.managed_disk.id
                old_osdisk_name = vm.storage_profile.os_disk.name
                print(vm_name + " creating new disk")
                # Create New Managed Disk from restore point
                restorepoint_id = compute_client.restore_points.get(resource_group, "metasploit3-win-restorepoint", "metasploit3-win-base-rp").source_metadata.storage_profile.os_disk.disk_restore_point.id
                print(vm_name + " restorepoint id: " + restorepoint_id)
                new_osdisk_name = vm_name + "-NewOSDisk" + timestamp  
                print(vm_name + " old disk id: " + old_osdisk_id)
                print(vm_name + " new disk name to be created: " + new_osdisk_name)
                # Must be object
                disk_param = Disk(
                    location = 'southeastasia',
                    tags = {
                        'owner': 'Rong An (rong-an.su@cloudadsc.net)',
                        'engagement_code': 'Cyber Admin (I-19553828)'
                    },
                    zones = [2],
                    sku = DiskSku(name = 'Premium_LRS'),
                    creation_data = CreationData(
                        create_option ='Restore',
                        source_resource_id = restorepoint_id
                    )
                )
                print("Disk Params:", json.dumps(disk_param.as_dict(), indent=2))
                compute_client.disks.begin_create_or_update(resource_group, new_osdisk_name, disk_param).result()
                print(vm_name + " new disk created.")
                # Get new disk ID
                new_osdisk_id = compute_client.disks.get(resource_group, new_osdisk_name).id
                if not new_osdisk_id == old_osdisk_id:
                    print("Swapping disk")
                    vm.storage_profile.os_disk.managed_disk.id = new_osdisk_id
                    vm.storage_profile.os_disk.name = new_osdisk_name
                    print(vm_name + " updated disk id: " + vm.storage_profile.os_disk.managed_disk.id)
                    print(vm_name + " updated disk name: " + vm.storage_profile.os_disk.name)
                    compute_client.virtual_machines.begin_create_or_update(resource_group, vm_name, vm).result()
                    print("Disk Swap Successful")
                    print("Deleting old os disk")
                    compute_client.disks.begin_delete(resource_group, old_osdisk_name).result()
                    print("Old Disk deleted.")
                else:
                    print("Same ID. Please change the ID and name of new disk")
                    return jsonify({"message": f"Unable to swap disk. Change ID and name of new disk"})
                # Start VM
                compute_client.virtual_machines.begin_start(resource_group, vm_name)
                print(vm_name + " started")
                return jsonify({"message": f"VM {vm_name} resetted and started successfully."})

@app.route('/vmreset', methods=['POST'])
def reset_vm():
    data = request.json
    vm_name = ip_dict[data.get("vm_name")]
    action = data.get("action")
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    if action == "reset":
        if "docker" in vm_name:
            # Reboot VM
            print("Resetting now")
            compute_client.virtual_machines.begin_restart(resource_group, vm_name)
            print(vm_name + " rebooted")
            return jsonify({"message": f"{data.get("vm_name")} resetted successfully."})
        
        else:
            # Reset basicpen
            if vm_name == "basicpen-2-vuln-vm":
                # Deallocate vm
                compute_client.virtual_machines.begin_deallocate(resource_group, vm_name).result()
                print(vm_name + " deallocated.")
                # Get resource info of VM (disk id)
                vm = compute_client.virtual_machines.get(resource_group, vm_name)
                old_osdisk_id = vm.storage_profile.os_disk.managed_disk.id
                old_osdisk_name = vm.storage_profile.os_disk.name
                print(vm_name + " creating new disk")
                # Create New Managed Disk from restore point
                restorepoint_id = compute_client.restore_points.get(resource_group, "basicpen-restorepoint", "basicpen-base").source_metadata.storage_profile.os_disk.disk_restore_point.id
                print(vm_name + " restorepoint id: " + restorepoint_id)
                new_osdisk_name = vm_name + "-NewOSDisk" + timestamp 
                print(vm_name + " old disk id: " + old_osdisk_id)
                # Must be object
                disk_param = Disk(
                    location = 'southeastasia',
                    tags = {
                        'owner': 'Rong An (rong-an.su@cloudadsc.net)',
                        'engagement_code': 'Cyber Admin (I-19553828)'
                    },
                    sku = DiskSku(name = 'Premium_LRS'),
                    creation_data = CreationData(
                        create_option ='Restore',
                        source_resource_id = restorepoint_id
                    )
                )
                print("Disk Params:", json.dumps(disk_param.as_dict(), indent=2))
                compute_client.disks.begin_create_or_update(resource_group, new_osdisk_name, disk_param).result()
                print(vm_name + " new disk created.")
                # Get new disk ID
                new_osdisk_id = compute_client.disks.get(resource_group, new_osdisk_name).id
                if not new_osdisk_id == old_osdisk_id:
                    print("Swapping disk")
                    vm.storage_profile.os_disk.managed_disk.id = new_osdisk_id
                    vm.storage_profile.os_disk.name = new_osdisk_name
                    print(vm_name + " updated disk id: " + vm.storage_profile.os_disk.managed_disk.id)
                    print(vm_name + " updated disk name: " + vm.storage_profile.os_disk.name)
                    compute_client.virtual_machines.begin_create_or_update(resource_group, vm_name, vm).result()
                    print("Disk Swap Successful")
                    print("Deleting old os disk")
                    compute_client.disks.begin_delete(resource_group, old_osdisk_name).result()
                    print("Old Disk deleted.")
                else:
                    print("Same ID. Please change the ID and name of new disk. Or timestamp may not have updated properly.")
                    return jsonify({"message": f"Error has occured. Please contact administrator."})
                # Start VM
                compute_client.virtual_machines.begin_start(resource_group, vm_name)
                print(vm_name + " started")
                return jsonify({"message": f"{data.get("vm_name")} resetted and started successfully."})
            
            # Reset metasploit ubuntu
            elif vm_name == "metasploit3-ubuntu1404-vm":
                # Deallocate vm
                compute_client.virtual_machines.begin_deallocate(resource_group, vm_name).result()
                print(vm_name + " deallocated.")
                # Get resource info of VM (disk id)
                vm = compute_client.virtual_machines.get(resource_group, vm_name)
                old_osdisk_id = vm.storage_profile.os_disk.managed_disk.id
                old_osdisk_name = vm.storage_profile.os_disk.name
                print(vm_name + " creating new disk")
                # Create New Managed Disk from restore point
                restorepoint_id = compute_client.restore_points.get(resource_group, "metasploit3-ubuntu-restorepoint", "metasploit3-ubuntu-base-rp").source_metadata.storage_profile.os_disk.disk_restore_point.id
                print(vm_name + " restorepoint id: " + restorepoint_id)
                new_osdisk_name = vm_name + "-NewOSDisk" + timestamp
                print(vm_name + " old disk id: " + old_osdisk_id)
                # Must be object
                disk_param = Disk(
                    location = 'southeastasia',
                    tags = {
                        'owner': 'Rong An (rong-an.su@cloudadsc.net)',
                        'engagement_code': 'Cyber Admin (I-19553828)'
                    },
                    zones = [2],
                    sku = DiskSku(name = 'Premium_LRS'),
                    creation_data = CreationData(
                        create_option ='Restore',
                        source_resource_id = restorepoint_id
                    )
                )
                print("Disk Params:", json.dumps(disk_param.as_dict(), indent=2))
                compute_client.disks.begin_create_or_update(resource_group, new_osdisk_name, disk_param).result()
                print(vm_name + " new disk created.")
                # Get new disk ID
                new_osdisk_id = compute_client.disks.get(resource_group, new_osdisk_name).id
                if not new_osdisk_id == old_osdisk_id:
                    print("Swapping disk")
                    vm.storage_profile.os_disk.managed_disk.id = new_osdisk_id
                    vm.storage_profile.os_disk.name = new_osdisk_name
                    print(vm_name + " updated disk id: " + vm.storage_profile.os_disk.managed_disk.id)
                    print(vm_name + " updated disk name: " + vm.storage_profile.os_disk.name)
                    compute_client.virtual_machines.begin_create_or_update(resource_group, vm_name, vm).result()
                    print("Disk Swap Successful")
                    print("Deleting old os disk")
                    compute_client.disks.begin_delete(resource_group, old_osdisk_name).result()
                    print("Old Disk deleted.")
                else:
                    print("Same ID. Please change the ID and name of new disk. Or timestamp may not have updated properly.")
                    return jsonify({"message": f"Error has occured. Please contact administrator."})
                # Start VM
                compute_client.virtual_machines.begin_start(resource_group, vm_name)
                print(vm_name + " started")
                return jsonify({"message": f"{data.get("vm_name")} resetted and started successfully."})
            
            # Reset metasploit win
            elif vm_name == "metasploit3-win-vm":
                # Deallocate vm
                compute_client.virtual_machines.begin_deallocate(resource_group, vm_name).result()
                print(vm_name + " deallocated.")
                # Get resource info of VM (disk id)
                vm = compute_client.virtual_machines.get(resource_group, vm_name)
                old_osdisk_id = vm.storage_profile.os_disk.managed_disk.id
                old_osdisk_name = vm.storage_profile.os_disk.name
                print(vm_name + " creating new disk")
                # Create New Managed Disk from restore point
                restorepoint_id = compute_client.restore_points.get(resource_group, "metasploit3-win-restorepoint", "metasploit3-win-base-rp").source_metadata.storage_profile.os_disk.disk_restore_point.id
                print(vm_name + " restorepoint id: " + restorepoint_id)
                new_osdisk_name = vm_name + "-NewOSDisk" + timestamp  
                print(vm_name + " old disk id: " + old_osdisk_id)
                print(vm_name + " new disk name to be created: " + new_osdisk_name)
                # Must be object
                disk_param = Disk(
                    location = 'southeastasia',
                    tags = {
                        'owner': 'Rong An (rong-an.su@cloudadsc.net)',
                        'engagement_code': 'Cyber Admin (I-19553828)'
                    },
                    zones = [2],
                    sku = DiskSku(name = 'Premium_LRS'),
                    creation_data = CreationData(
                        create_option ='Restore',
                        source_resource_id = restorepoint_id
                    )
                )
                print("Disk Params:", json.dumps(disk_param.as_dict(), indent=2))
                compute_client.disks.begin_create_or_update(resource_group, new_osdisk_name, disk_param).result()
                print(vm_name + " new disk created.")
                # Get new disk ID
                new_osdisk_id = compute_client.disks.get(resource_group, new_osdisk_name).id
                if not new_osdisk_id == old_osdisk_id:
                    print("Swapping disk")
                    vm.storage_profile.os_disk.managed_disk.id = new_osdisk_id
                    vm.storage_profile.os_disk.name = new_osdisk_name
                    print(vm_name + " updated disk id: " + vm.storage_profile.os_disk.managed_disk.id)
                    print(vm_name + " updated disk name: " + vm.storage_profile.os_disk.name)
                    compute_client.virtual_machines.begin_create_or_update(resource_group, vm_name, vm).result()
                    print("Disk Swap Successful")
                    print("Deleting old os disk")
                    compute_client.disks.begin_delete(resource_group, old_osdisk_name).result()
                    print("Old Disk deleted.")
                else:
                    print("Same ID. Please change the ID and name of new disk. Or timestamp may not have updated properly.")
                    return jsonify({"message": f"Error has occured. Please contact administrator."})
                # Start VM
                compute_client.virtual_machines.begin_start(resource_group, vm_name)
                print(vm_name + " started")
                return jsonify({"message": f"{data.get("vm_name")} resetted and started successfully."})
            
    else:
        print("Parameter unallowed. Abnormal behavior detected.")
        return jsonify({"message": f"Unpermitted Action."})
            
# Page not found error
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

# Internal error
@app.errorhandler(500)
def page_not_found(e):
    return render_template("500.html"), 500

# Method not allowed error
@app.errorhandler(405)
def not_allowed(e):
    return render_template("405.html"), 405
