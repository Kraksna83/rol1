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
import hmac
import hashlib


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


def generate_document_markdowns(directory):
    """
    Scans the given directory for all files, extracting metadata when available,
    and generates Markdown tables for general documents and meeting records.
    Files with pattern 'nameDD_MM_YY.ext' will have dates parsed,
    while other files will have date omitted.
    Returns the general and meeting-record markdown as a tuple.
    """
    date_pattern = re.compile(r"(.+?)(\d{2}_\d{2}_\d{2})\.(docx?|pdf)$", re.IGNORECASE)
    ext_pattern = re.compile(r"(.+?)\.(docx?|pdf)$", re.IGNORECASE)
    document_rows = []
    meeting_rows = []
    linkbase = "/public/docs/"
    
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
            rel_path = linkbase + fname
            #print (f"Processing file: {fname}, relative path: {rel_path}")
            link = f"[{fname}]({rel_path})"
            row = (date_fmt, name_part, ext, link)
            if name_part.casefold().startswith(("zapis", "usneseni")):
                meeting_rows.append(row)
            else:
                document_rows.append(row)

    def format_rows(rows):
        rows.sort(key=lambda x: ("0" if not x[0] else "1") + x[0], reverse=True)

        markdown = "| Den | Co | Format | Odkaz |\n"
        markdown += "|------|------|------|----------|\n"
        for date_fmt, name_part, ext, link in rows:
            markdown += f"| {date_fmt} | {name_part} | {ext} | {link} |\n"
        return markdown
    
    return format_rows(document_rows), format_rows(meeting_rows)

def run(cmd, cwd=None):
    result = subprocess.run(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.returncode, result.stdout.decode(), result.stderr.decode()


def required_env(name):
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Required environment variable {name} is not set.")
    return value


def read_cgi_payload():
    content_length = os.environ.get("CONTENT_LENGTH")
    if content_length is None:
        raise ValueError("Missing request content length.")

    try:
        length = int(content_length)
    except ValueError as error:
        raise ValueError("Invalid request content length.") from error

    if length < 0:
        raise ValueError("Invalid request content length.")

    payload = sys.stdin.buffer.read(length)
    if len(payload) != length:
        raise ValueError("Incomplete request payload.")
    return payload


def verify_github_signature(secret, payload, signature):
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    expected_signature = f"sha256={digest}"
    return hmac.compare_digest(
        signature.encode("utf-8"),
        expected_signature.encode("ascii"),
    )


def build_site(repo_dir, jekyll_cmd):
    dokumenty_path = os.path.join(repo_dir, "dokumenty.md")
    meeting_records_path = os.path.join(repo_dir, "zapisy-a-usneseni.md")
    docs_dir = os.path.join("public/docs/")

    docs_markdown, meeting_records_markdown = generate_document_markdowns(docs_dir)

    with open(dokumenty_path, 'w') as f:
        f.write("---\n")
        f.write("layout: page\n")
        f.write("title: Dokumenty\n")
        f.write("---\n\n")
        f.write(docs_markdown)

    with open(meeting_records_path, 'w') as f:
        f.write("---\n")
        f.write("layout: page\n")
        f.write("title: Zápisy a usnesení\n")
        f.write("---\n\n")
        f.write(meeting_records_markdown)

    print("Generated dokumenty.md file")
    print("Generated zapisy-a-usneseni.md file")

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

    signature = os.environ.get("HTTP_X_HUB_SIGNATURE_256", "")
    try:
        payload = read_cgi_payload()
    except ValueError as error:
        print(f"Invalid request payload: {error}")
        sys.exit(1)

    if not verify_github_signature(secret, payload, signature):
        print("Unauthorized: invalid secret.")
        sys.exit(1)
    
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
        print("No repository changes; rebuilding and deploying the site.")

    #zkus build
    if not build_site(repo_dir, jekyll_cmd):
        sys.exit(1)

    # pokud to proslo, oddelej stare soubory
    code, out, err = run(f"rm -rf {web_dir}/*")
    if code != 0:
        print("Failed to clean web dir:\n", err)
        sys.exit(1)

    #a udelej to znova, kdyz sis to smazal
    if not build_site(repo_dir, jekyll_cmd):
        sys.exit(1)


    print (f"web_dir: {web_dir}, repo_dir: {os.path.join(repo_dir, '_site')}")
    if web_dir != os.path.join(repo_dir, "_site"):
        # Copy new site files
        code, out, err = run(f"cp -r {repo_dir}/_site/* {web_dir}/")
        if code != 0:
            print("Failed to copy site:\n", err)
            sys.exit(1)
    else:
        print("Web directory is the same as the site directory; no need to copy files.")

    print("Deployment successful.")

if __name__ == "__main__":
    main()
