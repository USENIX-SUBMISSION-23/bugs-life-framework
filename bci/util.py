"""
Functions from the os and shutil libraries show erroneous behavior when attempting to move a file from one file system
to another. These methods should be safe.
"""
import shutil
import os
import time
import json


def safe_move_file(src_path, dst_path):
    if not os.path.isfile(src_path):
        raise AttributeError("src path is not a file: '%s'" % src_path)
    if not os.path.exists(os.path.dirname(dst_path)):
        os.makedirs(dst_path)
    shutil.copyfile(src_path, dst_path)
    os.remove(src_path)


def safe_move_dir(src_path, dst_path):
    if not os.path.isdir(src_path):
        raise AttributeError("src path is not a directory: '%s'" % src_path)
    if not os.path.exists(dst_path):
        os.makedirs(dst_path)
    for file_or_dir in os.listdir(src_path):
        new_src_path = os.path.join(src_path, file_or_dir)
        new_dst_path = os.path.join(dst_path, file_or_dir)
        if os.path.isfile(new_src_path):
            safe_move_file(new_src_path, new_dst_path)
        elif os.path.isdir(new_src_path):
            safe_move_dir(new_src_path, new_dst_path)
        else:
            raise AttributeError("Something went wrong")


def rmtree(src_path):
    """
    Removes folder at given src_path.

    :param src_path: path to the folder that is to be removed
    :return: True if the folder was successfully removed, otherwise False.
    """
    max_tries = 10
    for _ in range(0, max_tries):
        try:
            shutil.rmtree(src_path)
            return True
        except OSError as _: # noqa
            time.sleep(2)
            continue
    return False


def read_web_report(file_name):
    report_folder = "/reports"
    path = os.path.join(report_folder, file_name)
    if not os.path.isfile(path):
        raise AttributeError("Could not find report at '%s'" % path)
    with open(path, "r") as file:
        return json.load(file)
