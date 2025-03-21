#!/bin/python

from flask import Flask
from flask import render_template, request, jsonify, flash, redirect, url_for
import hashlib
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.compute.models import Disk, CreationData, DiskSku
import json
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired
import os, pytz
from flask_migrate import migrate
from flask_login import UserMixin, login_user, login_required, LoginManager, logout_user, current_user


tz = pytz.timezone('Asia/Singapore')
app = Flask(__name__)

# Database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///vm_resource.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.urandom(16)

# Initialise DB
db = SQLAlchemy(app)

# Create Model
class Vm(db.Model):
    name = db.Column(db.String(200), primary_key=True)
    identifier = db.Column(db.String(100), nullable=False)
    ip_address = db.Column(db.String(20), nullable=False)
    restore_from = db.Column(db.String(50), nullable=False)
    source_name = db.Column(db.String(200), nullable=False)
    vm_type = db.Column(db.String(20), nullable=False)

    def __repr__(self):
            return '<Name %r>' % self.name

# Azure authentication
subscription_id = "bc50133c-a33a-4f60-8206-38e15e58fd00"
credential = DefaultAzureCredential()
compute_client = ComputeManagementClient(credential, subscription_id)
resource_group = "offsec-interview-environment"
# Database of admin login
database = {'offsecAdmin': '630f7fbd42a9f5dbb07a5d41c521275fd016dbb17be848a1e0225f60ead80460'}

def check_password(stored_hash, entered_pass):
    hashed = hashlib.sha256(entered_pass.encode())
    if hashed.hexdigest() == stored_hash:
        return True

class AddVmForm(FlaskForm):
    name = StringField("VM Name", validators=[DataRequired()])
    identifier = StringField("Identifier", validators=[DataRequired()])
    ip_address = StringField("IP Address", validators=[DataRequired()])
    restore_from = StringField("Snapshot or Restore Point", validators=[DataRequired()])
    source_name = StringField("Name of Snapshot/Restore Point", validators=[DataRequired()])
    source_collection = StringField("Name of Restore Point Collection")
    submit = SubmitField("Submit")

class RemoveVmForm(FlaskForm):
    name = StringField("VM Name", validators=[DataRequired()])
    submit = SubmitField("Delete")

# Home page
@app.route("/")
def index():
    return render_template("index.html")

# VM Reset page
@app.route("/reset")
def reset():
    vm_list = db.session.execute(db.select(Vm).where(Vm.vm_type == 'target')).scalars()
    return render_template("reset.html", vm_list=vm_list)

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
            vm_list = vm_list = db.session.execute(db.select(Vm).order_by(Vm.name)).scalars()
            return render_template('admin.html', vm_list=vm_list)

@app.route('/addvm', methods=['GET', 'POST'])
def add_vm_page():
    vm_list = db.session.execute(db.select(Vm).order_by(Vm.name)).scalars()
    return render_template("addvm.html", vm_list=vm_list)

@app.route('/addvm/add', methods=['GET', 'POST'])
def add_vm():
    if request.method == 'POST':
        vm_name = request.form["vm_name"]
        vm = db.session.execute(db.select(Vm).filter_by(name=vm_name)).first()
        if vm is None:
            vm = Vm(
                name=vm_name,
                identifier=request.form['identifier'],
                ip_address=request.form["ip_address"],
                restore_from=request.form['restore_from'],
                source_name=request.form['source_name'],
                vm_type=request.form['vm_type']
            )
            db.session.add(vm)
            db.session.commit()
            flash("VM Added")
            return redirect("/addvm")
        else:
            flash("VM already exists")
            return redirect("/addvm")

@app.route('/removevm', methods=['GET', 'POST'])
def remove_vm():
    if request.method == 'POST':
        vm_name = request.form.get('vm_name')
        vm = db.session.execute(db.select(Vm).filter_by(name=vm_name)).scalar_one()
        if vm:
            db.session.delete(vm)
            db.session.commit()
            flash("VM Entry Deleted")
        else:
            flash("VM Not Found")
    vm_list = db.session.execute(db.select(Vm).order_by(Vm.name)).scalars()
    return render_template("removevm.html", vm_list=vm_list)

