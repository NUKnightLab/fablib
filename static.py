"""
Static sites
"""
import codecs
import collections
from datetime import date
import json
import os
import re
import shutil
from fabric.api import env, local, settings
from fabric.context_managers import hide
from fabric.operations import prompt
from fabric.utils import puts
from .fos import join, makedirs, relpath

# Banner for the top of CSS and JS files
BANNER = """
/* %(name)s - v%(version)s - %(date)s
 * Copyright (c) %(year)s %(author)s 
 */
""".lstrip()


def load_config():
    """Read config.json and add 'date' and 'year'"""
    with open(join(env.project_path, 'config.json')) as fp:
        s = fp.read()
        s = re.sub(r'//.*', '', s)
        s = re.sub(r'/\*.*?\*/', '', s, flags=re.DOTALL)
        config = json.loads(s, object_pairs_hook=collections.OrderedDict)

    today = date.today()
    config['date'] = today
    config['year'] = today.year
    return config
            
def find_file(file_name, cur_dir):
    """Find a file.  Look first in cur_dir, then env.source_path"""
    file_path = os.path.abspath(join(cur_dir, file_name))
    if os.path.exists(file_path):
        return file_path
    for dirpath, dirs, files in os.walk(env.source_path):
        if file_name in files:
            return join(dirpath, file_name)
    raise Exception('Could not find "%s" in %s' % (file_name, env.source_path))

def match_files(src, regex):
    """Return relative filepaths matching regex in src"""
    re_match = re.compile(regex)
    
    for (dirpath, dirnames, filenames) in os.walk(src):  
        relative_dir = relpath(src, dirpath)
        
        for f in filter(lambda x: not x.startswith('.'), filenames):
            relative_path = join(relative_dir, f)
            if re_match.match(relative_path):   
                yield relative_path

def open_file(path, mode, encoding=''):
    """Open a file with character encoding detection"""   
    if mode.startswith('r'):
        bytes = min(32, os.path.getsize(path))
    
        with open(path, 'rb') as fd:
            raw = fd.read()       
            if raw.startswith(codecs.BOM_UTF8):
                encoding = 'utf-8-sig'
            else:
                encoding = 'utf-8'    
    return codecs.open(path, mode, encoding) 
       
def render_templates(src_path, dst_path):
    """Render flask templates"""
    puts('render: %s >> %s' % (src_path, dst_path))        
    from website import app
    from flask import g, request
  
    compiled_includes = []
    
    for f in match_files(src_path, '^[^_].*$'):  
        with app.app.test_request_context():
            g.compile_includes = True
            g.compiled_includes = compiled_includes
            content = app.catch_all(f)
            compiled_includes = g.compiled_includes

        page_file = join(dst_path, f)
        puts('  %s' % page_file)
        makedirs(page_file, isfile=True)
        with open(page_file, 'w') as fd:
            fd.write(content.encode('utf-8'))

#
# Main operations
#           
def banner(config, param):
    """
    Place banner at top of js and css files in-place.    
    """
    _banner_text = BANNER % config

    def _do(file_path):
        puts('  %s' % file_path)  
        with open_file(file_path, 'r+') as fd:
            s = fd.read()
            fd.seek(0)
            fd.write(_banner_text.encode(fd.encoding))
            fd.write(s)
    
    for r in param:
        src = join(env.project_path, r)
        puts('banner: %s' % src)
        if os.path.isdir(src):
            for f in match_files(src, '.*\.(css|js)$'):
                _do(join(src, f))
        else:
            _do(src)

def concat(config, param):
    """
    Concatenate files
    """        
    for r in param:
        dst = join(env.project_path, r['dst']) 
        src = map(lambda x: join(env.project_path, x), r['src'])      
        makedirs(dst, isfile=True)
        local('cat %s > %s' % (' '.join(src), dst))
 
def copy(config, param):
    """
    Copy files
    """  
    def _do(src_path, dst_path):
        puts('  %s' % src_path)     
        makedirs(dst_path, isfile=True)
        shutil.copy2(src_path, dst_path)
        
    for r in param:
        src = join(env.project_path, r['src'])
        dst = join(env.project_path, r['dst'])
        puts('copy: %s >> %s' % (src, dst))
        if os.path.isdir(src):
            regex = r['regex'] if 'regex' in r else '.*'           
            for f in match_files(src, regex):
                _do(join(src, f), join(dst, f))
        else:   
            _do(src, dst)             

