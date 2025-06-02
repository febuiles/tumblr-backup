#!/usr/bin/env python3

import os
import base64
import hashlib
import hmac
import time
import urllib.parse
import secrets
import requests
from dotenv import load_dotenv

load_dotenv()

def generate_signature(method, url, params, consumer_secret, token_secret=""):
    sorted_params = sorted(params.items())
    param_string = urllib.parse.urlencode(sorted_params)
    base_string = f"{method}&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(param_string, safe='')}"
    signing_key = f"{urllib.parse.quote(consumer_secret, safe='')}&{urllib.parse.quote(token_secret, safe='')}"

    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()

    return signature

def step1_get_request_token():
    consumer_key = os.getenv('TUMBLR_CONSUMER_KEY')
    consumer_secret = os.getenv('TUMBLR_CONSUMER_SECRET')

    if not consumer_key or not consumer_secret:
        print("Error: TUMBLR_CONSUMER_KEY and TUMBLR_CONSUMER_SECRET must be set in .env file")
        return None, None

    url = "https://www.tumblr.com/oauth/request_token"
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)

    oauth_params = {
        'oauth_callback': 'http://localhost:4567/callback',
        'oauth_consumer_key': consumer_key,
        'oauth_nonce': nonce,
        'oauth_signature_method': 'HMAC-SHA1',
        'oauth_timestamp': timestamp,
        'oauth_version': '1.0'
    }

    signature = generate_signature('POST', url, oauth_params, consumer_secret)
    oauth_params['oauth_signature'] = signature
    auth_header = 'OAuth ' + ', '.join([f'{k}="{urllib.parse.quote(str(v), safe="")}"' for k, v in oauth_params.items()])

    print("Step 1: Get Request Token")
    print("Run this curl command:")
    print()
    print(f'curl -X POST "{url}" \\')
    print(f'  -H "Authorization: {auth_header}"')
    print()
    print("This should return: oauth_token=XXX&oauth_token_secret=YYY&oauth_callback_confirmed=true")
    print()
    try:
        response = requests.post(url, headers={'Authorization': auth_header})
        if response.status_code == 200:
            tokens = dict(urllib.parse.parse_qsl(response.text))
            print("✅ Request successful! Response:")
            print(response.text)
            return tokens.get('oauth_token'), tokens.get('oauth_token_secret')
        else:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return None, None
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return None, None

def step2_authorize(oauth_token):
    if not oauth_token:
        print("❌ No oauth_token from step 1")
        return

    auth_url = f"https://www.tumblr.com/oauth/authorize?oauth_token={oauth_token}"
    print("\nStep 2: User Authorization")
    print("Visit this URL in your browser:")
    print(auth_url)
    print()
    print("After authorizing, you'll be redirected to a localhost URL.")
    print("Copy the 'oauth_verifier' parameter from that URL.")
    print()

def step3_get_access_token(oauth_token, oauth_token_secret, oauth_verifier):
    consumer_key = os.getenv('TUMBLR_CONSUMER_KEY')
    consumer_secret = os.getenv('TUMBLR_CONSUMER_SECRET')

    url = "https://www.tumblr.com/oauth/access_token"
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)

    oauth_params = {
        'oauth_consumer_key': consumer_key,
        'oauth_nonce': nonce,
        'oauth_signature_method': 'HMAC-SHA1',
        'oauth_timestamp': timestamp,
        'oauth_token': oauth_token,
        'oauth_verifier': oauth_verifier,
        'oauth_version': '1.0'
    }

    signature = generate_signature('POST', url, oauth_params, consumer_secret, oauth_token_secret)
    oauth_params['oauth_signature'] = signature
    auth_header = 'OAuth ' + ', '.join([f'{k}="{urllib.parse.quote(str(v), safe="")}"' for k, v in oauth_params.items()])

    print("\nStep 3: Get Access Token")
    print("Run this curl command:")
    print()
    print(f'curl -X POST "{url}" \\')
    print(f'  -H "Authorization: {auth_header}"')
    print()
    try:
        response = requests.post(url, headers={'Authorization': auth_header})
        if response.status_code == 200:
            tokens = dict(urllib.parse.parse_qsl(response.text))
            print("✅ Success! Your OAuth tokens:")
            print(f"Access Token: {tokens.get('oauth_token')}")
            print(f"Access Token Secret: {tokens.get('oauth_token_secret')}")
            print()
            print("Add these to your .env file or enter them when running the backup script.")
            return tokens.get('oauth_token'), tokens.get('oauth_token_secret')
        else:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return None, None
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return None, None

def main():
    print("Tumblr OAuth Token Generator")
    print("=" * 40)
    oauth_token, oauth_token_secret = step1_get_request_token()

    if not oauth_token:
        print("❌ Failed to get request token. Check your consumer key/secret.")
        return
    step2_authorize(oauth_token)
    oauth_verifier = input("Enter the oauth_verifier from the callback URL: ").strip()

    if not oauth_verifier:
        print("❌ No verifier provided")
        return
    access_token, access_token_secret = step3_get_access_token(oauth_token, oauth_token_secret, oauth_verifier)

    if access_token and access_token_secret:
        print("\n🎉 OAuth process complete!")
        print("You can now run the backup script.")

if __name__ == '__main__':
    main()
