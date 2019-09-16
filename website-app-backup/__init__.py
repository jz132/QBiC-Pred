# app/__init__.py

from flask import Flask,session
from celery import Celery
import redis

from datetime import timedelta

# Initialize the app
app = Flask(__name__, instance_relative_config=True)
app.secret_key = "super secret key"

# Need to set this to keep session
app.permanent_session_lifetime = timedelta(minutes=3600)

# Load the config file
app.config.from_object('config')

db = redis.Redis('localhost', decode_responses=True) # decode->make it in utf8,TODO

celery = Celery(app.name, backend=app.config['CELERY_RESULT_BACKEND'], broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

# Load the views
from app import views
