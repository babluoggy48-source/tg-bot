#!/usr/bin/env python3
"""
MicroWorkers Premium Job Bot - FIXED VERSION
Complete solution for "Email Submit + Click + Reply + Screenshot" job notifications
"""

import os
import sys
import json
import asyncio
import aiohttp
import hmac
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging
import traceback

# Try to import colorama (optional)
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    COLORS_AVAILABLE = True
except ImportError:
    COLORS_AVAILABLE = False
    # Create dummy color classes
    class Fore:
        RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ''
    class Style:
        BRIGHT = RESET_ALL = ''

# Import telegram with proper error handling
try:
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.error import TelegramError, TimedOut, NetworkError
    from telegram.ext import Application, CommandHandler, ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError as e:
    print(f"❌ Telegram import error: {e}")
    print("📦 Run: pip install python-telegram-bot==20.7")
    sys.exit(1)

# ==================== CONFIGURATION ====================

class Config:
    """Configuration management from environment variables"""
    
    # Required - Get from environment
    TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
    
    # API Keys (your provided keys)
    API_SECRET_KEY = os.environ.get('API_SECRET_KEY', 'f0737b7d3a2c4de47564a47ee55a59ea4f16947831848c86efafa0be926d003f')
    VCODE_SECRET_KEY = os.environ.get('VCODE_SECRET_KEY', '121b0fb13a9745890bf300f622e104ce39f5bc42ea8ec8915fd2bda02618d440')
    
    # API Endpoints
    API_BASE_URL = os.environ.get('API_BASE_URL', 'https://ttv.microworkers.com')
    API_VERSION = '2.0.0'
    
    # Job Settings
    TARGET_JOB_PATTERN = os.environ.get('TARGET_JOB_PATTERN', 'Email Submit + Click + Reply + Screenshot')
    CHECK_INTERVAL = int(os.environ.get('CHECK_INTERVAL', '30'))
    NOTIFICATION_COOLDOWN = int(os.environ.get('NOTIFICATION_COOLDOWN', '300'))
    
    # Bot Settings
    DEBUG_MODE = os.environ.get('DEBUG_MODE', 'false').lower() == 'true'
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# ==================== LOGGING SETUP ====================

def setup_logging():
    """Setup logging"""
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL),
        format='%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# ==================== API CLIENT ====================

