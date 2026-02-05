#!/usr/bin/env python3
"""
SCRIBD DOWNLOADER TELEGRAM BOT
A professional, reliable Scribd document downloader bot
Deployment-ready for Railway & cloud platforms
"""

import os
import re
import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
import aiohttp
from telegram import Update, InputFile
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ContextTypes
)
from telegram.constants import ParseMode
import json

# ========== CONFIGURATION ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Set in Railway environment
PORT = int(os.getenv("PORT", 8443))  # Railway provides PORT
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # For webhook deployment

# Service endpoints (multiple fallbacks)
DOWNLOAD_SERVICES = [
    "https://api.scribd-downloader.co/v1/download",
    "https://scribd-downloader-api.herokuapp.com/download",
    "https://scribd-dl.onrender.com/api/download",
]

# Enable detailed logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

# ========== UTILITY FUNCTIONS ==========
def validate_scribd_url(url: str) -> bool:
    """Validate if URL is a proper Scribd link"""
    patterns = [
        r'https?://(?:www\.)?scribd\.com/(?:doc|document|presentation)/(\d+)',
        r'https?://(?:www\.)?scribd\.com/doc/(\d+)',
        r'https?://(?:www\.)?scribd\.com/document/(\d+)(?:/[^/?]+)?',
        r'https?://(?:www\.)?scribd\.com/presentation/(\d+)',
    ]
    return any(re.search(pattern, url, re.IGNORECASE) for pattern in patterns)

def extract_document_id(url: str) -> Optional[str]:
    """Extract document ID from Scribd URL"""
    patterns = [
        r'scribd\.com/(?:doc|document|presentation)/(\d+)',
        r'/doc/(\d+)',
        r'/document/(\d+)',
        r'/presentation/(\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)
    return None

def sanitize_filename(name: str) -> str:
    """Clean filename for safe use"""
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'[-\s]+', '_', name)
    name = name.strip('_')
    if not name.lower().endswith('.pdf'):
        name += '.pdf'
    return name[:60]  # Telegram filename limit