def lessc(config, param):
    """
    Compile LESS
    """        
    def _do(src_path, dst_path):
        makedirs(dst_path, isfile=True)
        with hide('warnings'), settings(warn_only=True):
            result = local('lessc -x %s %s' % (src_path, dst_path))
        if result.failed:
            abort('Error running lessc on %s' % src_path)    

    if not os.popen('which lessc').read().strip():
        abort('You must install the LESS compiler')
        
    for r in param:
        src = join(env.project_path, r['src'])
        dst = join(env.project_path, r['dst'])
        
        if os.path.isdir(src):
            regex = r['regex'] if 'regex' in r else '.*'           
            for f in match_files(src, regex):
                (base, ext) = os.path.splitext(join(dst, f)) 
                _do(join(src, f), base+".css")
        else:
            _do(src, dst)             

def minify(config, param):
    """
    Minify javascript 
    """       
    def _do(src_path, dst_path, opt):
        local('uglifyjs %s --output %s %s' % (opt, dst_path, src_path))
                   
    for r in param:
        src = join(env.project_path, r['src'])
        dst = join(env.project_path, r['dst'])
        puts('minify: %s >> %s' % (src, dst))
 
        opt = r['opt'] if ('opt' in r) else ''
        out_ext = r['ext'] if ('ext' in r) else ''
       
        if os.path.isdir(src):
            makedirs(dst, isfile=False)
            for f in match_files(src, '.*\.js'):
                (base, in_ext) = os.path.splitext(join(dst, f))
                _do(join(src, f), base+out_ext+in_ext, opt)
        else:                
            makedirs(dst, isfile=True)
            _do(src, dst, opt)

def process(config, param):
    """
    Process codekit style imports
    """
    _re_prepend = re.compile(r'@codekit-prepend\s*[\'"](?P<file>.+)[\'"]\s*;')
    _re_append = re.compile(r'@codekit-append\s*[\'"](?P<file>.+)[\'"]\s*;')

    def _mark(f_out, path):
        f_out.write("""
/* **********************************************
     Begin %s
********************************************** */

""" % os.path.basename(path))
        
    def _do(f_out, path, imported):
        s = ''
        dirpath = os.path.dirname(path)      
        with open_file(path, 'r') as f_in:
            s = f_in.read()
     
        # Write out prepends
        for m in _re_prepend.finditer(s):
            file_path = find_file(m.group('file'), dirpath)
            if not file_path in imported:
                puts('  prepend: %s' % file_path)
                imported.append(file_path)
                _do(f_out, file_path, imported)
        
        # Write out file
        _mark(f_out, os.path.basename(path))  
        f_out.write(s+'\n')
        
        # Write out appends    
        for m in _re_append.finditer(s):
            file_path = find_file(m.group('file'), dirpath)
            if not file_path in imported:
                puts('  append: %s' % file_path)
                imported.append(file_path)
                _do(f_out, file_path, imported)
              
    for r in param:
        src = join(env.project_path, r['src'])
        dst = join(env.project_path, r['dst'])       
        puts('process: %s >> %s' % (src, dst))
     
        makedirs(dst, isfile=True)
        with open_file(dst, 'w', 'utf-8') as out_file:
            _do(out_file, src, [])

def usemin(config, param):
    """
    Replaces usemin-style build blocks with a reference to a single file.    

    Build blocks take the format:
    
        <!-- build:type path -->
        (references to unoptimized files go here)
        <!-- endbuild -->
    
    where:
        type = css | js
        path = reference to the optimized file
    
    Any leading backslashes will be stripped, but the path will otherwise
    by used as it appears within the opening build tag.
    """
    _re_build = re.compile(r"""
        <!--\s*build:(?P<type>\css|js)\s+(?P<dest>\S+)\s*-->
        .*?
        <!--\s*endbuild\s*-->
        """, 
        re.VERBOSE | re.DOTALL)

    def _sub(m):
        type = m.group('type')
        dest = m.group('dest').strip('\\')
    
        if type == 'css':
            return '<link rel="stylesheet" href="%s">' % dest
        elif type == 'js':
            return '<script type="text/javascript" src="%s"></script>' % dest
        else:
            warn('Unknown build block type (%s)' % type)
            return m.group(0)

    def _do(file_path):
        with open_file(file_path, 'r+') as fd:
            s = fd.read()        
            (new_s, n) = _re_build.subn(_sub, s)     
            if n:
                puts('  (%d) %s' % (n, file_path))        
                fd.seek(0)
                fd.write(new_s)
                fd.truncate()
                      
    for r in param:
        src = join(env.project_path, r)  
        puts('usemin: %s' % src)

        if os.path.isdir(src):            
            for f in match_files(src, '.*\.html'):
                _do(join(src, f))
        else:                
            _do(src)
     