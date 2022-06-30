import os
import sys
import logging
import random
import json
import uuid
from datetime import datetime
import time
import pytz
from datetime import datetime, timedelta
from pytz import timezone
from pytz import common_timezones
from pytz import country_timezones

from flask import Flask, request, make_response, render_template, current_app, g
from flask import redirect, url_for
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
import sqlalchemy
from sqlalchemy import func
from sqlalchemy.orm import relationship

from flask_cors import CORS

import socket # for non HTTP network communication

basedir = os.path.abspath(os.path.dirname(__file__))
ENV_VARS = {}
app = Flask(__name__, static_folder='static')

app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['EXPLAIN_TEMPLATE_LOADING'] = True
env = app.jinja_env
env.add_extension("jinja2.ext.loopcontrols") #Loop extension to enable {% break %}

UPLOAD_FOLDER = os.path.join(basedir, 'static/video')
ALLOWED_EXTENSIONS = {'mp4'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

app.app_context().push()
CORS(app)

db = SQLAlchemy()

file_handler = logging.FileHandler(filename=os.path.join(app.root_path,'logs/app_'+time.strftime('%d-%m-%Y-%H-%M-%S')+'.log'))
stdout_handler = logging.StreamHandler(sys.stdout)
handlers = [file_handler, stdout_handler]

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s',
                    handlers=handlers)
logging.info("Server loading...")

# Load environmental variables
def load_env(filename):
  with open(filename) as myfile:
    for line in myfile:
      name, var = line.rstrip('\n').partition("=")[::2]
      ENV_VARS[name.strip()] = var

# Date-Time helpers
def utcnow():
  return datetime.now(tz=pytz.utc)

def pstnow():
  utc_time = utcnow()
  pacific = timezone('US/Pacific')
  pst_time = utc_time.astimezone(pacific)
  return pst_time

# Server instance initialize
def setup_app(app):
  global db

  logging.info("Initializing the server, first load env variables...")
  logging.info("Root path: %s" % app.root_path)

  # Load environmental variables
  load_env(os.path.join(app.root_path,"variables.env"))

  # Initialize the database
  logging.info("Initialize the database...")

  #db_name = ENV_VARS.get('DB_NAME')
  #db_user = ENV_VARS.get('DB_USER')
  #db_pass = ENV_VARS.get('DB_PASS')

  #app.config['SQLALCHEMY_DATABASE_URI'] = "mysql+pymysql://"+str(db_user)+":"+str(db_pass)+"@127.0.0.1:3306/"+str(db_name)
  #app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
  #app.config['SQLALCHEMY_POOL_RECYCLE'] = 1

  #logging.info("DB access string: %s" % app.config['SQLALCHEMY_DATABASE_URI'])
  #db.init_app(app)

  # Create all database tables
  #logging.info("Create DB tables...")
  #db.create_all()

  # Initialize global application context
  logging.info("Initialize global application context...")
  with app.app_context():
    # within this block, current_app points to app.
    logging.info("App name: %s" % current_app.name)

  logging.info("Initialization complete, start the actual server...")

setup_app(app)

