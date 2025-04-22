import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import yt_dlp as youtube_dl
import requests

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Telegram Bot Token
TOKEN = os.getenv('BOT_TOKEN')

# Buy Me a Coffee URL
DONATION_URL = "https://www.buymeacoffee.com/yourusername"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! Send me a URL to download media or a YouTube link for video/audio downloads."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Available commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/donate - Support the developer\n"
        "\nJust send any valid URL to download media!"
    )

async def donate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Buy Me a Coffee ☕", url=DONATION_URL)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "If you find this bot useful, please consider supporting:",
        reply_markup=reply_markup
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if "youtube.com" in url or "youtu.be" in url:
        await youtube_options(update, context, url)
    else:
        await handle_media_url(update, context, url)

async def youtube_options(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    keyboard = [
        [
            InlineKeyboardButton("Video", callback_data=f"youtube_video_{url}"),
            InlineKeyboardButton("Audio", callback_data=f"youtube_audio_{url}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Choose download type:",
        reply_markup=reply_markup
    )

async def youtube_video_qualities(update: Update, url: str):
    ydl_opts = {'quiet': True, 'extract_flat': True}
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        formats = info.get('formats', [])
    
    buttons = []
    for f in formats:
        if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
            res = f.get('format_note', f.get('height'))
            buttons.append(
                InlineKeyboardButton(
                    f"{res}p ({f['ext']})",
                    callback_data=f"video_{f['format_id']}_{url}"
                )
            )
    
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Available video qualities:",
        reply_markup=reply_markup
    )

async def youtube_audio_options(update: Update, url: str):
    keyboard = [
        [
            InlineKeyboardButton("MP3", callback_data=f"audio_mp3_{url}"),
            InlineKeyboardButton("M4A", callback_data=f"audio_m4a_{url}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Choose audio format:",
        reply_markup=reply_markup
    )

async def audio_quality_options(update: Update, url: str, format_type: str):
    keyboard = [
        [
            InlineKeyboardButton("High", callback_data=f"{format_type}_high_{url}"),
            InlineKeyboardButton("Medium", callback_data=f"{format_type}_medium_{url}"),
            InlineKeyboardButton("Low", callback_data=f"{format_type}_low_{url}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Choose audio quality:",
        reply_markup=reply_markup
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    url = data.split('_')[-1]
    
    if data.startswith('youtube_video'):
        await youtube_video_qualities(query, url)
    elif data.startswith('youtube_audio'):
        await youtube_audio_options(query, url)
    elif data.startswith('audio_mp3') or data.startswith('audio_m4a'):
        await audio_quality_options(query, url, data.split('_')[1])
    elif data.startswith('mp3_') or data.startswith('m4a_'):
        await download_audio(update, context, data)
    elif data.startswith('video_'):
        await download_video(update, context, data)
    
    await query.answer()

async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query
    format_id = data.split('_')[1]
    url = '_'.join(data.split('_')[2:])
    
    ydl_opts = {
        'format': format_id,
        'outtmpl': '%(title)s.%(ext)s',
    }
    
    await query.edit_message_text("Downloading video...")
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
    
    await context.bot.send_video(
        chat_id=query.message.chat_id,
        video=open(filename, 'rb'),
        caption=info['title']
    )
    os.remove(filename)

async def download_audio(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query
    parts = data.split('_')
    format_type = parts[0]
    quality = parts[1]
    url = '_'.join(parts[2:])
    
    format_map = {
        'mp3': {
            'high': 'bestaudio/best',
            'medium': 'worstaudio/worst',
            'low': 'worstaudio/worst'
        },
        'm4a': {
            'high': 'bestaudio[ext=m4a]',
            'medium': 'worstaudio[ext=m4a]',
            'low': 'worstaudio[ext=m4a]'
        }
    }
    
    ydl_opts = {
        'format': format_map[format_type][quality],
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': format_type,
            'preferredquality': '320' if quality == 'high' else '128' if quality == 'medium' else '64'
        }],
        'outtmpl': '%(title)s.%(ext)s',
    }
    
    await query.edit_message_text("Downloading audio...")
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info).replace('.webm', f'.{format_type}')
    
    await context.bot.send_audio(
        chat_id=query.message.chat_id,
        audio=open(filename, 'rb'),
        title=info['title']
    )
    os.remove(filename)

async def handle_media_url(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    try:
        response = requests.head(url)
        content_type = response.headers.get('Content-Type', '')
        
        if 'image' in content_type:
            await update.message.reply_photo(url)
        elif 'video' in content_type:
            await update.message.reply_video(url)
        elif 'audio' in content_type:
            await update.message.reply_audio(url)
        else:
            await update.message.reply_text("Unsupported media type")
    except Exception as e:
        await update.message.reply_text(f"Error downloading media: {str(e)}")

def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("donate", donate))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    application.add_handler(CallbackQueryHandler(handle_callback))

    application.run_polling()

if __name__ == '__main__':
    main()
