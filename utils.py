"""
Utility functions
"""
from fabric.api import env, run
from fabric.colors import red, blue
from fabric.context_managers import prefix
from fabric.contrib.files import exists
from fabric.decorators import task
from fabric.operations import prompt
import fabric.utils
import sys
import os

def run_in_ve(command):
    """Execute the command inside the virtualenv."""
    with prefix('. %s' % env.activate_path):
        env.doit(command)
                
def notice(msg):
    """Show blue notice message."""
    print '\nNotice: '+blue(msg % env)+'\n'

def warn(msg):
    """Show red warning message."""
    fabric.utils.warn(red(msg % env))

def abort(msg):
    """Show red error message and abort."""      
    fabric.utils.abort(red(msg % env))

def do(yes_no):
    """Boolean for yes/no values."""
    return yes_no.strip().lower().startswith('y')

def confirm(msg):
    """Get confirmation from the user."""
    return do(raw_input(msg))
    
def add_path(dir_path):
    """Make sure a directory is in sys.path."""
    notice('Checking sys.path for %s' % dir_path)
    if dir_path not in sys.path:
        notice('Appending %s to sys.path' % dir_path)
        sys.path.append(dir_path)
  
def symlink(existing, link):
    """Removes link if it exists and creates the specified link."""
    if exists(link):
        run('rm %s' % link)
    run('ln -s %s %s' % (existing, link))  