@app.route('/vm-op', methods=['POST'])
def operate_vm():
    data = request.json
    vm_name = db.session.execute(db.select(Vm.name).filter_by(identifier=data.get("vm_name"))).scalar_one()
    action = data.get("action")
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    if action == "start":
        # Start VM
        print(vm_name + " Starting")
        compute_client.virtual_machines.begin_start(resource_group, vm_name)
        print(vm_name + " started")
        return jsonify({"message": f"VM {vm_name} started successfully."})
    elif action == "stop":
        # Stop VM
        print(vm_name + " Stopping")
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
        else:
            print("Shutting down VM")
            compute_client.virtual_machines.begin_deallocate(resource_group, vm_name)
            print(vm_name + " deallocated")
            # Get resource info of VM (disk id)
            vm = compute_client.virtual_machines.get(resource_group, vm_name)
            old_osdisk_id = vm.storage_profile.os_disk.managed_disk.id
            old_osdisk_name = vm.storage_profile.os_disk.name
            print(vm_name + " creating new disk")
            # Create New Managed Disk from snapshot
            snapshot_source = db.session.execute(db.select(Vm.source_name).filter_by(identifier=data.get("vm_name"))).scalar_one()
            snapshot_id = compute_client.snapshots.get(resource_group, snapshot_source).id
            print(vm_name + " snapshot id: " + snapshot_id)
            new_osdisk_name = vm_name + "-NewOSDisk" + timestamp
            print(vm_name + " old disk id: " + old_osdisk_id)
            disk_param = Disk(
                location = 'southeastasia',
                tags = {
                    'owner': 'Rong An (rong-an.su@cloudasc.net)',
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
            # Start VM
            compute_client.virtual_machines.begin_start(resource_group, vm_name)
            print(vm_name + " started")
            return jsonify({"message": f"VM {vm_name} resetted and started successfully."})



@app.route('/vmreset', methods=['POST'])
def reset_vm():
    data = request.json
    vm_name = db.session.execute(db.select(Vm.name).filter_by(ip_address=data.get("ip_address"))).scalar_one()
    action = data.get("action")
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    if action == "reset":
        if "docker" in vm_name:
            # Reboot VM
            print("Resetting now")
            compute_client.virtual_machines.begin_restart(resource_group, vm_name)
            print(vm_name + " rebooted")
            return jsonify({"message": f"VM {vm_name} resetted successfully."})
        else:
            print("Shutting down VM")
            compute_client.virtual_machines.begin_deallocate(resource_group, vm_name)
            print(vm_name + " deallocated")
            # Get resource info of VM (disk id)
            vm = compute_client.virtual_machines.get(resource_group, vm_name)
            old_osdisk_id = vm.storage_profile.os_disk.managed_disk.id
            old_osdisk_name = vm.storage_profile.os_disk.name
            print(vm_name + " creating new disk")
            # Create New Managed Disk from snapshot
            snapshot_source = db.session.execute(db.select(Vm.source_name).filter_by(identifier=data.get("vm_name"))).scalar_one()
            snapshot_id = compute_client.snapshots.get(resource_group, snapshot_source).id
            print(vm_name + " snapshot id: " + snapshot_id)
            new_osdisk_name = vm_name + "-NewOSDisk" + timestamp
            print(vm_name + " old disk id: " + old_osdisk_id)
            disk_param = Disk(
                location = 'southeastasia',
                tags = {
                    'owner': 'Rong An (rong-an.su@cloudasc.net)',
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
            # Start VM
            compute_client.virtual_machines.begin_start(resource_group, vm_name)
            print(vm_name + " started")
            return jsonify({"message": f"VM {vm_name} resetted and started successfully."})
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

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)