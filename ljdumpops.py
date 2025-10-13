import os, codecs, pprint, argparse, shutil, xml.dom.minidom
from getpass import getpass
import urllib
import html
import re
import calendar
from datetime import *
from xml.etree import ElementTree as ET
from ljdumpsqlite import *
import time
from ljdumpops import *

MimeExtensions = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

def fail(message):
    """Fail with a message."""
    print(message)
    os.__exit(os.EX_IOERR)
