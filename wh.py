#!/usr/bin/env python3

import os
import sys
import subprocess
import re
from datetime import datetime
import smtplib
from email.message import EmailMessage

# Configuration
import importlib.util

spec = importlib.util.spec_from_file_location("config", "/var/www/html/wh_receiver/config.py")
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)

REPO_DIR = config.REPO_DIR
WEB_DIR = config.WEB_DIR
JEKYLL_CMD = config.JEKYLL_CMD
SECRET = config.SECRET


def generate_dokumenty_md(directory):
    """
    Scans the given directory for all files, extracting metadata when available,
    and generates a Markdown table listing the documents.
    Files with pattern 'nameDD_MM_YY.ext' will have dates parsed,
    while other files will have date omitted.
    Returns the generated markdown as a string.
    """
    date_pattern = re.compile(r"(.+?)(\d{2}_\d{2}_\d{2})\.(docx?|pdf)$", re.IGNORECASE)
    ext_pattern = re.compile(r"(.+?)\.(docx?|pdf)$", re.IGNORECASE)
    rows = []
    
    # Walk through the directory and its subdirectories
    for root, _, files in os.walk(directory):
        for fname in files:
            date_match = date_pattern.match(fname)
            ext_match = ext_pattern.match(fname)
            
            if date_match:
                # Extract name, date, and extension
                name_part = date_match.group(1).replace('_', ' ').strip()
                date_str = date_match.group(2)
                ext = date_match.group(3).lower()
                
                # Try to parse the date string
                try:
                    # Convert from DD_MM_YY to DD-MM-YY for datetime parsing
                    date_parse_str = date_str.replace('_', '-')
                    date_obj = datetime.strptime(date_parse_str, "%d-%m-%y")
                    date_fmt = date_obj.strftime("%Y-%m-%d")
                except ValueError:
                    date_fmt = date_str  # Fallback if date parsing fails
                
            elif ext_match and ext_match.group(2).lower() in ['doc', 'docx', 'pdf']:
                # Handle files without dates
                name_part = ext_match.group(1).replace('_', ' ').strip()
                ext = ext_match.group(2).lower()
                date_fmt = ""  # Date omitted
            else:
                continue  # Skip files that don't match our criteria
                
            # Get relative path for the link
            rel_path = os.path.relpath(os.path.join(root, fname), directory)
            print (f"Processing file: {fname}, relative path: {rel_path}")
            link = f"[{fname}]({rel_path})"
            rows.append((date_fmt, name_part, ext, link))

    # Sort rows by date descending (newest first), with empty dates at the beginning
    rows.sort(key=lambda x: ("0" if not x[0] else "1") + x[0], reverse=True)

    # Generate the Markdown table as a string
    markdown = "| Den | Co | Format | Odkaz |\n"
    markdown += "|------|------|------|----------|\n"
    for date_fmt, name_part, ext, link in rows:
        markdown += f"| {date_fmt} | {name_part} | {ext} | {link} |\n"
    
    return markdown

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
    
    # Check if changes were pulled
    if "Already up to date" not in out:
        # Get the email of the last commit author
        code, author_email, err = run("git log -1 --pretty=format:%ae", cwd=REPO_DIR)
        if code == 0 and author_email:
            # Send notification email
            # Prepare email content
            subject = 'Site deployment notification'
            commit_msg = run("git log -1 --pretty=format:%s", cwd=REPO_DIR)[1]
            body = f'Your changes have been pulled and the site has been deployed.\n\nCommit message: {commit_msg}'
            
            # Use mail command to send email
            mail_cmd = f"echo '{body}' | mail -s '{subject}' -r {config.EMAIL_FROM} {author_email}"
            try:
                code, out, err = run(mail_cmd)
                if code == 0:
                    print(f"Notification email sent to {author_email}")
                else:
                    print(f"Failed to send email notification: {err}")
            except Exception as e:
                print(f"Failed to send email notification: {str(e)}")
    else:
        print("No changes to deploy.")
        sys.exit(0)
    # Generate and save dokumenty.md file
    dokumenty_path = os.path.join(REPO_DIR, "dokumenty.md")
    docs_dir = os.path.join(REPO_DIR, "public/docs/")

    # Generate markdown table content
    docs_markdown = generate_dokumenty_md(docs_dir)

    # Create the full markdown content with header from config
    with open(dokumenty_path, 'w') as f:
        f.write(f"---\n")
        f.write(f"layout: page\n")
        f.write(f"title: Dokumenty\n")
        f.write(f"---\n\n")
        f.write(docs_markdown)

    print(f"Generated dokumenty.md file")

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
