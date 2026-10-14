"""Run once on your own computer to get a never-expiring Facebook Page token
plus your Page ID and Instagram account ID.

Usage:
    pip install requests
    python meta_token.py
"""
import sys

import requests

API = "https://graph.facebook.com/v24.0"

app_id = input("Meta App ID: ").strip()
app_secret = input("Meta App Secret: ").strip()
short_token = input("User token from Graph API Explorer: ").strip()

r = requests.get(f"{API}/oauth/access_token", params={
    "grant_type": "fb_exchange_token",
    "client_id": app_id,
    "client_secret": app_secret,
    "fb_exchange_token": short_token,
}, timeout=30)
if not r.ok:
    sys.exit(f"Token exchange failed: {r.text}")
long_token = r.json()["access_token"]

pages = requests.get(f"{API}/me/accounts", params={"access_token": long_token, "fields": "id,name,access_token"}, timeout=30).json()
if not pages.get("data"):
    sys.exit(f"No Facebook Pages found for this login: {pages}")

for i, p in enumerate(pages["data"]):
    print(f"[{i}] {p['name']}")
choice = pages["data"][int(input("Which Page should the bot post to? ") or 0)]

ig = requests.get(f"{API}/{choice['id']}", params={"fields": "instagram_business_account{id,username}", "access_token": choice["access_token"]}, timeout=30).json()
ig_account = ig.get("instagram_business_account")

debug = requests.get(f"{API}/debug_token", params={"input_token": choice["access_token"], "access_token": f"{app_id}|{app_secret}"}, timeout=30).json()
expires = debug.get("data", {}).get("expires_at")

print("\nAdd these as GitHub repository secrets:\n")
print("FB_PAGE_ID      =", choice["id"])
print("META_PAGE_TOKEN =", choice["access_token"])
if ig_account:
    print("IG_USER_ID      =", ig_account["id"], f"   (@{ig_account.get('username')})")
else:
    print("\nNo Instagram professional account is linked to this Page.")
    print("Link one in Instagram app: Settings > Account type and tools > switch to Professional, then connect this Page.")
print("\nToken expiry:", "never" if not expires else expires)
