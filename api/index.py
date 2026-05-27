import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from prototype.app import app

handler = app
