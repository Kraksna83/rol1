#!/usr/bin/env python3

import argparse
import os
import sys
import subprocess
import re
from datetime import datetime
from pathlib import Path
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv


def get_pdf_creation_date(filepath):
    try:
        result = subprocess.run(
            ["pdfinfo", "-rawdates", filepath],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""

    match = re.search(r"^CreationDate:\s*D:(\d{4})(\d{2})(\d{2})", result.stdout, re.MULTILINE)
    if not match:
        return ""

    try:
        return datetime.strptime("".join(match.groups()), "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return ""


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
            
            if not ext_match or ext_match.group(2).lower() not in ['doc', 'docx', 'pdf']:
                continue  # Skip files that don't match our criteria

            ext = ext_match.group(2).lower()
            name_match = date_match.group(1) if date_match else ext_match.group(1)
            name_part = name_match.replace('_', ' ').strip()
            date_fmt = get_pdf_creation_date(os.path.join(root, fname)) if ext == "pdf" else ""

            if not date_fmt and date_match:
                date_str = date_match.group(2)
                try:
                    date_parse_str = date_str.replace('_', '-')
                    date_obj = datetime.strptime(date_parse_str, "%d-%m-%y")
                    date_fmt = date_obj.strftime("%Y-%m-%d")
                except ValueError:
                    date_fmt = date_str
                
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


def required_env(name):
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Required environment variable {name} is not set.")
    return value


def build_site(repo_dir, jekyll_cmd):
    dokumenty_path = os.path.join(repo_dir, "dokumenty.md")
    docs_dir = os.path.join(repo_dir, "public/docs/")

    docs_markdown = generate_dokumenty_md(docs_dir)

    with open(dokumenty_path, 'w') as f:
        f.write("---\n")
        f.write("layout: page\n")
        f.write("title: Dokumenty\n")
        f.write("---\n\n")
        f.write(docs_markdown)

    print("Generated dokumenty.md file")

    code, out, err = run(jekyll_cmd, cwd=repo_dir)
    if code != 0:
        print("Jekyll build failed:\n", err)
        return False

    return True


def main():
    parser = argparse.ArgumentParser(description="Build and deploy the Jekyll site.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="generate dokumenty.md and build locally without pulling or deploying",
    )
    args = parser.parse_args()

    if not args.dry_run:
        print("Content-Type: text/plain\n")

    load_dotenv(dotenv_path=Path(__file__).resolve().with_name(".env"))

    try:
        repo_dir = required_env("REPO_DIR")
        jekyll_cmd = required_env("JEKYLL_CMD")
        if args.dry_run:
            if not build_site(repo_dir, jekyll_cmd):
                sys.exit(1)
            print("Dry run successful; site built locally and not deployed.")
            return

        web_dir = required_env("WEB_DIR")
        secret = required_env("SECRET")
        email_from = required_env("EMAIL_FROM")
    except ValueError as error:
        print(f"Configuration error: {error}")
        sys.exit(1)

    # Check for POST and validate secret
    
    if os.environ.get("REQUEST_METHOD") != "POST":
        print("Invalid request method.")
        sys.exit(1)
    if os.environ.get("HTTP_X_SECRET") != secret:
        print("Unauthorized: invalid secret.")
        sys.exit(1)
        # Pull latest changes
    
    code, out, err = run("git pull", cwd=repo_dir)
    if code != 0:
        print("Git pull failed:\n", err)
        sys.exit(1)
    
    # Check if changes were pulled
    if "Already up to date" not in out:
        # Get the email of the last commit author
        code, author_email, err = run("git log -1 --pretty=format:%ae", cwd=repo_dir)
        if code == 0 and author_email:
            # Send notification email
            # Prepare email content
            subject = 'Site deployment notification'
            commit_msg = run("git log -1 --pretty=format:%s", cwd=repo_dir)[1]
            body = f'Your changes have been pulled and the site has been deployed.\n\nCommit message: {commit_msg}'
            
            # Use mail command to send email
            mail_cmd = f"echo '{body}' | mail -s '{subject}' -r {email_from} {author_email}"
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
    if not build_site(repo_dir, jekyll_cmd):
        sys.exit(1)

    # Remove old site files
    code, out, err = run(f"rm -rf {web_dir}/*")
    if code != 0:
        print("Failed to clean web dir:\n", err)
        sys.exit(1)

    # Copy new site files
    code, out, err = run(f"cp -r {repo_dir}/_site/* {web_dir}/")
    if code != 0:
        print("Failed to copy site:\n", err)
        sys.exit(1)

    print("Deployment successful.")

if __name__ == "__main__":
    main()
