#!/usr/bin/env python3
"""
NostrX - Nostr to Twitter/X Sync Tool
Syncs posts from Nostr to Twitter, handling media and remembering state.
"""

import asyncio
import json
import os
import re
import time
import requests
import tempfile
from datetime import datetime, timedelta
from dotenv import load_dotenv

import tweepy
from nostr_sdk import (
    Client, Filter, Kind, Timestamp, PublicKey, 
    RelayUrl
)

# Load environment variables from .env file
load_dotenv()

# ==========================================
# CONFIGURATION
# ==========================================

# Nostr Settings
# Get npubs from environment variable (comma-separated)
npubs_env = os.getenv("NOSTR_NPUBS", "")
MONITORED_NPUBS = [n.strip() for n in npubs_env.split(",") if n.strip()]

# Get relays from environment variable (comma-separated), or use defaults
relays_env = os.getenv("NOSTR_RELAYS", "")
if relays_env:
    NOSTR_RELAYS = [r.strip() for r in relays_env.split(",") if r.strip()]
else:
    NOSTR_RELAYS = [
        "wss://relay.damus.io",
        "wss://nos.lol",
        "wss://relay.nostr.band",
        "wss://relay.primal.net"
    ]

# Twitter Settings
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET")

# State File
STATE_FILE = "sync_state.json"

# Media Extensions to detect in Nostr posts
MEDIA_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.mp4', '.mov']

# ==========================================
# STATE MANAGEMENT
# ==========================================

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    # Default state: Sync from 24 hours ago if running for the first time
    return {
        "last_synced_timestamp": int(time.time()) - 86400,
        "synced_event_ids": [] # Keep track of IDs to avoid duplicates
    }

def save_state(state):
    # Keep history manageable (last 1000 IDs)
    state["synced_event_ids"] = state["synced_event_ids"][-1000:]
    
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

# ==========================================
# MEDIA HANDLING
# ==========================================

def extract_media_urls(content):
    """Find media URLs in text content"""
    urls = []
    clean_content = content
    
    # Regex for URLs
    url_pattern = r'https?://\S+'
    found_urls = re.findall(url_pattern, content)
    
    for url in found_urls:
        lower_url = url.lower()
        # Check if it looks like an image/video file
        if any(lower_url.endswith(ext) for ext in MEDIA_EXTENSIONS):
            urls.append(url)
            # Remove the URL from the text so it doesn't appear as a link in the tweet
            # (Twitter displays uploaded media natively)
            clean_content = clean_content.replace(url, "").strip()
            
    return clean_content, urls

def download_media(url):
    """Download media to a temp file"""
    try:
        # Fake user agent to avoid blocking
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, stream=True, headers=headers, timeout=10)
        
        if response.status_code == 200:
            # Get extension
            ext = os.path.splitext(url)[1]
            if not ext:
                ext = ".jpg" # Default
                
            # Create temp file
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            for chunk in response.iter_content(chunk_size=8192):
                tf.write(chunk)
            tf.close()
            return tf.name
    except Exception as e:
        print(f"     ❌ Failed to download media {url}: {e}")
    return None

# ==========================================
# SYNC LOGIC
# ==========================================

