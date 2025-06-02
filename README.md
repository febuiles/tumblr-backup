# Tumblr Backups

These scripts fetch all your Tumblr posts and their media files, storing them in a local SQLite database and downloading all media files to a local directory.

<img width="1134" alt="Screenshot 2025-06-02 at 20 09 45" src="https://github.com/user-attachments/assets/5fccc40e-7f07-469e-97fe-266452355b9b" />


## Setup

1. Get Tumblr API credentials:
   - Go to https://www.tumblr.com/oauth/apps
   - Click "Register application"
   - Fill in the application details:
     - Application name: "Tumblr Backup" (or any name you prefer)
     - Application website: can be any URL
     - Application description: "Personal backup tool"
     - Default callback URL: http://localhost:4567/callback
   - After registering, you'll get:
     - OAuth Consumer Key
     - OAuth Consumer Secret

2. Use the keys to create a `.env` file in the project root:
   ```
   TUMBLR_CONSUMER_KEY=your_consumer_key_here
   TUMBLR_CONSUMER_SECRET=your_consumer_secret_here
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Get OAuth tokens:
   ```bash
   python get_oauth_tokens.py
   ```
   This will either guide you through the OAuth authorization and save
   the new tokens automatically, or if will crash and die. Good luck!

5. Run the backup:
   ```bash
   python tumblr_backup.py
   ```
   This will create the SQLite database and start backing up your
   posts. It won't overwrite existing posts.

## Usage

To fetch your posts and media:

```bash
python tumblr_backup.py
```

You can run this command multiple times but the script will only download new posts and media files that haven't been backed up yet.

## Web Viewer

To view your backed up posts in a web interface:

```bash
python web_viewer.py
```

Then open http://localhost:3000 in your browser.
