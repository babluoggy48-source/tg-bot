#!/usr/bin/env python3
"""
MicroWorkers ULTIMATE BOT - With Owner System
Owner ID: 7977315501
Private commands only for owner!
"""

import os
import sys
import json
import asyncio
import aiohttp
import hmac
import hashlib
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set
from aiohttp import web

# Telegram
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== CONFIGURATION ====================

# Owner ID - SIRF YAHI WALA OWNER HOGA
OWNER_ID = 7977315501  # 👑 YEH TUM HO BHAI!

# Telegram (Render se aayega)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
if not TELEGRAM_TOKEN:
    print("❌ TELEGRAM_TOKEN environment variable not set!")
    sys.exit(1)

# API Keys (tumhare diye hue)
API_SECRET_KEY = 'f0737b7d3a2c4de47564a47ee55a59ea4f16947831848c86efafa0be926d003f'
VCODE_SECRET_KEY = '121b0fb13a9745890bf300f622e104ce39f5bc42ea8ec8915fd2bda02618d440'

# API Settings
API_BASE_URL = 'https://ttv.microworkers.com'  # Working endpoint
CHECK_INTERVAL = 45  # seconds
PORT = int(os.environ.get('PORT', 10000))

# Data file for storing authorized users
DATA_FILE = 'data.json'

# ==================== LOGGING ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ==================== DATA MANAGER ====================

