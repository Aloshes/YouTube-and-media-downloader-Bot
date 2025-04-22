import os
import logging
import tempfile
import json
import requests
from flask import Flask, request, jsonify
import yt_dlp as youtube_dl
from urllib.parse import quote

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

app = Flask(__name__)

# Configuration
TOKEN = os.environ['BOT_TOKEN']
API_URL = f"https://api.telegram.org/bot{TOKEN}/"
DONATION_URL = "https://www.buymeacoffee.com/yourusername"
CHUNK_SIZE = 50 * 1024 * 1024  # 50MB chunks for large files
PROGRESS_INTERVAL = 5  # Progress update interval in percent

# Track download progress and status
download_status = {}

def send_message(chat_id, text, reply_markup=None):
    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'Markdown'
    }
    if reply_markup:
        data['reply_markup'] = reply_markup
    try:
        response = requests.post(API_URL + 'sendMessage', json=data)
        if not response.ok:
            logging.error(f"Error sending message: {response.text}")
    except Exception as e:
        logging.error(f"Failed to send message: {str(e)}")

def edit_message(chat_id, message_id, text, reply_markup=None):
    data = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': text
    }
    if reply_markup:
        data['reply_markup'] = reply_markup
    try:
        requests.post(API_URL + 'editMessageText', json=data)
    except Exception as e:
        logging.error(f"Failed to edit message: {str(e)}")

def process_youtube(url, chat_id):
    keyboard = {
        'inline_keyboard': [
            [
                {'text': '🎥 Video', 'callback_data': f'yt_video_{quote(url)}'},
                {'text': '🎵 Audio', 'callback_data': f'yt_audio_{quote(url)}'}
            ]
        ]
    }
    send_message(chat_id, "Choose download type:", json.dumps(keyboard))

def download_media(url, chat_id, ydl_opts=None, is_video=True):
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_opts = {
                'outtmpl': f'{tmpdir}/%(title)s.%(ext)s',
                'quiet': True,
                'progress_hooks': [lambda d: progress_hook(d, chat_id)]
            }
            
            if ydl_opts:
                base_opts.update(ydl_opts)
            
            with youtube_dl.YoutubeDL(base_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filepath = ydl.prepare_filename(info)
                
                # For very large files, we might need to split and send as document
                if os.path.getsize(filepath) > 2000 * 1024 * 1024:  # 2GB
                    send_message(chat_id, "⚠️ File is very large, sending as document...")
                    with open(filepath, 'rb') as f:
                        requests.post(API_URL + 'sendDocument',
                                    data={'chat_id': chat_id},
                                    files={'document': f})
                else:
                    if is_video:
                        with open(filepath, 'rb') as f:
                            requests.post(API_URL + 'sendVideo',
                                        data={'chat_id': chat_id},
                                        files={'video': f})
                    else:
                        with open(filepath, 'rb') as f:
                            requests.post(API_URL + 'sendAudio',
                                        data={'chat_id': chat_id},
                                        files={'audio': f})
                
                # Cleanup
                if chat_id in download_status:
                    del download_status[chat_id]
                    
    except Exception as e:
        send_message(chat_id, f"❌ Error: {str(e)}")
        logging.error(f"Download failed: {str(e)}")

def progress_hook(d, chat_id):
    if d['status'] == 'downloading':
        progress = d.get('_percent_str', '')
        if progress:
            current_progress = float(progress.strip('%'))
            if chat_id not in download_status or \
               current_progress - download_status.get(chat_id, {}).get('progress', 0) >= PROGRESS_INTERVAL:
                send_message(chat_id, f"⬇️ Downloading... {progress}")
                download_status[chat_id] = {'progress' : current_progress}

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    chat_id = update['message']['chat']['id']
    message_id = update['message']['message_id']
    text = update['message'].get('text', '')

    if text.startswith('/start'):
        send_message(chat_id, "Welcome! Send me a YouTube link to download.")
    elif 'youtube.com/watch' in text or 'youtu.be/' in text:
        process_youtube(text, chat_id)
    else:
        send_message(chat_id, "Please send a valid YouTube link.")

    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(port=5000)
# Ensure to set the webhook for your bot after deploying
# You can set the webhook using the following command:
# curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=<YOUR_WEBHOOK_URL>"

# Remember to replace <YOUR_BOT_TOKEN> and <YOUR_WEBHOOK_URL> with your actual bot token and webhook URL.
