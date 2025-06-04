#!/usr/bin/env python3

import os
import sys
import subprocess

# Configuration
import importlib.util

spec = importlib.util.spec_from_file_location("config", "/var/www/html/wh_receiver/test.py")
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)

REPO_DIR = config.REPO_DIR
WEB_DIR = config.WEB_DIR
JEKYLL_CMD = config.JEKYLL_CMD
SECRET = config.SECRET

def run(cmd, cwd=None):
    result = subprocess.run(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.returncode, result.stdout.decode(), result.stderr.decode()

def main():
    print("Content-Type: text/plain\n")
    # Check for POST and validate secret
    
    if os.environ.get("REQUEST_METHOD") != "POST":
        print("Invalid request method.")
        sys.exit(1)
    if os.environ.get("HTTP_X_SECRET") != SECRET:
        print("Unauthorized: invalid secret.")
        sys.exit(1)

    # Pull latest changes
    code, out, err = run("git pull", cwd=REPO_DIR)
    if code != 0:
        print("Git pull failed:\n", err)
        sys.exit(1)

    # Build Jekyll site
    code, out, err = run(JEKYLL_CMD, cwd=REPO_DIR)
    if code != 0:
        print("Jekyll build failed:\n", err)
        sys.exit(1)

    # Remove old site files
    code, out, err = run(f"rm -rf {WEB_DIR}/*")
    if code != 0:
        print("Failed to clean web dir:\n", err)
        sys.exit(1)

    # Copy new site files
    code, out, err = run(f"cp -r {REPO_DIR}/_site/* {WEB_DIR}/")
    if code != 0:
        print("Failed to copy site:\n", err)
        sys.exit(1)

    print("Deployment successful.")

if __name__ == "__main__":
    main()
