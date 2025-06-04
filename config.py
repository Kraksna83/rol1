#!/usr/bin/env python3

# Configuration for webhook deployment script

# Directory where the git repository is located
REPO_DIR = "/home/tomas/rol1"

# Directory where the built site should be deployed
WEB_DIR = "/var/www/html"

# Jekyll build command
JEKYLL_CMD = "/usr/bin/jekyll build"

# Secret key for webhook authentication
# Change this to a secure random string
SECRET = "your-webhook-secret-key-here"

print('Configuration loaded successfully.')