class SyncTool:
    def __init__(self):
        self.state = load_state()
        self.client = None
        self.twitter_client = None
        self.twitter_v2 = None
        
    def setup_twitter(self):
        if all([TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET]):
            # V1.1 API for media upload
            auth = tweepy.OAuth1UserHandler(
                TWITTER_API_KEY, TWITTER_API_SECRET,
                TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
            )
            self.twitter_client = tweepy.API(auth)
            
            # V2 API for posting tweets
            self.twitter_v2 = tweepy.Client(
                consumer_key=TWITTER_API_KEY,
                consumer_secret=TWITTER_API_SECRET,
                access_token=TWITTER_ACCESS_TOKEN,
                access_token_secret=TWITTER_ACCESS_SECRET
            )
            print("✓ Twitter API connected")
        else:
            print("⚠️  Twitter credentials missing. Running in DRY RUN mode.")

    async def setup_nostr(self):
        self.client = Client()
        for relay in NOSTR_RELAYS:
            await self.client.add_relay(RelayUrl.parse(relay))
        
        await self.client.connect()
        print(f"✓ Connected to {len(NOSTR_RELAYS)} Nostr relays")

    async def run(self):
        print(r"""
                  _      __  __
  _ __   ___  ___| |_ _ _\ \/ /
 | '_ \ / _ \/ __| __| '__\  / 
 | | | | (_) \__ \ |_| |  /  \ 
 |_| |_|\___/|___/\__|_| /_/\_\                       
        """)
        
        self.setup_twitter()
        
        if not MONITORED_NPUBS:
            print("❌ No npubs configured in MONITORED_NPUBS")
            return

        await self.setup_nostr()

        # 1. Prepare Filter
        # Fetch events since the last successful sync
        last_ts = self.state["last_synced_timestamp"]
        since = Timestamp.from_secs(last_ts + 1)
        
        authors = [PublicKey.parse(npub) for npub in MONITORED_NPUBS]
        f = Filter().authors(authors).kind(Kind(1)).since(since)
        
        print(f"\n📥 Fetching posts since {datetime.fromtimestamp(last_ts)}...")
        
        # Fetch events
        timeout = timedelta(seconds=10)
        events = await self.client.fetch_events(f, timeout)
        event_list = events.to_vec()
        
        # Sort oldest to newest so we post in order
        event_list.sort(key=lambda x: x.created_at().as_secs())
        
        if not event_list:
            print("✅ No new posts found.")
            return

        print(f"found {len(event_list)} new posts.")
        
        new_last_ts = last_ts
        
        for event in event_list:
            event_id = event.id().to_hex()
            
            # Skip duplicates
            if event_id in self.state["synced_event_ids"]:
                continue
                
            # Skip replies
            is_reply = False
            for tag in event.tags().to_vec():
                t = tag.as_vec()
                if len(t) > 0 and t[0] in ['e', 'reply']:
                    is_reply = True
                    break
            
            if is_reply:
                print(f"⏭️  Skipping reply {event_id[:8]}")
                continue

            # Process Content
            content = event.content()
            clean_text, media_urls = extract_media_urls(content)
            ts = datetime.fromtimestamp(event.created_at().as_secs())
            
            print(f"\n📝 Processing post from {ts}:")
            print(f"   \"{clean_text[:50]}...\"")
            
            # Download Media
            media_ids = []
            temp_files = []
            
            if media_urls:
                print(f"   📷 Found {len(media_urls)} media items")
                for url in media_urls:
                    path = download_media(url)
                    if path:
                        temp_files.append(path)
                        if self.twitter_client:
                            try:
                                print(f"     Uploading {os.path.basename(path)}...")
                                media = self.twitter_client.media_upload(filename=path)
                                media_ids.append(media.media_id)
                            except Exception as e:
                                print(f"     ❌ Upload failed: {e}")
            
            # Post to Twitter
            if self.twitter_v2:
                try:
                    # Truncate text if too long
                    if len(clean_text) > 280:
                        clean_text = clean_text[:277] + "..."
                    
                    if media_ids:
                        self.twitter_v2.create_tweet(text=clean_text, media_ids=media_ids)
                    else:
                        self.twitter_v2.create_tweet(text=clean_text)
                        
                    print("   ✅ Posted to Twitter")
                    
                    # Update state immediately after success
                    self.state["synced_event_ids"].append(event_id)
                    if event.created_at().as_secs() > new_last_ts:
                        new_last_ts = event.created_at().as_secs()
                        self.state["last_synced_timestamp"] = new_last_ts
                    
                    save_state(self.state)
                    
                except Exception as e:
                    print(f"   ❌ Failed to tweet: {e}")
            else:
                print("   [DRY RUN] Would post to Twitter")
                # In dry run, we still update state to avoid "processing" them again in this loop
                # but usually you wouldn't save state in dry run. 
                # For this tool, let's NOT save state in dry run so you can test freely.
            
            # Cleanup
            for path in temp_files:
                try:
                    os.remove(path)
                except:
                    pass
            
            # Small delay to be nice to APIs
            time.sleep(1)

        print("\n Sync Complete!")

if __name__ == "__main__":
    tool = SyncTool()
    asyncio.run(tool.run())
