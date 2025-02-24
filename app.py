#!/bin/python

from flask import Flask
from flask import render_template, request
import hashlib

app = Flask(__name__)

# Database of admin login
database = {'offsecAdmin': '630f7fbd42a9f5dbb07a5d41c521275fd016dbb17be848a1e0225f60ead80460'}

def check_password(stored_hash, entered_pass):
    hashed = hashlib.sha256(entered_pass.encode())
    if hashed.hexdigest() == stored_hash:
        return True

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/reset")
def reset():
    return render_template("reset.html")

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/loginreset", methods=['POST'])
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
