"""
For building JS libraries and static sites deployed to s3
"""
import codecs
import collections
from datetime import date
import json
import os
import re
import shutil
from fabric.api import local, settings
from fabric.context_managers import hide
from fabric.operations import prompt
from fabric.utils import puts
from .fos import join, makedirs, relpath
from .utils import abort

# Banner for the top of CSS and JS files
BANNER = """
/* %(name)s - v%(version)s - %(date)s
 * Copyright (c) %(year)s %(author)s
 */
""".strip()


def load_config(config_file):
    """Read config.json, add date, year, paths"""
    with open(config_file) as fp:
        s = fp.read()
        s = re.sub(r'^\s*//.*[\r\n]*', '', s, flags=re.MULTILINE)
        config = json.loads(s, object_pairs_hook=collections.OrderedDict)

    today = date.today()
    config['date'] = today
    config['year'] = today.year

    config['project_path'] = os.path.dirname(config_file)
    config['root_path'] = os.path.dirname(config['project_path'])
    config['source_path'] = os.path.join(config['project_path'], 'source')
    config['build_path'] = os.path.join(config['project_path'], 'build')
    return config


def find_file(file_name, cur_dir, source_dir):
    """Find a file.  Look first in cur_dir, then source_dir"""
    file_path = os.path.abspath(join(cur_dir, file_name))
    if os.path.exists(file_path):
        return file_path
    for dirpath, dirs, files in os.walk(source_dir):
        if file_name in files:
            return join(dirpath, file_name)
    raise Exception('Could not find "%s" in %s' % (file_name, source_dir))


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


def render_templates(src_path, dst_path, extra_context):
    """Render flask templates"""
    puts('render: %s >> %s' % (src_path, dst_path))
    from website import app
    from flask import g, request

    compiled_includes = []

    for f in match_files(src_path, '^[^_].*$'):
        with app.app.test_request_context():
            g.compile_includes = True
            g.compiled_includes = compiled_includes
            content = app.catch_all(f, extra_context)
            compiled_includes = g.compiled_includes

        page_file = join(dst_path, f)
        puts('  %s' % page_file)
        makedirs(page_file, isfile=True)
        with open(page_file, 'w') as fd:
            fd.write(content.encode('utf-8'))


def add_zip_files(zip_file, config, param):
    """
    Add files to zip_file
    """
    project_path = config['project_path']

    for r in param:
        src = join(project_path, r['src'])
        dst = r['dst']
        puts('add: %s >> %s' % (src, dst))
        if os.path.isdir(src):
            regex = r['regex'] if 'regex' in r else '.*'
            for f in match_files(src, regex):
                puts('add: %s >> %s' % (join(src, f), join(dst, f)))
                zip_file.write(join(src, f),  join(dst, f))
        else:
            puts('add: %s >> %s' % (src, dst))
            zip_file.write(src, dst)


#
# Main operations
#
def banner(config, param):
    """
    Place banner at top of js and css files in-place.
    """
    #_banner_text = BANNER % config
    project_path = config['project_path']

    def _do(file_path, banner_text):
        puts('banner:  %s' % file_path)
        with open_file(file_path, 'r+') as fd:
            s = fd.read()
            fd.seek(0)
            fd.write(banner_text.encode(fd.encoding))
            fd.write(s)

    for r in param:
        src = join(project_path, r['src'])

        if 'template' in r:
            template = '\n'.join(r['template'])
        else:
            template = BANNER
        banner_text = (template+'\n') % config

        if os.path.isdir(src):
            regex = r['regex'] if 'regex' in r else '.*'
            for f in match_files(src, regex):
                _do(join(src, f), banner_text)
        else:
            _do(src, banner_text)


def concat(config, param):
    """
    Concatenate files
    """
    project_path = config['project_path']
    for r in param:
        dst = join(project_path, r['dst'])
        src = map(lambda x: join(project_path, x), r['src'])
        makedirs(dst, isfile=True)
        local('cat %s > %s' % (' '.join(src), dst))


def copy(config, param):
    """
    Copy files
    """
    project_path = config['project_path']

    def _do(src_path, dst_path):
        puts('  %s' % src_path)
        makedirs(dst_path, isfile=True)
        shutil.copy2(src_path, dst_path)

    for r in param:
        src = join(project_path, r['src'])
        dst = join(project_path, r['dst'])
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
    project_path = config['project_path']

    def _do(src_path, dst_path, opt):
        makedirs(dst_path, isfile=True)
        with hide('warnings'), settings(warn_only=True):
            result = local('lessc -x %s %s %s' % (opt, src_path, dst_path))
        if result.failed:
            abort('Error running lessc on %s' % src_path)

    if not os.popen('which lessc').read().strip():
        abort('You must install the LESS compiler')

    for r in param:
        src = join(project_path, r['src'])
        dst = join(project_path, r['dst'])

        opt = r['opt'] if ('opt' in r) else ''

        if os.path.isdir(src):
            regex = r['regex'] if 'regex' in r else '.*'
            for f in match_files(src, regex):
                (base, ext) = os.path.splitext(join(dst, f))
                _do(join(src, f), base+".css", opt)
        else:
            _do(src, dst, opt)


def minify(config, param):
    """
    Minify javascript
    """
    project_path = config['project_path']

    def _do(src_path, dst_path, opt):
        local('uglifyjs %s --output %s %s' % (src_path, dst_path, opt))

    for r in param:
        src = join(project_path, r['src'])
        dst = join(project_path, r['dst'])
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
    project_path = config['project_path']
    source_path = config['source_path']

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
            file_path = find_file(m.group('file'), dirpath, source_path)
            if not file_path in imported:
                puts('  prepend: %s' % file_path)
                imported.append(file_path)
                _do(f_out, file_path, imported)

        # Write out file
        _mark(f_out, os.path.basename(path))
        f_out.write(s+'\n')

        # Write out appends
        for m in _re_append.finditer(s):
            file_path = find_file(m.group('file'), dirpath, source_path)
            if not file_path in imported:
                puts('  append: %s' % file_path)
                imported.append(file_path)
                _do(f_out, file_path, imported)

    for r in param:
        src = join(project_path, r['src'])
        dst = join(project_path, r['dst'])
        puts('process: %s >> %s' % (src, dst))

        makedirs(dst, isfile=True)
        with open_file(dst, 'w', 'utf-8') as out_file:
            _do(out_file, src, [])


def usemin(config, param, context=None):
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

    If context, treat as a string format for context.
    """
    project_path = config['project_path']

    _re_build = re.compile(r"""
        <!--\s*build:(?P<type>\css|js)\s+(?P<dest>\S+)\s*-->
        .*?
        <!--\s*endbuild\s*-->
        """,
        re.VERBOSE | re.DOTALL)

    def _sub(m):
        type = m.group('type')
        dest = m.group('dest').strip('\\') % (context or {})

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
        src = join(project_path, r)
        puts('usemin: %s' % src)

        if os.path.isdir(src):
            for f in match_files(src, '.*\.html'):
                _do(join(src, f))
        else:
            _do(src)

def npm_run(config, param):
    """Value of `param` should be an array of strings whose values are npm tasks valid for the current project."""
    for task in param:
        local('npm run {}'.format(task))