class DataManager:
    """Manage authorized users"""
    
    def __init__(self):
        self.authorized_users: Set[int] = {OWNER_ID}  # Owner always included
        self.load()
        
    def load(self):
        """Load authorized users from file"""
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r') as f:
                    data = json.load(f)
                    self.authorized_users = set(data.get('users', []))
                    self.authorized_users.add(OWNER_ID)  # Ensure owner is always there
                    logger.info(f"📂 Loaded {len(self.authorized_users)} authorized users")
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            
    def save(self):
        """Save authorized users to file"""
        try:
            with open(DATA_FILE, 'w') as f:
                json.dump({'users': list(self.authorized_users)}, f)
            logger.info("💾 Data saved")
        except Exception as e:
            logger.error(f"Error saving data: {e}")
            
    def is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized"""
        return user_id in self.authorized_users
        
    def is_owner(self, user_id: int) -> bool:
        """Check if user is owner"""
        return user_id == OWNER_ID
        
    def add_user(self, user_id: int) -> bool:
        """Add user to authorized list"""
        if user_id not in self.authorized_users:
            self.authorized_users.add(user_id)
            self.save()
            return True
        return False
        
    def remove_user(self, user_id: int) -> bool:
        """Remove user from authorized list (can't remove owner)"""
        if user_id != OWNER_ID and user_id in self.authorized_users:
            self.authorized_users.remove(user_id)
            self.save()
            return True
        return False
        
    def get_all_users(self) -> List[int]:
        """Get all authorized users"""
        return list(self.authorized_users)

# ==================== API CLIENT ====================

class MicroWorkersAPI:
    """MicroWorkers API Client"""
    
    def __init__(self):
        self.api_key = API_SECRET_KEY
        self.vcode_key = VCODE_SECRET_KEY
        self.base_url = API_BASE_URL
        self.session = None
        
    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
            
    async def close(self):
        if self.session:
            await self.session.close()
            
    def _generate_signatures(self, timestamp: str, method: str, path: str) -> Dict:
        """Generate API signatures"""
        payload = f"{timestamp}{method}{path}"
        
        vcode = hmac.new(
            self.vcode_key.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        auth = hmac.new(
            self.api_key.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return {
            'X-API-Key': self.api_key,
            'X-VCode': vcode,
            'X-Auth': auth,
            'X-Timestamp': timestamp
        }
        
    async def get_jobs(self) -> Optional[List[Dict]]:
        """Fetch jobs from API"""
        try:
            await self.ensure_session()
            
            timestamp = str(int(time.time() * 1000))
            path = "/api/v2/jobs?type=all&limit=100"
            
            headers = self._generate_signatures(timestamp, 'GET', path)
            headers['Content-Type'] = 'application/json'
            
            url = f"{self.base_url}{path}"
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('jobs') if isinstance(data, dict) else data
                else:
                    return None
                    
        except Exception:
            return None
            
    def find_target_job(self, jobs: List[Dict]) -> Optional[Dict]:
        """Find Email Submit job"""
        if not jobs:
            return None
            
        keywords = ['email', 'submit', 'click', 'reply', 'screenshot']
        
        for job in jobs:
            try:
                title = str(job.get('title', job.get('name', ''))).lower()
                
                if all(k in title for k in keywords):
                    completed = int(job.get('completed_count', job.get('completed', 0)))
                    total = int(job.get('total_jobs', job.get('total', 100)))
                    remaining = total - completed
                    
                    return {
                        'payment': '0.10',
                        'completed': completed,
                        'total': total,
                        'remaining': remaining,
                        'timestamp': datetime.now().strftime('%d %H:%M')
                    }
            except:
                continue
                
        return None

# ==================== TELEGRAM BOT ====================

class MicroWorkersBot:
    """Main Bot with Owner System"""
    
    def __init__(self):
        self.token = TELEGRAM_TOKEN
        self.bot = Bot(token=self.token)
        self.api = MicroWorkersAPI()
        self.data = DataManager()
        self.start_time = datetime.now()
        self.stats = {'checks': 0, 'notifications': 0}
        self.notification_cache = set()
        self.job_monitoring = True
        
    # ========== AUTHORIZATION CHECK ==========
    
    async def is_authorized(self, update) -> bool:
        """Check if user is authorized"""
        user_id = update.effective_user.id
        if not self.data.is_authorized(user_id):
            await update.message.reply_text(
                "❌ *Unauthorized Access*\n\n"
                "You are not authorized to use this bot.\n"
                "Contact @YOUR_USERNAME for access.",
                parse_mode='Markdown'
            )
            return False
        return True
        
    # ========== JOB MONITORING ==========
    
    async def monitor_jobs(self):
        """Monitor jobs continuously"""
        logger.info("🔍 Job monitoring started...")
        
        while self.job_monitoring:
            try:
                self.stats['checks'] += 1
                
                jobs = await self.api.get_jobs()
                if jobs:
                    job = self.api.find_target_job(jobs)
                    if job:
                        cache_key = f"{job['completed']}_{job['total']}"
                        
                        if cache_key not in self.notification_cache:
                            await self.send_job_notification(job)
                            self.notification_cache.add(cache_key)
                            
                            # Clear old cache
                            if len(self.notification_cache) > 100:
                                self.notification_cache.clear()
                    
                await asyncio.sleep(CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(60)
                
    async def send_job_notification(self, job: Dict):
        """Send job notification to ALL authorized users"""
        
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
        
        keyboard = [[InlineKeyboardButton("🚀 OPEN JOB", url="https://www.microworkers.com/jobs.php")]]
        
        # Send to ALL authorized users
        sent_count = 0
        for user_id in self.data.get_all_users():
            try:
                await self.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send to {user_id}: {e}")
                
        self.stats['notifications'] += 1
        logger.info(f"✅ Notification sent to {sent_count} users")
        
    # ========== COMMANDS ==========
    
    async def cmd_start(self, update, context):
        """Start command - public"""
        if not await self.is_authorized(update):
            return
            
        user_id = update.effective_user.id
        is_owner = self.data.is_owner(user_id)
        
        message = (
            f"🚀 *MicroWorkers Bot*\n\n"
            f"📌 Monitoring: `Email Submit + Click + Reply + Screenshot`\n"
            f"⏱ Interval: `{CHECK_INTERVAL}s`\n\n"
        )
        
        if is_owner:
            message += "👑 *Owner Commands:*\n"
            message += "`/users` - List all users\n"
            message += "`/add [user_id]` - Add user\n"
            message += "`/remove [user_id]` - Remove user\n"
            message += "`/broadcast [msg]` - Broadcast\n\n"
            
        message += "📱 *User Commands:*\n"
        message += "`/status` - Bot status\n"
        message += "`/test` - Test notification\n"
        message += "`/help` - Show help"
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    async def cmd_status(self, update, context):
        """Status command - public"""
        if not await self.is_authorized(update):
            return
            
        uptime = datetime.now() - self.start_time
        
        message = (
            f"📊 *Bot Status*\n\n"
            f"```\n"
            f"Uptime: {str(uptime).split('.')[0]}\n"
            f"Checks: {self.stats['checks']}\n"
            f"Notifications: {self.stats['notifications']}\n"
            f"Users: {len(self.data.get_all_users())}\n"
            f"```"
        )
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    async def cmd_test(self, update, context):
        """Test command - send test notification"""
        if not await self.is_authorized(update):
            return
            
        test_job = {
            'payment': '0.10',
            'completed': 113,
            'total': 400,
            'remaining': 287,
            'timestamp': datetime.now().strftime('%d %H:%M')
        }
        
        await self.send_job_notification(test_job)
        await update.message.reply_text("✅ Test notification sent to all users!")
        
    async def cmd_help(self, update, context):
        """Help command - public"""
        if not await self.is_authorized(update):
            return
            
        await update.message.reply_text(
            "📚 *Help*\n\n"
            "This bot monitors MicroWorkers for:\n"
            "`Email Submit + Click + Reply + Screenshot`\n\n"
            "Commands:\n"
            "/start - Welcome\n"
            "/status - Bot status\n"
            "/test - Test notification\n"
            "/help - This help",
            parse_mode='Markdown'
        )
        
    # ========== OWNER ONLY COMMANDS ==========
    
    async def cmd_users(self, update, context):
        """List all users - OWNER ONLY"""
        user_id = update.effective_user.id
        
        if not self.data.is_owner(user_id):
            await update.message.reply_text("❌ This command is only for owner!")
            return
            
        users = self.data.get_all_users()
        message = "👥 *Authorized Users*\n\n"
        
        for uid in users:
            if uid == OWNER_ID:
                message += f"👑 `{uid}` (Owner)\n"
            else:
                message += f"👤 `{uid}`\n"
                
        message += f"\nTotal: {len(users)} users"
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    async def cmd_add(self, update, context):
        """Add user - OWNER ONLY"""
        user_id = update.effective_user.id
        
        if not self.data.is_owner(user_id):
            await update.message.reply_text("❌ This command is only for owner!")
            return
            
        try:
            new_user = int(context.args[0])
            if self.data.add_user(new_user):
                await update.message.reply_text(f"✅ User `{new_user}` added successfully!")
            else:
                await update.message.reply_text(f"⚠️ User `{new_user}` already exists!")
        except:
            await update.message.reply_text("❌ Usage: /add [user_id]")
            
    async def cmd_remove(self, update, context):
        """Remove user - OWNER ONLY"""
        user_id = update.effective_user.id
        
        if not self.data.is_owner(user_id):
            await update.message.reply_text("❌ This command is only for owner!")
            return
            
        try:
            remove_id = int(context.args[0])
            if self.data.remove_user(remove_id):
                await update.message.reply_text(f"✅ User `{remove_id}` removed successfully!")
            else:
                await update.message.reply_text(f"⚠️ Cannot remove owner or user not found!")
        except:
            await update.message.reply_text("❌ Usage: /remove [user_id]")
            
    async def cmd_broadcast(self, update, context):
        """Broadcast message to all users - OWNER ONLY"""
        user_id = update.effective_user.id
        
        if not self.data.is_owner(user_id):
            await update.message.reply_text("❌ This command is only for owner!")
            return
            
        if not context.args:
            await update.message.reply_text("❌ Usage: /broadcast [message]")
            return
            
        message = " ".join(context.args)
        broadcast_msg = f"📢 *Broadcast from Owner*\n\n{message}"
        
        sent = 0
        failed = 0
        
        for uid in self.data.get_all_users():
            if uid != user_id:  # Don't send to owner
                try:
                    await self.bot.send_message(
                        chat_id=uid,
                        text=broadcast_msg,
                        parse_mode='Markdown'
                    )
                    sent += 1
                except:
                    failed += 1
                    
        await update.message.reply_text(
            f"✅ Broadcast sent!\n"
            f"📨 Sent: {sent}\n"
            f"❌ Failed: {failed}"
        )
        
    # ========== RUN BOT ==========
    
    async def run(self):
        """Main run method"""
        print("\n" + "="*50)
        print("🚀 MICROWORKERS BOT - OWNER EDITION")
        print("="*50)
        print(f"👑 Owner ID: {OWNER_ID}")
        print(f"📊 Total Users: {len(self.data.get_all_users())}")
        print("="*50 + "\n")
        
        # Send startup message to owner
        try:
            await self.bot.send_message(
                chat_id=OWNER_ID,
                text="✅ *Bot Started!*\n\n"
                     f"👑 Owner: `{OWNER_ID}`\n"
                     f"📊 Users: `{len(self.data.get_all_users())}`\n"
                     f"⏱ Interval: `{CHECK_INTERVAL}s`",
                parse_mode='Markdown'
            )
            logger.info("✅ Startup message sent to owner")
        except Exception as e:
            logger.error(f"Failed to send startup message: {e}")
            
        # Create application
        app = Application.builder().token(self.token).build()
        
        # Public commands (for authorized users)
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("test", self.cmd_test))
        app.add_handler(CommandHandler("help", self.cmd_help))
        
        # Owner only commands
        app.add_handler(CommandHandler("users", self.cmd_users))
        app.add_handler(CommandHandler("add", self.cmd_add))
        app.add_handler(CommandHandler("remove", self.cmd_remove))
        app.add_handler(CommandHandler("broadcast", self.cmd_broadcast))
        
        # Start monitoring
        asyncio.create_task(self.monitor_jobs())
        
        # Start bot
        logger.info("✅ Bot is running!")
        await app.run_polling(allowed_updates=['message'])

# ==================== WEB SERVER ====================

async def web_server():
    """Simple web server for Render health checks"""
    app = web.Application()
    
    async def home(request):
        uptime = datetime.now() - bot.start_time if 'bot' in globals() else datetime.now() - datetime.now()
        return web.Response(
            text=f"""
            <html>
                <head><title>MicroWorkers Bot</title></head>
                <body style="font-family: Arial; padding: 40px;">
                    <h1>🚀 MicroWorkers Bot</h1>
                    <p>Status: ✅ ONLINE</p>
                    <p>Owner ID: {OWNER_ID}</p>
                    <p>Uptime: {str(uptime).split('.')[0]}</p>
                    <p><a href="/health">Health Check</a></p>
                </body>
            </html>
            """,
            content_type='text/html'
        )
        
    async def health(request):
        return web.json_response({'status': 'ok', 'owner': OWNER_ID})
        
    app.router.add_get('/', home)
    app.router.add_get('/health', health)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"🌐 Web server running on port {PORT}")

# ==================== MAIN ====================

bot = None

async def main():
    global bot
    bot = MicroWorkersBot()
    
    # Start web server
    await web_server()
    
    # Run bot
    await bot.run()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
