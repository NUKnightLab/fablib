"""
Amazon Web Services
"""
import boto
from .utils import abort


AWS_CREDENTIALS_ERR_MSG = """
    Unable to connect to AWS. Check your credentials. boto attempts to
    find AWS credentials in environment variables AWS_ACCESS_KEY_ID
    and AWS_SECRET_ACCESS_KEY, or in config files: /etc/boto.cfg, or
    ~/.boto. Do not quote key strings in config files. For details, see:
    http://boto.readthedocs.org/en/latest/boto_config_tut.html#credentials
"""


_s3_con = None

    
def get_s3_con():
    """Get an S3 connection."""
    global _s3_con
    
    if _s3_con is None:
        try:
            _s3_con = boto.connect_s3()
        except boto.exception.NoAuthHandlerFound:
            abort(AWS_CREDENTIALS_ERR_MSG)
    return _s3_con
       