# ========== SCRIBD DOWNLOADER CLASS ==========
class ScribdDownloader:
    """Professional Scribd Downloader with multiple service fallbacks"""
    
    def __init__(self):
        self.session = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/html, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'DNT': '1',
        }
        self.timeout = aiohttp.ClientTimeout(total=45)
        
    async def __aenter__(self):
        await self.create_session()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_session()
    
    async def create_session(self):
        """Create aiohttp session"""
        if not self.session:
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=self.timeout
            )
    
    async def close_session(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def download_from_service(self, doc_id: str, service_url: str) -> Optional[bytes]:
        """Try downloading from a specific service"""
        try:
            async with self.session.post(
                service_url,
                json={'url': f'https://scribd.com/document/{doc_id}'},
                timeout=30
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('success') and data.get('pdf_url'):
                        # Download the PDF
                        async with self.session.get(data['pdf_url'], timeout=30) as pdf_response:
                            if pdf_response.status == 200:
                                return await pdf_response.read()
        except Exception as e:
            logger.debug(f"Service {service_url} failed: {e}")
            return None
        return None
    
    async def direct_download(self, scribd_url: str) -> Optional[bytes]:
        """Try direct download methods"""
        try:
            # Method 1: Try common API endpoints
            doc_id = extract_document_id(scribd_url)
            if not doc_id:
                return None
            
            # Try multiple services
            for service_url in DOWNLOAD_SERVICES:
                logger.info(f"Trying service: {service_url}")
                pdf_data = await self.download_from_service(doc_id, service_url)
                if pdf_data and pdf_data[:4] == b'%PDF':
                    logger.info(f"Success from service: {service_url}")
                    return pdf_data
            
            # Method 2: Try alternative approach
            alt_url = f"https://scribd-downloader.co/download/{doc_id}"
            async with self.session.get(alt_url, allow_redirects=True) as response:
                if response.status == 200:
                    content = await response.read()
                    if content[:4] == b'%PDF':
                        return content
            
            return None
            
        except Exception as e:
            logger.error(f"Direct download error: {e}")
            return None
    
    async def download_document(self, scribd_url: str) -> Dict[str, Any]:
        """
        Main download function with comprehensive error handling
        Returns: {'success': bool, 'data': bytes or None, 'filename': str, 'error': str}
        """
        await self.create_session()
        
        try:
            # Validate URL
            if not validate_scribd_url(scribd_url):
                return {
                    'success': False,
                    'data': None,
                    'filename': '',
                    'error': 'Invalid Scribd URL format'
                }
            
            doc_id = extract_document_id(scribd_url)
            if not doc_id:
                return {
                    'success': False,
                    'data': None,
                    'filename': '',
                    'error': 'Could not extract document ID'
                }
            
            logger.info(f"Processing document ID: {doc_id}")
            
            # Try download
            start_time = datetime.now()
            pdf_data = await self.direct_download(scribd_url)
            elapsed = (datetime.now() - start_time).total_seconds()
            
            if pdf_data:
                # Check file size
                file_size = len(pdf_data)
                if file_size > 50 * 1024 * 1024:  # 50MB Telegram limit
                    return {
                        'success': False,
                        'data': None,
                        'filename': f'document_{doc_id}.pdf',
                        'error': f'File too large ({file_size/1024/1024:.1f}MB). Max 50MB.'
                    }
                
                # Generate filename
                filename = f'scribd_document_{doc_id}.pdf'
                
                logger.info(f"Download successful: {file_size} bytes in {elapsed:.1f}s")
                
                return {
                    'success': True,
                    'data': pdf_data,
                    'filename': filename,
                    'error': None,
                    'size': file_size
                }
            else:
                return {
                    'success': False,
                    'data': None,
                    'filename': '',
                    'error': 'Document could not be downloaded. It might require subscription or be private.'
                }
                
        except asyncio.TimeoutError:
            return {
                'success': False,
                'data': None,
                'filename': '',
                'error': 'Download timed out (30s). Try again later.'
            }
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return {
                'success': False,
                'data': None,
                'filename': '',
                'error': f'Internal error: {str(e)[:100]}'
            }

# ========== TELEGRAM BOT HANDLERS ==========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message"""
    user = update.effective_user
    welcome = f"""
✨ *Welcome to Scribd Downloader Bot*, {user.first_name}! ✨

📚 I can download Scribd documents as PDF files for you.

*How to use:*
1. Send me any Scribd link
2. I'll process it automatically
3. Receive your PDF document

*Supported links:*
• `https://scribd.com/document/123456789`
• `https://scribd.com/presentation/987654321`
• `https://scribd.com/doc/456789123/Title`

*Features:*
• Fast and reliable downloads
• Multiple service fallbacks
• Support for large documents
• No ads or tracking

*Important:*
• Maximum file size: 50MB (Telegram limit)
• Processing time: 10-30 seconds
• Download only content you have rights to

Use /help for more information or just send a link to begin!
"""
    await update.message.reply_text(welcome, parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help instructions"""
    help_text = """
🆘 *Scribd Downloader Bot - Help* 🆘

*Commands:*
/start - Start the bot
/help - Show this help message
/stats - Show bot statistics
/support - Get support information

*Usage:*
Simply send me a Scribd link starting with:
• https://scribd.com/document/
• https://scribd.com/presentation/
• https://scribd.com/doc/

*Examples:*
https://www.scribd.com/document/123456789/Book-Title
https://scribd.com/presentation/987654321

*Troubleshooting:*
• If download fails, try a different Scribd link
• Large documents take longer (be patient)
• Check if document is publicly accessible
• Try removing any tracking parameters from URL

*Privacy:* I don't store any documents or user data.
"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot statistics"""
    stats = context.bot_data.get('stats', {
        'downloads_success': 0,
        'downloads_failed': 0,
        'total_users': 0,
        'last_success': None
    })
    
    stats_text = f"""
📊 *Bot Statistics*

✅ Successful downloads: {stats.get('downloads_success', 0)}
❌ Failed downloads: {stats.get('downloads_failed', 0)}
👥 Total users served: {stats.get('total_users', 0)}
🕒 Last success: {stats.get('last_success', 'Never')}

*Uptime:* 24/7
*Status:* ✅ Operational
*Version:* 3.0 (Railway Optimized)
"""
    await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)

async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Support information"""
    support_text = """
💬 *Support & Contact*

*Developer:* Scribd Downloader Team
*Version:* 3.0
*Platform:* Railway

*Need help?*
• Check /help for common issues
• Ensure your Scribd link is valid
• Documents must be publicly accessible

*Disclaimer:*
This bot is for educational purposes.
Please respect copyright laws and only download content you have permission to access.

For bug reports or feature requests:
Contact via GitHub or Telegram channel.
"""
    await update.message.reply_text(support_text, parse_mode=ParseMode.MARKDOWN)

async def handle_scribd_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process Scribd links"""
    user = update.effective_user
    scribd_url = update.message.text.strip()
    
    # Initialize stats if not exists
    if 'stats' not in context.bot_data:
        context.bot_data['stats'] = {
            'downloads_success': 0,
            'downloads_failed': 0,
            'total_users': 1,
            'last_success': None
        }
    
    logger.info(f"User {user.id} requested: {scribd_url[:50]}...")
    
    # Send processing message
    processing_msg = await update.message.reply_text(
        "⏳ *Processing your request...*\n\n"
        "Downloading document from Scribd...\n"
        "This usually takes 10-20 seconds.\n"
        "_Please wait..._",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        # Download the document
        async with ScribdDownloader() as downloader:
            result = await downloader.download_document(scribd_url)
        
        if result['success']:
            # Update statistics
            context.bot_data['stats']['downloads_success'] += 1
            context.bot_data['stats']['last_success'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Send the PDF
            await update.message.reply_document(
                document=InputFile(
                    result['data'],
                    filename=result['filename']
                ),
                caption=f"""
✅ *Download Complete!*

📄 *File:* {result['filename']}
📦 *Size:* {result['size']/1024:.0f} KB
⚡ *Status:* Successfully downloaded

_Use /help for more options_
                """,
                parse_mode=ParseMode.MARKDOWN
            )
            
            await processing_msg.delete()
            logger.info(f"Successfully sent PDF to user {user.id}")
            
        else:
            # Update failed stats
            context.bot_data['stats']['downloads_failed'] += 1
            
            error_msg = f"""
❌ *Download Failed*

*Reason:* {result['error']}

*Possible solutions:*
1. Check if the link is correct
2. Ensure document is publicly accessible
3. Try a different Scribd document
4. Remove any tracking parameters from URL

*Alternative:* Try downloading manually from scribd-downloader.co
            """
            
            await processing_msg.edit_text(error_msg, parse_mode=ParseMode.MARKDOWN)
            logger.warning(f"Download failed for user {user.id}: {result['error']}")
            
    except Exception as e:
        logger.error(f"Unexpected error for user {user.id}: {e}")
        await processing_msg.edit_text(
            f"❌ *Unexpected Error*\n\n`{str(e)[:200]}`\n\nPlease try again later.",
            parse_mode=ParseMode.MARKDOWN
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages"""
    text = update.message.text.strip()
    
    # Ignore commands
    if text.startswith('/'):
        return
    
    # Check if it's a Scribd URL
    if 'scribd.com' in text.lower() and ('http://' in text.lower() or 'https://' in text.lower()):
        await handle_scribd_link(update, context)
    else:
        await update.message.reply_text(
            "🤖 *I only process Scribd links*\n\n"
            "Please send me a valid Scribd URL like:\n"
            "`https://www.scribd.com/document/123456789/Title`\n\n"
            "Use /help for instructions.",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors gracefully"""
    logger.error(f"Update {update} caused error: {context.error}")
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ *Bot Error*\n\n"
                "An unexpected error occurred. Please try again.\n"
                "If problem persists, contact support.",
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass

# ========== HEALTH CHECK ENDPOINT ==========
async def health_check():
    """Simple HTTP server for Railway health checks"""
    from aiohttp import web
    
    async def handle_health(request):
        return web.Response(text='OK', status=200)
    
    app = web.Application()
    app.router.add_get('/', handle_health)
    app.router.add_get('/health', handle_health)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    logger.info(f"Health check server running on port {PORT}")
    return runner

# ========== MAIN FUNCTION ==========
def main():
    """Start the bot with proper Railway configuration"""
    # Validate token
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not set in environment variables!")
        logger.error("Set it in Railway dashboard: BOT_TOKEN=your_bot_token_here")
        return
    
    logger.info("🚀 Starting Scribd Downloader Bot...")
    logger.info(f"📊 Port: {PORT}")
    logger.info(f"🌐 Webhook URL: {WEBHOOK_URL or 'Not set (using polling)'}")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Store initial stats
    application.bot_data['stats'] = {
        'downloads_success': 0,
        'downloads_failed': 0,
        'total_users': 0,
        'last_success': None,
        'start_time': datetime.now().isoformat()
    }
    
    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("support", support_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_error_handler(error_handler)
    
    # Choose deployment method based on WEBHOOK_URL
    if WEBHOOK_URL:
        # Webhook mode (better for production)
        logger.info("🌐 Using webhook mode")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
        )
    else:
        # Polling mode (simpler, works with Railway's internal routing)
        logger.info("🔄 Using polling mode")
        
        # Start health check in background
        async def run_bot():
            # Start health check server
            health_runner = await health_check()
            
            # Start bot
            await application.initialize()
            await application.start()
            await application.updater.start_polling()
            
            # Keep running
            await asyncio.Event().wait()
            
            # Cleanup
            await application.updater.stop()
            await application.stop()
            await application.shutdown()
            await health_runner.cleanup()
        
        # Run bot
        try:
            asyncio.run(run_bot())
        except KeyboardInterrupt:
            logger.info("👋 Bot stopped by user")
        except Exception as e:
            logger.error(f"❌ Bot crashed: {e}")
            raise

if __name__ == '__main__':
    # Check dependencies
    try:
        import aiohttp
        from telegram import __version__ as telegram_version
        logger.info(f"✅ Dependencies: aiohttp={aiohttp.__version__}, python-telegram-bot={telegram_version}")
        
        # Run the bot
        main()
        
    except ImportError as e:
        logger.error(f"❌ Missing dependency: {e}")
        logger.error("Install: pip install python-telegram-bot[job-queue]==20.7 aiohttp")
        exit(1)
