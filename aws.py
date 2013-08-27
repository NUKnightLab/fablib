"""
Amazon Web Services
"""
import os
import re
import sys
import tempfile
import boto
from fabric.api import env, put
from .decorators import require_settings


AWS_CREDENTIALS_ERR_MSG = """
    Unable to connect to AWS. Check your credentials. boto attempts to
    find AWS credentials in environment variables AWS_ACCESS_KEY_ID
    and AWS_SECRET_ACCESS_KEY, or in config files: /etc/boto.cfg, or
    ~/.boto. Do not quote key strings in config files. For details, see:
    http://boto.readthedocs.org/en/latest/boto_config_tut.html#credentials
"""

_ec2_con = None
_s3_con = None


def get_ec2_con():
    """Get an EC2 connection."""
    global _ec2_con
    if _ec2_con is None:
        try:
            _ec2_con = boto.connect_ec2()
        except boto.exception.NoAuthHandlerFound:
            print AWS_CREDENTIALS_ERR_MSG
            sys.exit(0)
    return _ec2_con
    
def get_s3_con():
    """Get an S3 connection."""
    global _s3_con
    if _s3_con is None:
        try:
            _s3_con = boto.connect_s3()
        except boto.exception.NoAuthHandlerFound:
            print AWS_CREDENTIALS_ERR_MSG
            sys.exit(0)
    return _s3_con

def get_ec2_reservations():
    try:
        return get_ec2_con().get_all_instances()
    except boto.exception.EC2ResponseError, e:
        abort('Received error from AWS. Are your credentials correct?' \
            'Note: do not quote keys in boto config files.' \
            '\nError from Amazon was:\n'+str(e))

def lookup_ec2_instances():
    """Load the EC2 instances by role definition into env.roledefs"""
    regex = re.compile(r'^%s-(?P<role>[a-zA-Z]+)[0-9]+$' % env.settings)
    for r in get_ec2_reservations():
        for i in r.instances:
            m = regex.match(i.tags.get('Name', ''))
            if m:
                env.roledefs[m.group('role')].append(
                    '%s@%s' % (env.app_user, i.public_dns_name))
                    
def copy_from_s3(bucket_name, resource, dest_path):
    """Copy a resource from S3 to a remote file."""
    bucket = get_s3_con().get_bucket(bucket_name)
    key = bucket.lookup(resource)
    f = tempfile.NamedTemporaryFile(delete=False)
    key.get_file(f)
    f.close()
    put(f.name, dest_path)
    os.unlink(f.name)
