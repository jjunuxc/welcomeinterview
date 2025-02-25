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
