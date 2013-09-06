"""
Django settings file to use during deploystatic
"""
from os.path import abspath, dirname, join

from core.settings.loc import *

STATIC_ROOT = join(dirname(abspath(__file__)), '_static')