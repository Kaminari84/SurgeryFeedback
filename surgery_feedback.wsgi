#!/usr/bin/python3
import os
import sys

# config instructions: https://www.digitalocean.com/community/tutorials/how-to-deploy-a-flask-application-on-an-ubuntu-vps
path = '/var/www/'
if path not in sys.path: sys.path.append(path)

path = '/var/www/surgery_feedback'
if path not in sys.path: sys.path.append(path)

from surgery_feedback import app as application