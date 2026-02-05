#!/usr/bin/env python3
"""
Scribd Downloader Telegram Bot
Sends PDFs from Scribd links using scribd-downloader.co
"""

import os
import re
import logging
import asyncio
from typing import Optional
import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ========== CONFIGURATION ==========
# Get your bot token from environment variable (SAFE WAY)
BOT_TOKEN = os.getenv("8561803442:AAF6DwuG_kNZMa_y132KTc_Pbg1FNrSWrxI")  # Set this in your system or Railway/Heroku

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== SCRIBD DOWNLOADER CLASS ==========
class AsyncScribdDownloader:
    """Async version of Scribd downloader using aiohttp"""
    
    def __init__(self):
        self.base_url = "https://scribd-downloader.co"
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def init_session(self):
        """Initialize aiohttp session"""
        if not self.session:
            self.session = aiohttp.ClientSession(
                headers={
                    'User-Agent': self.user_agent,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            )
    
    async def close_session(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()
    
    def extract_doc_info(self, url: str) -> Optional[dict]:
        """Extract document ID and name from Scribd URL"""
        patterns = [
            r'scribd\.com/(?:doc|document|presentation)/(\d+)(?:/([^/?]+))?',
            r'scribd\.com/doc/(\d+)',
            r'scribd\.com/document/(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                doc_id = match.group(1)
                doc_name = match.group(2) if match.groups() > 1 else None
                return {'id': doc_id, 'name': doc_name}
        
        return None
    
    async def get_pdf_from_url(self, scribd_url: str) -> Optional[bytes]:
        """
        Get PDF from scribd-downloader.co
        Uses the website's actual form submission
        """
        try:
            await self.init_session()
            
            # Extract document ID
            doc_info = self.extract_doc_info(scribd_url)
            if not doc_info:
                logger.error(f"Invalid Scribd URL: {scribd_url}")
                return None
            
            doc_id = doc_info['id']
            logger.info(f"Processing document ID: {doc_id}")
            
            # Method 1: Try direct download endpoint (most reliable)
            pdf_url = f"https://scribd-downloader.co/api/download/{doc_id}"
            
            async with self.session.get(pdf_url, timeout=30) as response:
                if response.status == 200:
                    content = await response.read()
                    if content[:4] == b'%PDF':
                        logger.info(f"Successfully downloaded PDF via direct endpoint")
                        return content
            
            # Method 2: Use the main website form
            logger.info("Trying main website form...")
            
            # First, get the page to get cookies
            async with self.session.get(self.base_url, timeout=30) as response:
                if response.status != 200:
                    logger.error(f"Failed to access site: {response.status}")
                    return None
            
            # Prepare form submission (simulating the actual form)
            form_data = aiohttp.FormData()
            form_data.add_field('url', scribd_url)
            form_data.add_field('format', 'pdf')
            form_data.add_field('action', 'download')
            
            # Submit the form
            async with self.session.post(
                self.base_url,
                data=form_data,
                timeout=30
            ) as response:
                if response.status == 200:
                    html = await response.text()
                    
                    # Look for download links in the HTML
                    download_patterns = [
                        r'<a[^>]*href="([^"]+\.pdf)"[^>]*>',
                        r'download="([^"]+)"',
                        r'"(https?://[^"]+\.pdf)"',
                        r'window\.location\.href\s*=\s*["\']([^"\']+)["\']',
                    ]
                    
                    for pattern in download_patterns:
                        matches = re.findall(pattern, html, re.IGNORECASE)
                        for match in matches:
                            pdf_url = match
                            if not pdf_url.startswith('http'):
                                pdf_url = self.base_url + pdf_url
                            
                            logger.info(f"Found PDF URL: {pdf_url}")
                            
                            # Download the PDF
                            async with self.session.get(pdf_url, timeout=30) as pdf_response:
                                if pdf_response.status == 200:
                                    content = await pdf_response.read()
                                    if content[:4] == b'%PDF':
                                        return content
            
            logger.error("No PDF found in response")
            return None
            
        except asyncio.TimeoutError:
            logger.error("Request timed out")
            return None
        except Exception as e:
            logger.error(f"Error downloading PDF: {e}")
            return None

# ========== TELEGRAM BOT HANDLERS ==========
downloader = AsyncScribdDownloader()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    welcome_text = f"""
👋 Hello {user.first_name}!

📚 *Scribd Downloader Bot*

I can download Scribd documents as PDF for you!

*How to use:*
1. Send me any Scribd link
2. I'll process it
3. You'll receive the PDF

*Examples:*
• https://www.scribd.com/document/123456789/Title
• https://www.scribd.com/presentation/987654321
• https://www.scribd.com/doc/456789123

*Note:* Please only download content you have rights to access.

Send /help for more info.
"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = """
🆘 *Help - Scribd Downloader Bot*

*Commands:*
/start - Start the bot
/help - Show this help message
/about - About this bot

*Usage:*
Simply send me a Scribd link and I'll download it as PDF.

*Supported links:*
• https://scribd.com/document/...
• https://scribd.com/presentation/...
• https://scribd.com/doc/...

*Important:*
• Large documents may take longer to process
• Maximum file size: 50MB (Telegram limit)
• Please be patient during processing

*Privacy:* I don't store any documents or user data.
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send information about the bot."""
    about_text = """
ℹ️ *About Scribd Downloader Bot*

*Version:* 2.0
*Developer:* Your Developer Name

*Features:*
• Fast PDF downloads from Scribd
• Support for documents and presentations
• Clean, easy-to-use interface
• No ads or tracking

*Technology:*
• Built with Python 3.10+
• Uses scribd-downloader.co service
• Async/await for better performance

*Disclaimer:*
This bot is for educational purposes only.
Please respect copyright laws and only download content you have permission to access.

*Support:* Contact @yourusername for help
"""
    await update.message.reply_text(about_text, parse_mode='Markdown')

async def handle_scribd_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Scribd links sent by users."""
    scribd_url = update.message.text.strip()
    
    # Check if it's a valid Scribd URL
    if not re.search(r'scribd\.com/(?:doc|document|presentation)/', scribd_url, re.IGNORECASE):
        await update.message.reply_text(
            "❌ *Invalid URL*\n\n"
            "Please send a valid Scribd link.\n"
            "Example: `https://www.scribd.com/document/123456789/Title`",
            parse_mode='Markdown'
        )
        return
    
    # Send processing message
    processing_msg = await update.message.reply_text(
        "🔄 *Processing your request...*\n\n"
        "This may take 20-30 seconds depending on document size.\n"
        "Please wait...",
        parse_mode='Markdown'
    )
    
    try:
        # Download PDF
        pdf_content = await downloader.get_pdf_from_url(scribd_url)
        
        if pdf_content:
            # Create filename
            doc_info = downloader.extract_doc_info(scribd_url)
            if doc_info and doc_info.get('name'):
                # Clean filename
                filename = re.sub(r'[^\w\-\.]', '_', doc_info['name'])
                if not filename.lower().endswith('.pdf'):
                    filename += '.pdf'
            else:
                filename = f"document_{doc_info['id'] if doc_info else 'unknown'}.pdf"
            
            # Check file size (Telegram limit: 50MB)
            if len(pdf_content) > 50 * 1024 * 1024:
                await processing_msg.edit_text(
                    "❌ *File too large*\n\n"
                    "The document exceeds Telegram's 50MB limit.\n"
                    "Try downloading it directly from scribd-downloader.co",
                    parse_mode='Markdown'
                )
                return
            
            # Send PDF
            await update.message.reply_document(
                document=pdf_content,
                filename=filename[:64],  # Telegram filename limit
                caption="✅ *Download Complete!*\n\n"
                       "Here's your PDF from Scribd.\n"
                       f"Filename: `{filename}`",
                parse_mode='Markdown'
            )
            
            # Delete processing message
            await processing_msg.delete()
            
            logger.info(f"Successfully sent PDF for URL: {scribd_url}")
            
        else:
            await processing_msg.edit_text(
                "❌ *Download Failed*\n\n"
                "Could not download the PDF. Possible reasons:\n"
                "• Document requires login/subscription\n"
                "• Link is invalid or private\n"
                "• Service is temporarily unavailable\n\n"
                "Try: https://scribd-downloader.co",
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Error processing {scribd_url}: {e}")
        await processing_msg.edit_text(
            f"❌ *Error*\n\nAn error occurred: `{str(e)}`\n\nPlease try again later.",
            parse_mode='Markdown'
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle any text message."""
    text = update.message.text
    
    if text.startswith('/'):
        # It's a command, ignore here
        return
    
    # Check if it looks like a URL
    if 'scribd.com' in text.lower() and 'http' in text.lower():
        await handle_scribd_link(update, context)
    else:
        await update.message.reply_text(
            "📝 *I can only process Scribd links*\n\n"
            "Please send me a Scribd URL starting with:\n"
            "• `https://scribd.com/document/`\n"
            "• `https://scribd.com/presentation/`\n"
            "• `https://scribd.com/doc/`\n\n"
            "Send /help for more information.",
            parse_mode='Markdown'
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors."""
    logger.error(f"Update {update} caused error: {context.error}")

# ========== MAIN FUNCTION ==========
def main() -> None:
    """Start the bot."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN environment variable is not set!")
        logger.error("Get a token from @BotFather and set it as BOT_TOKEN")
        return
    
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Register error handler
    application.add_error_handler(error_handler)
    
    # Start the bot
    logger.info("Starting Scribd Downloader Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    # Check for required packages
    try:
        import aiohttp
        import telegram
    except ImportError as e:
        logger.error(f"Missing package: {e}")
        logger.error("Install with: pip install aiohttp python-telegram-bot")
        exit(1)
    
    # Run the bot
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        # Close downloader session
        asyncio.run(downloader.close_session())
    finally:
        logger.info("Bot shutdown complete")