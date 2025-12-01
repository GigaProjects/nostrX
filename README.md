# NostrX

A local, self-hosted tool to automatically sync your Nostr posts to Twitter/X.

## Features

- 🔒 **Runs locally** - No need to trust third-party services
- 🔄 **One-Way Sync** - Reads from Nostr, posts to Twitter
- 💾 **Stateful** - Remembers where it left off (runs efficiently via cron)
- 🖼️ **Media Support** - Downloads images/videos from Nostr and uploads them to Twitter natively
- 🚫 **Filters replies** - Only posts top-level notes

## Setup

### 1. Install Dependencies
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 2. Configure Twitter/X Developer App (Crucial Step!)
You need a free Twitter Developer account to get API keys.

Dont worry its FREE.

1.  Go to [developer.twitter.com](https://developer.twitter.com) and sign up.
2.  Create a **Free** project/app.
3.  **Configure Permissions (IMPORTANT):**
    *   Go to **Projects & Apps** > **[Your project name]** > **User authentication settings**.
    *   Click **Edit**.
    *   **App permissions**: Change to **"Read and Write"**.
    *   **Type of App**: Select "Web App, Automated App or Bot".
    *   **Callback URI / Redirect URL**: Enter `http://localhost` (required but unused).
    *   **Website URL**: Enter your Twitter profile URL (e.g., `https://twitter.com/yourhandle`).
    *   Click **Save**.
4.  **Get Your Keys:**
    *   Go to the **Keys and Tokens** tab.
    *   **API Key and Secret**: Copy these.
    *   **Access Token and Secret**: **IMPORTANT:** If you just changed permissions, you MUST click **Regenerate** here to get new tokens with "Write" access. Old tokens will fail.
    *   **Note:** You can ignore "OAuth 2.0 Client ID" and "Client Secret". You only need the 4 keys above.

### 3. Configure Environment Variables
Copy the example file to create your own configuration:

```bash
cp .env.example .env
```

Open `.env` and paste your keys:

```bash
# .env file
TWITTER_API_KEY=your_api_key
TWITTER_API_SECRET=your_api_secret
TWITTER_ACCESS_TOKEN=your_access_token
TWITTER_ACCESS_SECRET=your_access_secret
```

### 4. Configure Your Nostr Account
Add your npub to the `.env` file:

```bash
NOSTR_NPUBS=npub1...
```
You can add multiple npubs by separating them with commas:
```bash
NOSTR_NPUBS=npub1...,npub1...
```

**Optional: Custom Relays**
By default, NostrX connects to 4 popular relays. You can add your own by uncommenting and editing the `NOSTR_RELAYS` line in `.env`:
```bash
NOSTR_RELAYS=wss://relay.damus.io,wss://nos.lol,wss://your-relay.com
```
Add as many relays as you want (comma-separated). More relays = better chance of finding your posts.

## Usage

Run the script manually or via cron:

```bash
./venv/bin/python nostrx.py
```

**First Run:** It will check the last 24 hours of posts.
**Subsequent Runs:** It will only check for new posts since the last sync.

## Sync Behavior

### First Run
When you run the tool for the very first time (and `sync_state.json` doesn't exist):
- It defaults to syncing posts from the **last 24 hours only**.
- This is a safety feature to prevent spamming your Twitter account with years of history.

**Want to sync more history?**
Open `nostr_crossposter.py` and find this line (around line 60):
```python
"last_synced_timestamp": int(time.time()) - 86400,
```
Change `86400` (24 hours in seconds) to a larger number.
- `604800` = 7 days
- `2592000` = 30 days

### Subsequent Runs
- The tool creates a file called `sync_state.json`.
- It records the exact timestamp of the last post it successfully synced.
- Next time you run it, it **continues exactly where it left off**, ensuring no posts are missed and no duplicates are created.

## ⚠️ Twitter Free Tier Limits

If you are using a **Free** Twitter Developer account, be aware of these limits:
- **500 posts per month** (approx. 17 posts per day).
- If you exceed this, the script will get a `403 Forbidden` error.
- **Recommendation:** Do not set the initial history lookback too far back (e.g., don't try to sync last year's posts), or you will burn through your monthly limit immediately.

## How it Works (Technical)

- **State Tracking:** Uses `sync_state.json` to store the last synced Unix timestamp and a list of recent event IDs for deduplication.
- **Media:** Automatically detects image/video URLs in your Nostr notes, downloads them to a temporary file, and uploads them to Twitter as native media attachments.
- **One-Way:** Strictly reads from Nostr and writes to Twitter. It does not read your Tweets.

## Credits & Inspiration

This tool was inspired by [nos-crossposting-service](https://github.com/planetary-social/nos-crossposting-service) by Planetary Social. 

While that project is a centralized web service written in Go, this tool is a lightweight, self-hosted Python alternative designed for personal use.