class MicroWorkersAPIClient:
    """API Client for MicroWorkers v2.0.0"""
    
    def __init__(self):
        self.api_key = Config.API_SECRET_KEY
        self.vcode_key = Config.VCODE_SECRET_KEY
        self.base_url = Config.API_BASE_URL
        self.session = None
        self.request_count = 0
        
    async def ensure_session(self):
        """Ensure aiohttp session exists"""
        if not self.session:
            self.session = aiohttp.ClientSession(
                headers={
                    'User-Agent': f'MicroWorkersBot/{Config.API_VERSION}',
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                },
                timeout=aiohttp.ClientTimeout(total=30)
            )
            
    async def close(self):
        """Close session properly"""
        if self.session:
            await self.session.close()
            self.session = None
            
    def _generate_signatures(self, timestamp: str, method: str, path: str) -> Dict[str, str]:
        """Generate authentication signatures"""
        try:
            payload = f"{timestamp}{method}{path}"
            
            vcode_signature = hmac.new(
                self.vcode_key.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            auth_signature = hmac.new(
                self.api_key.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            return {
                'X-VCode': vcode_signature,
                'X-Auth': auth_signature,
                'X-Timestamp': timestamp,
                'X-API-Key': self.api_key
            }
            
        except Exception as e:
            logger.error(f"❌ Signature generation failed: {e}")
            raise
            
    async def get_jobs(self) -> Optional[List[Dict]]:
        """Fetch jobs from API"""
        try:
            await self.ensure_session()
            
            timestamp = str(int(time.time() * 1000))
            path = "/api/v2/jobs?type=all&limit=200"
            method = "GET"
            
            headers = self._generate_signatures(timestamp, method, path)
            
            async with self.session.get(f"{self.base_url}{path}", headers=headers) as response:
                self.request_count += 1
                
                if response.status == 200:
                    data = await response.json()
                    jobs = data.get('jobs') if isinstance(data, dict) else data
                    logger.info(f"📊 API Call #{self.request_count} | Jobs: {len(jobs) if jobs else 0}")
                    return jobs
                else:
                    error_text = await response.text()
                    logger.error(f"❌ API Error {response.status}: {error_text[:200]}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error("⏰ Request timeout")
            return None
        except Exception as e:
            logger.error(f"❌ API Error: {e}")
            return None
            
    def find_target_jobs(self, jobs: List[Dict]) -> List[Dict]:
        """Find target jobs"""
        matches = []
        keywords = ['email', 'submit', 'click', 'reply', 'screenshot']
        
        if not jobs:
            return matches
            
        for job in jobs:
            try:
                title = str(job.get('title', job.get('name', ''))).lower()
                
                if all(keyword in title for keyword in keywords):
                    completed = int(job.get('completed_count', job.get('completed', 0)))
                    total = int(job.get('total_jobs', job.get('total', 100)))
                    remaining = max(0, total - completed)
                    
                    job_info = {
                        'payment': '0.10',
                        'completed': completed,
                        'total': total,
                        'remaining': remaining,
                        'timestamp': datetime.now().strftime('%d %H:%M')
                    }
                    matches.append(job_info)
                    logger.info(f"🎯 Found: {completed}/{total} ({remaining} left)")
                    
            except Exception as e:
                continue
                
        return matches

# ==================== TELEGRAM BOT ====================

class MicroWorkersBot:
    """Telegram Bot for job notifications"""
    
    def __init__(self):
        self.token = Config.TELEGRAM_TOKEN
        self.chat_id = Config.TELEGRAM_CHAT_ID
        self.api = MicroWorkersAPIClient()
        self.bot = Bot(token=self.token)
        self.application = None
        self.running = True
        self.notification_cache = {}
        self.stats = {
            'start_time': datetime.now(),
            'total_checks': 0,
            'total_notifications': 0
        }
        
    def print_banner(self):
        """Print startup banner"""
        banner = f"""
╔══════════════════════════════════════════════════╗
║  ███╗   ███╗██╗ ██████╗██████╗  ██████╗ ██╗    ██╗ ██████╗ ██████╗ ██╗  ██╗███████╗██████╗ ███████╗
║  ████╗ ████║██║██╔════╝██╔══██╗██╔═══██╗██║    ██║██╔═══██╗██╔══██╗██║ ██╔╝██╔════╝██╔══██╗██╔════╝
║  ██╔████╔██║██║██║     ██████╔╝██║   ██║██║ █╗ ██║██║   ██║██████╔╝█████╔╝ █████╗  ██████╔╝███████╗
║  ██║╚██╔╝██║██║██║     ██╔══██╗██║   ██║██║███╗██║██║   ██║██╔══██╗██╔═██╗ ██╔══╝  ██╔══██╗╚════██║
║  ██║ ╚═╝ ██║██║╚██████╗██║  ██║╚██████╔╝╚███╔███╔╝╚██████╔╝██║  ██║██║  ██╗███████╗██║  ██║███████║
║  ╚═╝     ╚═╝╚═╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝  ╚══╝╚══╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚══════╝
╚══════════════════════════════════════════════════╝
⚡ Premium Job Notification Bot v{Config.API_VERSION} ⚡
────────────────────────────────────────────────────
"""
        print(banner)
        
    async def verify_chat_id(self):
        """Verify Telegram chat ID is valid"""
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text="🟢 *Bot Connected Successfully!*\n\nMonitoring: `Email Submit + Click + Reply + Screenshot`",
                parse_mode='Markdown'
            )
            logger.info("✅ Chat ID verified successfully")
            return True
        except TelegramError as e:
            logger.error(f"❌ Invalid Chat ID: {e}")
            logger.info("\n📝 How to fix:")
            logger.info("1. Message @userinfobot on Telegram")
            logger.info("2. Send /start to get your ID")
            logger.info("3. Copy the number and update TELEGRAM_CHAT_ID")
            return False
            
    async def start(self):
        """Start the bot"""
        self.print_banner()
        
        # Validate config
        if not self.token:
            logger.error("❌ TELEGRAM_TOKEN not set")
            return
        if not self.chat_id:
            logger.error("❌ TELEGRAM_CHAT_ID not set")
            return
            
        # Verify chat ID first
        logger.info("🔍 Verifying Telegram connection...")
        if not await self.verify_chat_id():
            return
            
        # Setup application
        self.application = Application.builder().token(self.token).build()
        
        # Add command handlers
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        self.application.add_handler(CommandHandler("test", self.cmd_test))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        
        # Start monitoring in background
        asyncio.create_task(self.monitoring_loop())
        
        # Start bot
        logger.info("🚀 Bot is running...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        # Keep running
        while self.running:
            await asyncio.sleep(1)
            
    async def monitoring_loop(self):
        """Main monitoring loop"""
        logger.info("🔍 Starting monitoring loop...")
        
        while self.running:
            try:
                self.stats['total_checks'] += 1
                
                jobs = await self.api.get_jobs()
                if jobs:
                    target_jobs = self.api.find_target_jobs(jobs)
                    for job in target_jobs:
                        await self.send_notification(job)
                        
                await asyncio.sleep(Config.CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"❌ Monitoring error: {e}")
                await asyncio.sleep(60)
                
    async def send_notification(self, job: Dict):
        """Send job notification"""
        try:
            cache_key = f"{job['completed']}_{job['total']}"
            
            # Check cache
            if cache_key in self.notification_cache:
                time_diff = (datetime.now() - self.notification_cache[cache_key]).seconds
                if time_diff < Config.NOTIFICATION_COOLDOWN:
                    return
                    
            # Format message exactly like screenshot
            message = f"""Reply + Screenshot (Read Updated...)

${job['payment']} {job['completed']}/{job['total']} {job['remaining']} left

Open Job    {job['timestamp']}

Website: Email Submit + Click + Reply + Screenshot (Read Updated...)

${job['payment']} {job['completed']}/{job['total']} {job['remaining']} left

Open Job    {job['timestamp']}

Microworkers Alerts
Website: Email Submit + Click + Reply + Screenshot (Read Updated...)

${job['payment']} {job['completed']}/{job['total']} {job['remaining']} left

Open Job    {job['timestamp']}

Website: Email Submit + Click + Reply + Screenshot (Read Updated...)

${job['payment']} {job['completed']}/{job['total']} {job['remaining']} left

Open Job    {job['timestamp']}"""
            
            # Create button
            keyboard = [[
                InlineKeyboardButton(
                    "🚀 OPEN JOB",
                    url="https://www.microworkers.com/jobs.php"
                )
            ]]
            
            # Send message
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Update cache
            self.notification_cache[cache_key] = datetime.now()
            self.stats['total_notifications'] += 1
            
            logger.info(f"✅ Notification #{self.stats['total_notifications']} sent")
            
            # Clean old cache
            self.clean_cache()
            
        except Exception as e:
            logger.error(f"❌ Send error: {e}")
            
    def clean_cache(self):
        """Clean old cache entries"""
        current_time = datetime.now()
        keys_to_delete = []
        
        for key, timestamp in self.notification_cache.items():
            if (current_time - timestamp).seconds > 3600:
                keys_to_delete.append(key)
                
        for key in keys_to_delete:
            del self.notification_cache[key]
            
    # Command handlers
    async def cmd_start(self, update, context):
        await update.message.reply_text(
            "🚀 *MicroWorkers Bot*\n\n"
            "Monitoring: `Email Submit + Click + Reply + Screenshot`\n\n"
            "Commands:\n"
            "/status - Bot status\n"
            "/test - Test notification\n"
            "/help - Help",
            parse_mode='Markdown'
        )
        
    async def cmd_status(self, update, context):
        uptime = datetime.now() - self.stats['start_time']
        await update.message.reply_text(
            f"📊 *Bot Status*\n\n"
            f"Uptime: {str(uptime).split('.')[0]}\n"
            f"Checks: {self.stats['total_checks']}\n"
            f"Notifications: {self.stats['total_notifications']}",
            parse_mode='Markdown'
        )
        
    async def cmd_test(self, update, context):
        test_job = {
            'payment': '0.10',
            'completed': 113,
            'total': 400,
            'remaining': 287,
            'timestamp': datetime.now().strftime('%d %H:%M')
        }
        await self.send_notification(test_job)
        await update.message.reply_text("✅ Test sent!")
        
    async def cmd_help(self, update, context):
        await update.message.reply_text(
            "📚 *Commands*\n\n"
            "/start - Welcome\n"
            "/status - Status\n"
            "/test - Test\n"
            "/help - This",
            parse_mode='Markdown'
        )

# ==================== MAIN ====================

async def main():
    """Main entry point"""
    bot = MicroWorkersBot()
    await bot.start()

def run():
    """Run the bot"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped")
    except Exception as e:
        logger.error(f"💥 Error: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    run()