## VIDEO FEEDBACK INTERFACE ##
@app.route('/', methods = ['GET','POST'])
def main_page():
  needle_handling_skill = safe_cast(request.args.get('needle_handling_skill'), int, default=None)
  logging.info("Needle handling skill:"+str(needle_handling_skill))

  needle_driving_skill = safe_cast(request.args.get('needle_driving_skill'), int, default=None)
  logging.info("Needle driving skill:"+str(needle_driving_skill))

  domain_specs = [ 
    {
      "skill": needle_handling_skill, "skill_var_name": "needle_handling_skill", 
      "domain_name": "Needle Handling (Needle Repositions)",
      "ideal_level": {"encouragement": "Good work!", 
                      "general_assessment": "Your gestures show intent.",
                      "issue_list_intro": "You accomplishments:",
                      "issues": ["Fewer than 2 re-positions of the needle happend.", 
                                 "You adjusted needle grasp position based on depth of bite."]},

      "fail_level": {"encouragement": "Almost there!", 
                      "general_assessment": "Still, your gesture sequence shows little to no intent.",
                      "issue_list_intro": "Possible issues (compare with ideal video on the right):",
                      "issues": ["Likely more than 3 re-positions of the needle happend", 
                                 "You grasped the needle outside of the acceptable range."]
                      }
    },
    {
      "skill": needle_driving_skill, "skill_var_name": "needle_driving_skill", 
      "domain_name": "Needle Driving (Driving Smoothness)",
      "ideal_level": {"encouragement": "Good work!", 
                      "general_assessment": "Your needle driving is smooth.",
                      "issue_list_intro": "You accomplishments:",
                      "issues": ["Smooth, continuous motion", 
                                 "Maximum 1 adjustment during driving (no complete withdrawal of needle)",
                                 "Maximum 1 additional re-grab of needle"]},

      "fail_level": {"encouragement": "Almost there!", 
                      "general_assessment": "Still, your needle driving could be improved.",
                      "issue_list_intro": "Possible issues (compare with ideal video on the right):",
                      "issues": ["More then 2 adjustments during driving", 
                                 "2 or more additional regrabs of needle",
                                 "Complete removal of needle (reverse progress) and re-drive"]
                      }
    }
  ]

  resp = make_response(render_template('video_playback.html', 
                            domain_specs = domain_specs)
                      )
  return resp

## UPLOADING VIDEO FILES ##
# https://dev.to/nagatodev/uploading-media-files-to-your-flask-application-5h9k
@app.route('/video_upload', methods=['POST','GET'])
def video_upload():
  logging.info("Trying to upload video file!")
  video_files = os.listdir(os.path.join(app.root_path,'static/video/'))

  message = None
  status = None

  if request.method == 'POST':
    # check if the post request has the file part
    if 'file' not in request.files:
      status = "ERROR"
      message = "File part missing in request!"      
      #return redirect(request.url)
    else:
      file = request.files['file']
      logging.info("File to upload"+str(file))
      # If the user does not select a file, the browser submits an
      # empty file without a filename.
      if file.filename == '':
        logging.info("File empty!")
        status = "ERROR"
        message = "File not selected!"
        #return redirect(request.url)
      elif file and allowed_file(file.filename):
        logging.info("Uploading!")
        status = "OK"
        message = "Upload successful!"
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        #return redirect(request.url)
      else:
        logging.info("file extensions not allowed!")
        status = "ERROR"
        message = "Only mp4 formal supported, you tried: " +str(file.filename)
      
  
  return render_template('video_upload.html', status=status, message=message, 
  video_files = video_files)

def allowed_file(filename):
  return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/delete_video', methods=['POST','GET'])
def video_delete():
  video_file = request.args.get('video_file')
  logging.info(f"Video file to remove: {video_file}")

  os.remove(os.path.join(app.config['UPLOAD_FOLDER'], video_file))

  json_resp = json.dumps({'status': 'OK', 'message':'Removed file'+str()})
  return make_response(json_resp, 200, {"content_type":"application/json"})


## TEST ENTRIES ##

# Test simple response
@app.route('/test_text', methods = ['GET','POST'])
def test_text():
  return "Hello <b>LM bias inspection - mod locally!</b>"

# Test HTML template
@app.route('/test_template', methods = ['GET','POST'])
def test_template():
  kwds = 'word 1'
  resp = make_response(render_template('main.html', keywords=kwds))
  return resp

# Test gen response
@app.route('/test_json', methods = ['GET','POST'])
def test_json():
  json_resp = json.dumps({'status': 'OK', 'message':'Testing json response - mod locally'})
  return make_response(json_resp, 200, {"content_type":"application/json"})

# Cast string to int
def safe_cast(val, to_type, default=None):
  try:
    return to_type(val)
  except (ValueError, TypeError):
    return default