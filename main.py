import os
import logging
import tempfile
import json
import requests
from flask import Flask, request, jsonify
import yt_dlp as youtube_dl

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
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB Telegram limit
LAST_PROGRESS = {}  # Track progress updates per chat

def send_message(chat_id, text, reply_markup=None):
    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'Markdown'
    }
    if reply_markup:
        data['reply_markup'] = reply_markup
    requests.post(API_URL + 'sendMessage', json=data)

def process_youtube(url, chat_id):
    keyboard = {
        'inline_keyboard': [
            [
                {'text': '🎥 Video', 'callback_data': f'yt_video_{url}'},
                {'text': '🎵 Audio', 'callback_data': f'yt_audio_{url}'}
            ]
        ]
    }
    send_message(chat_id, "Choose download type:", json.dumps(keyboard))

def get_video_keyboard(url):
    try:
        ydl = youtube_dl.YoutubeDL({'quiet': True})
        info = ydl.extract_info(url, download=False)
        formats = info.get('formats', [])
        
        buttons = []
        for f in formats:
            if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                quality = f.get('format_note') or f"{f.get('height', '?')}p"
                buttons.append([{
                    'text': f"{quality} ({f['ext']})",
                    'callback_data': f"vid_{f['format_id']}_{url}"
                }])
        
        return {'inline_keyboard': buttons}
    except Exception as e:
        logging.error(f"Error getting video formats: {str(e)}")
        return {'inline_keyboard': []}

def get_audio_keyboard(url):
    keyboard = {
        'inline_keyboard': [
            [
                {'text': 'MP3', 'callback_data': f'aud_mp3_{url}'},
                {'text': 'M4A', 'callback_data': f'aud_m4a_{url}'}
            ]
        ]
    }
    return keyboard

def get_quality_keyboard(url, format_type):
    keyboard = {
        'inline_keyboard': [
            [
                {'text': 'High', 'callback_data': f'{format_type}_high_{url}'},
                {'text': 'Medium', 'callback_data': f'{format_type}_med_{url}'},
                {'text': 'Low', 'callback_data': f'{format_type}_low_{url}'}
            ]
        ]
    }
    return keyboard

def download_file(url, chat_id, ydl_opts=None, is_video=True):
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
                
                if os.path.getsize(filepath) > MAX_FILE_SIZE:
                    send_message(chat_id, "❌ File too large (max 50MB)")
                    return

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
                
                # Cleanup progress tracking
                if chat_id in LAST_PROGRESS:
                    del LAST_PROGRESS[chat_id]
                    
    except Exception as e:
        send_message(chat_id, f"❌ Error: {str(e)}")
        logging.error(f"Download failed: {str(e)}")

def progress_hook(d, chat_id):
    if d['status'] == 'downloading':
        progress = d.get('_percent_str', '')
        # Throttle progress updates to 5% increments
        if progress and (chat_id not in LAST_PROGRESS or 
                       (float(progress.strip('%')) - LAST_PROGRESS[chat_id]) >= 5):
            send_message(chat_id, f"⬇️ Downloading... {progress}")
            LAST_PROGRESS[chat_id] = float(progress.strip('%'))

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    update = request.get_json()
    
    if 'message' in update:
        msg = update['message']
        chat_id = msg['chat']['id']
        text = msg.get('text', '')
        
        if text.startswith('/start'):
            send_message(chat_id, 
                "📥 *Media Download Bot*\n\n"
                "Send me a YouTube link or direct media URL!\n"
                "Commands:\n"
                "/donate - Support development\n"
                "/help - Show help", None)
        
        elif text.startswith('/donate'):
            send_message(chat_id, f"Support us: {DONATION_URL}")
        
        elif text.startswith('/help'):
            send_message(chat_id, 
                "Help:\n"
                "- Send YouTube link for video/audio options\n"
                "- Send direct media URL to get file\n"
                "- Max file size: 50MB")
        
        elif 'youtube.com' in text or 'youtu.be' in text:
            process_youtube(text, chat_id)
        
        else:
            # Handle direct media URLs
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.head(text, headers=headers, timeout=5)
                content_type = response.headers.get('Content-Type', '')
                
                if 'video' in content_type:
                    requests.post(API_URL + 'sendVideo', 
                               json={'chat_id': chat_id, 'video': text})
                elif 'audio' in content_type:
                    requests.post(API_URL + 'sendAudio',
                               json={'chat_id': chat_id, 'audio': text})
                else:
                    send_message(chat_id, "❌ Unsupported media type")
            except Exception as e:
                send_message(chat_id, f"❌ Failed to download media: {str(e)}")
    
    elif 'callback_query' in update:
        cq = update['callback_query']
        data = cq['data']
        chat_id = cq['message']['chat']['id']
        message_id = cq['message']['message_id']
        url = data.split('_')[-1]
        
        try:
            if data.startswith('yt_video_'):
                keyboard = get_video_keyboard(url)
                requests.post(API_URL + 'editMessageText', json={
                    'chat_id': chat_id,
                    'message_id': message_id,
                    'text': 'Select video quality:',
                    'reply_markup': json.dumps(keyboard)
                })
            
            elif data.startswith('yt_audio_'):
                keyboard = get_audio_keyboard(url)
                requests.post(API_URL + 'editMessageText', json={
                    'chat_id': chat_id,
                    'message_id': message_id,
                    'text': 'Select audio format:',
                    'reply_markup': json.dumps(keyboard)
                })
            
            elif data.startswith('aud_'):
                parts = data.split('_')
                format_type = parts[1]
                keyboard = get_quality_keyboard(url, format_type)
                requests.post(API_URL + 'editMessageText', json={
                    'chat_id': chat_id,
                    'message_id': message_id,
                    'text': 'Select audio quality:',
                    'reply_markup': json.dumps(keyboard)
                })
            
            elif data.startswith(('mp3_', 'm4a_')):
                parts = data.split('_')
                format_type = parts[0]
                quality = parts[1]
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': format_type,
                        'preferredquality': '320' if quality == 'high' else '192' if quality == 'med' else '128'
                    }]
                }
                download_file(url, chat_id, ydl_opts=ydl_opts, is_video=False)
            
            elif data.startswith('vid_'):
                format_id = data.split('_')[1]
                ydl_opts = {'format': format_id}
                download_file(url, chat_id, ydl_opts=ydl_opts, is_video=True)
            
        except Exception as e:
            send_message(chat_id, f"❌ Error processing request: {str(e)}")
            logging.error(f"Callback error: {str(e)}")
        
        # Answer callback query
        requests.post(API_URL + 'answerCallbackQuery', 
                    json={'callback_query_id': cq['id']})
    
    return jsonify({'status': 'ok'})

@app.route('/')
def home():
    return 'Media Download Bot is running!'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
