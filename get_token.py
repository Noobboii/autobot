"""Run once on your own computer to get the YouTube refresh token.

Usage:
    pip install google-auth-oauthlib
    python get_token.py client_secret.json
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

secret_file = sys.argv[1] if len(sys.argv) > 1 else "client_secret.json"
flow = InstalledAppFlow.from_client_secrets_file(
    secret_file, scopes=["https://www.googleapis.com/auth/youtube.upload"]
)
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
info = json.load(open(secret_file))
client = info.get("installed") or info.get("web")

print("\nAdd these three as GitHub repository secrets:\n")
print("YT_CLIENT_ID     =", client["client_id"])
print("YT_CLIENT_SECRET =", client["client_secret"])
print("YT_REFRESH_TOKEN =", creds.refresh_token)
