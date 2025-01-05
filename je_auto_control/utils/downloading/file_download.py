import urllib.request
import shutil

from je_auto_control.utils.logging.loggin_instance import autocontrol_logger


def download_file(url: str, file_name: str):
    autocontrol_logger.info("file_download.py download_file"
                            f" url: {url} "
                            f" file_name: {file_name}")
    with urllib.request.urlopen(url) as response, open(file_name, 'wb') as out_file:
        shutil.copyfileobj(response, out_file)