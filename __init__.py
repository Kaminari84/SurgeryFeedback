import os
from pathlib import Path
import glob
import re
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
  alt_text = safe_cast(request.args.get('alt_text'), int, default=None)
  logging.info("Alt text:"+str(alt_text))

  needle_handling_skill_man = safe_cast(request.args.get('needle_handling_skill'), int, default=None)
  logging.info("Needle handling skill:"+str(needle_handling_skill_man))

  needle_driving_skill_man = safe_cast(request.args.get('needle_driving_skill'), int, default=None)
  logging.info("Needle driving skill:"+str(needle_driving_skill_man))

  pid = safe_cast(request.args.get('p'), int, default=None)
  logging.info("PID:"+str(pid))

  page = safe_cast(request.args.get('page'), int, default=1)
  logging.info("Page:"+str(page))
  if page<1 or page>2:
    page=1
  
  # get videos for the participant
  pidVideos = glob.glob(os.path.join(app.root_path,'static/video/','p'+str(pid)+'_*.mp4'))
  pidVideos = [os.path.basename(path) for path in pidVideos]
  logging.info("PID videos:" + str(pidVideos))

  # default videos
  videos = {"handling": ['none', 'none'],
            "driving": ['none', 'none']}

  skills = {"handling": None, "driving": None}

  error_message = None

  # extract from video if not explicitly specified
  base_count = 0
  non_base_count = 0
  for pidVid in pidVideos:
    for domain in ['handling', 'driving']:
      if domain in pidVid and 'base' in pidVid:
        digits = re.findall(r'\d+', pidVid)
        skills[domain] = 2
        if len(digits) < 2:
          error_message = "Wrong format of "+str(domain)+" baseline file: "+str(pidVid)
          logging.info(error_message)
        else:
          vid_no = safe_cast(digits[1], int, default=None)
          if vid_no == None:
            error_message = "Second digit in "+str(pidVid)+" , not a number!"
            logging.info(error_message)
          else:
            videos[domain][vid_no-1] = pidVid
            logging.info("Baseline video "+str(digits[1])+", name:<"+str(pidVid)+">")
      elif domain in pidVid :
        digits = re.findall(r'\d+', pidVid)
        if len(digits) < 2:
          error_message = "Wrong format of "+str(domain)+" intervention file: "+str(pidVid)
          logging.info(error_message)
        else:
          skills[domain] = safe_cast(digits[1], int, default=None)
          logging.info("Extracted 'needle "+str(domain)+"' skill from video "+str(pidVid)+": "+str(skills[domain]))
          videos[domain][0] = pidVid
          videos[domain][1] = 'handling_ideal.mp4' if domain=="handling" else 'driving_ideal.mp4'
    
  # video assessment overriden by manual specification of skill
  if needle_driving_skill_man != None:
    skills['driving'] = needle_driving_skill_man
  if needle_handling_skill_man != None:
    skills['handling'] = needle_handling_skill_man
  
  domain_specs = [ 
    {
      "skill": skills['handling'], "skill_var_name": "needle_handling_skill",
      "video_1": videos['handling'][0],
      "video_2": videos['handling'][1],
      "ideal_level": {"domain_name": "Needle Handling (Repositions)",
                      "video_1_title": "YOUR Video",
                      "video_2_title": "Expert Reference Video",
                      "encouragement": "Good work!", 
                      "issue_list_intro": "You successfully:",
                      "issues": ["Held the needle at 3/4<sup>th</sup> length", 
                                 "Re-grabbed the needle fewer than 3 times per stitch"]},

      "fail_level": { "domain_name": "Needle Handling (Repositions)",
                      "video_1_title": "YOUR Video",
                      "video_2_title": "Expert Reference Video",
                      "encouragement": "You did not satisfy ideal criteria!", 
                      "issue_list_intro": "To improve:",
                      "issues": ["Minimize number of re-grabs of the needle (<2 times)"]
                      },
      "baseline":  {"domain_name": "Needle Handling",
                    "video_1_title": "YOUR Video (randomly selected)",
                    "video_2_title": "YOUR Video (randomly selected)",
                    "encouragement": "",
                    "issue_list_intro": "",
                    "issues": [""]
      }
    },
    {
      "skill": skills['driving'], "skill_var_name": "needle_driving_skill", 
      "video_1": videos['driving'][0],
      "video_2": videos['driving'][1],
      "ideal_level": {"domain_name": "Needle Driving (Smoothness)",
                      "video_1_title": "YOUR Video",
                      "video_2_title": "Expert Reference Video",
                      "encouragement": "Good work!", 
                      "issue_list_intro": "You successfully:",
                      "issues": ["Used smooth, continuous motion", 
                                 "Re-grabbed the needle fewer than 1 time per stitch "
                                 "Adjusted the needle fewer than 2 times while driving"]},

      "fail_level": { "domain_name": "Needle Driving (Smoothness)",
                      "video_1_title": "YOUR Video",
                      "video_2_title": "Expert Reference Video",
                      "encouragement": "You did not satisfy ideal criteria!", 
                      "issue_list_intro": "To improve:",
                      "issues": ["Use a smooth, continuous motion", 
                                 "Minimize re-grabbing the needle, no more than once per stitch",
                                 "Minimize re-adjusting the needle, no more than once while driving"]
                      },
      "baseline":  {"domain_name": "Needle Driving",
                    "video_1_title": "YOUR Video (randomly selected)",
                    "video_2_title": "YOUR Video (randomly selected)",
                    "encouragement": "",
                    "issue_list_intro": "",
                    "issues": [""]
      }
    }
  ]

  logging.info("Spec:" + json.dumps(domain_specs[page-1:page]))

  resp = make_response(render_template('video_playback.html', 
                            domain_specs = domain_specs[page-1:page],
                            page = page,
                            pid = pid,
                            alt_text = alt_text,
                            needle_driving_skill = needle_driving_skill_man,
                            needle_handling_skill = needle_handling_skill_man
                          )
                      )
  return resp

## UPLOADING VIDEO FILES ##
# https://dev.to/nagatodev/uploading-media-files-to-your-flask-application-5h9k
# Handling redirects - https://thewebdev.info/2022/05/22/how-to-pass-arguments-into-redirecturl_for-of-flask/
@app.route('/video_upload', methods=['POST','GET'])
def video_upload():
  logging.info("Trying to upload video file!")
  #video_files = os.listdir(os.path.join(app.root_path,'static/video/'))
  
  #paths = sorted(Path(os.path.join(app.root_path,'static/video/')).iterdir(), key=os.path.getmtime, reverse=True)
  #video_files = [path.name for path in paths]
  paths_unsorted = glob.glob(os.path.join(app.root_path, 'static/video/', '*.mp4'))
  #print("Paths unsorted:", str(paths_unsorted))
  # print("OS stat:", os.stat(paths_unsorted[0]))
  paths = sorted(paths_unsorted, key=lambda t: os.stat(t).st_mtime, reverse=True)
  video_files = [os.path.basename(path) for path in paths]
  logging.info("Paths:"+str(video_files))

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
  logging.info("Video file to remove:"+str(video_file))

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