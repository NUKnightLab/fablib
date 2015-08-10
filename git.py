"""
git-related utilities
"""
import os
import re
from fabric.api import env, local
from fabric.context_managers import lcd
from fabric.operations import prompt
from fabric.utils import puts
from .utils import abort, warn


_re_ready_status = r'(.*)\n(nothing to commit|Your branch is up-to-date)'

_not_ready_msg = '' \
    'You have uncommitted local code changes. ' \
    'Please commit and push changes before deploying.'

 
def check_clean(force=False):   
    git_status = os.popen('git status').read()
    if not force and not re.match(_re_ready_status, git_status):  
        abort(_not_ready_msg)      

    
def tags():
    """Get list of current tags"""
    with lcd(env.project_path):
        tags = local('cd %(project_path)s;git tag' % env, capture=True)

    if tags:
        stripped = [x.strip() for x in tags.strip().split('\n')]
        re_num = re.compile('[^0-9.]')
        sorted_tags = reversed(sorted([map(int, re_num.sub('', t).split('.')) for t in stripped]))
        rebuilt = ['.'.join(map(str,t)) for t in sorted_tags]
        return rebuilt
    return []


def last_tag():
    """Get the last version tag"""
    tag_list = tags()
    if tag_list:
        return '.'.join(map(str, tag_list[-1]))
    return None  


def prompt_tag(msg, unique=False):
    """Prompt user for a version tag.  Pass unique=True to require a new one."""
    tag_list = tags()
    puts('This project has the following tags:')
    puts(tag_list)
        
    while True:
        version = prompt("%s: " % msg).strip()      
        if unique:
            if not re.match(r'^[0-9]+\.[0-9]+\.[0-9]+$', version):
                warn('Invalid version number, must be in the format:' \
                    ' major.minor.revision')
            elif version in tag_list:
                warn('Invalid version number, tag already exists')
            else:
                break   
        elif not version in tag_list:
            warn('You must enter an existing version')
        else:
            break
         
    return version   


def push_tag(version):
    """Create and push a tag"""
    with lcd(env.project_path):
        local('git tag %s' % version)
        local('git push origin %s' % version)    


def delete_tag(version):
    """Delete and push a tag"""
    with lcd(env.project_path):
        local('git tag -d %s' % version)
        local('git push origin :refs/tags/%s' % version)    
   
        
               
    