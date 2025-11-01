import os, codecs, pprint, argparse, shutil, xml.dom.minidom
from getpass import getpass
import urllib
import html
import re
import calendar
from datetime import *
import json
import time

MimeExtensions = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

def fail(message):
    """Fail with a message."""
    print(message)
    exit(1)

def load_config(config_file_path):
    """Load configuration from JSON file."""
    if os.path.exists(config_file_path):
        with open(config_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        fail("\n".join(
            [f"Could not open {config_file_path}",
            "need a json config file, like this:",
            "{",
            "  \"author\": \"Dante Alighieri\"",
            "  \"title\": \"Commedia Divina\"",
            "  \"input_files\": \"CommediaDivina/*.md\"",
            "  \"output_pdf\": \"CommediaDivina.pdf\"",
            "}"]))

