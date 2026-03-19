#!/usr/bin/env python3
"""
MicroWorkers BOT - FINAL WORKING VERSION
Owner ID: 7977315501
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
from telegram.ext import Application, CommandHandler, ContextTypes

# ==================== CONFIG ====================

OWNER_ID = 7977315501
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
API_SECRET_KEY = 'f0737b7d3a2c4de47564a47ee55a59ea4f16947831848c86efafa0be926d003f'
VCODE_SECRET_KEY = '121b0fb13a9745890bf300f622e104ce39f5bc42ea8ec8915fd2bda02618d440'
API_BASE_URL = 'https://ttv.microworkers.com'
CHECK_INTERVAL = 60
PORT = int(os.environ.get('PORT', 10000))
DATA_FILE = 'users.json'

# ==================== LOGGING ====================

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

# ==================== DATA MANAGER ====================

class DataManager:
    def __init__(self):
        self.users: Set[int] = {OWNER_ID}
        self.load()
        
    def load(self):
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r') as f:
                    data = json.load(f)
                    self.users = set(data.get('users', []))
                    self.users.add(OWNER_ID)
                logger.info(f"📂 Loaded {len(self.users)} users")
        except:
            pass
            
    def save(self):
        try:
            with open(DATA_FILE, 'w') as f:
                json.dump({'users': list(self.users)}, f)
        except:
            pass
            
    def is_owner(self, user_id: int) -> bool:
        return user_id == OWNER_ID
        
    def is_user(self, user_id: int) -> bool:
        return user_id in self.users
        
    def add_user(self, user_id: int) -> bool:
        if user_id not in self.users:
            self.users.add(user_id)
            self.save()
            return True
        return False
        
    def remove_user(self, user_id: int) -> bool:
        if user_id != OWNER_ID and user_id in self.users:
            self.users.remove(user_id)
            self.save()
            return True
        return False
        
    def get_users(self) -> List[int]:
        return list(self.users)

# ==================== API CLIENT ====================

class MicroWorkersAPI:
    def __init__(self):
        self.api_key = API_SECRET_KEY
        self.vcode_key = VCODE_SECRET_KEY
        self.base_url = API_BASE_URL
        self.session = None
        
    async def get_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session
        
    async def close(self):
        if self.session:
            await self.session.close()
            
    def _sign(self, timestamp: str, method: str, path: str) -> Dict:
        payload = f"{timestamp}{method}{path}"
        vcode = hmac.new(self.vcode_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        auth = hmac.new(self.api_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return {'X-API-Key': self.api_key, 'X-VCode': vcode, 'X-Auth': auth, 'X-Timestamp': timestamp}
        
    async def get_jobs(self):
        try:
            session = await self.get_session()
            ts = str(int(time.time() * 1000))
            headers = self._sign(ts, 'GET', '/api/v2/jobs?type=all&limit=100')
            headers['Content-Type'] = 'application/json'
            
            async with session.get(f"{self.base_url}/api/v2/jobs?type=all&limit=100", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('jobs') if isinstance(data, dict) else data
        except:
            return None
        return None
        
    def find_job(self, jobs):
        if not jobs:
            return None
        keywords = ['email', 'submit', 'click', 'reply', 'screenshot']
        for job in jobs:
            try:
                title = str(job.get('title', job.get('name', ''))).lower()
                if all(k in title for k in keywords):
                    completed = int(job.get('completed_count', job.get('completed', 0)))
                    total = int(job.get('total_jobs', job.get('total', 100)))
                    return {
                        'payment': '0.10',
                        'completed': completed,
                        'total': total,
                        'remaining': total - completed,
                        'time': datetime.now().strftime('%d %H:%M')
                    }
            except:
                continue
        return None

# ==================== BOT ====================

class MicroWorkersBot:
    def __init__(self):
        self.token = TELEGRAM_TOKEN
        self.data = DataManager()
        self.api = MicroWorkersAPI()
        self.start_time = datetime.now()
        self.stats = {'checks': 0, 'notifications': 0}
        self.cache = set()
        self.running = True
        
    # ========== NOTIFICATION ==========
    
    def format_message(self, job):
        return f"""Reply + Screenshot (Read Updated...)

${job['payment']} {job['completed']}/{job['total']} {job['remaining']} left

Open Job    {job['time']}

Website: Email Submit + Click + Reply + Screenshot (Read Updated...)

${job['payment']} {job['completed']}/{job['total']} {job['remaining']} left

Open Job    {job['time']}

Microworkers Alerts
Website: Email Submit + Click + Reply + Screenshot (Read Updated...)

${job['payment']} {job['completed']}/{job['total']} {job['remaining']} left

Open Job    {job['time']}

Website: Email Submit + Click + Reply + Screenshot (Read Updated...)

${job['payment']} {job['completed']}/{job['total']} {job['remaining']} left

Open Job    {job['time']}"""
        
    async def send_to_all(self, message, keyboard=None):
        bot = Bot(token=self.token)
        sent = 0
        for uid in self.data.get_users():
            try:
                await bot.send_message(chat_id=uid, text=message, reply_markup=keyboard, parse_mode='Markdown')
                sent += 1
            except:
                pass
        return sent
        
    async def send_notification(self, job):
        key = f"{job['completed']}_{job['total']}"
        if key in self.cache:
            return
            
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🚀 OPEN JOB", url="https://www.microworkers.com/jobs.php")
        ]])
        
        sent = await self.send_to_all(self.format_message(job), keyboard)
        self.cache.add(key)
        self.stats['notifications'] += 1
        logger.info(f"✅ Notification sent to {sent} users")
        
        if len(self.cache) > 100:
            self.cache.clear()
            
    # ========== MONITORING ==========
    
    async def monitor(self):
        logger.info("🔍 Monitoring started...")
        while self.running:
            try:
                self.stats['checks'] += 1
                jobs = await self.api.get_jobs()
                if jobs:
                    job = self.api.find_job(jobs)
                    if job:
                        await self.send_notification(job)
                await asyncio.sleep(CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(60)
                
    # ========== COMMANDS ==========
    
    async def start(self, update, context):
        uid = update.effective_user.id
        if not self.data.is_user(uid):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
            
        msg = "🚀 *MicroWorkers Bot*\n\n"
        msg += f"📌 Monitoring: `Email Submit Job`\n"
        msg += f"⏱ Interval: `{CHECK_INTERVAL}s`\n\n"
        
        if self.data.is_owner(uid):
            msg += "👑 *Owner Commands*\n"
            msg += "`/users` - List users\n"
            msg += "`/add [id]` - Add user\n"
            msg += "`/remove [id]` - Remove user\n"
            msg += "`/broadcast [msg]` - Broadcast\n\n"
            
        msg += "📱 *Commands*\n"
        msg += "`/status` - Bot status\n"
        msg += "`/test` - Test notification\n"
        msg += "`/help` - Help"
        
        await update.message.reply_text(msg, parse_mode='Markdown')
        
    async def status(self, update, context):
        uid = update.effective_user.id
        if not self.data.is_user(uid):
            return
            
        uptime = datetime.now() - self.start_time
        msg = f"📊 *Status*\n\n"
        msg += f"```\n"
        msg += f"Uptime: {str(uptime).split('.')[0]}\n"
        msg += f"Checks: {self.stats['checks']}\n"
        msg += f"Notifications: {self.stats['notifications']}\n"
        msg += f"Users: {len(self.data.get_users())}\n"
        msg += f"```"
        await update.message.reply_text(msg, parse_mode='Markdown')
        
    async def test(self, update, context):
        uid = update.effective_user.id
        if not self.data.is_user(uid):
            return
            
        test_job = {
            'payment': '0.10',
            'completed': 113,
            'total': 400,
            'remaining': 287,
            'time': datetime.now().strftime('%d %H:%M')
        }
        await self.send_notification(test_job)
        await update.message.reply_text("✅ Test notification sent!")
        
    async def help(self, update, context):
        uid = update.effective_user.id
        if not self.data.is_user(uid):
            return
            
        await update.message.reply_text(
            "📚 *Help*\n\n"
            "This bot monitors MicroWorkers for:\n"
            "`Email Submit + Click + Reply + Screenshot`\n\n"
            "Commands:\n"
            "/start - Welcome\n"
            "/status - Status\n"
            "/test - Test\n"
            "/help - Help",
            parse_mode='Markdown'
        )
        
    # ========== OWNER COMMANDS ==========
    
    async def users(self, update, context):
        uid = update.effective_user.id
        if not self.data.is_owner(uid):
            return
            
        msg = "👥 *Users*\n\n"
        for u in self.data.get_users():
            if u == OWNER_ID:
                msg += f"👑 `{u}` (Owner)\n"
            else:
                msg += f"👤 `{u}`\n"
        msg += f"\nTotal: {len(self.data.get_users())}"
        await update.message.reply_text(msg, parse_mode='Markdown')
        
    async def add(self, update, context):
        uid = update.effective_user.id
        if not self.data.is_owner(uid):
            return
            
        try:
            new_id = int(context.args[0])
            if self.data.add_user(new_id):
                await update.message.reply_text(f"✅ Added `{new_id}`")
            else:
                await update.message.reply_text(f"⚠️ Already exists")
        except:
            await update.message.reply_text("❌ Usage: /add [user_id]")
            
    async def remove(self, update, context):
        uid = update.effective_user.id
        if not self.data.is_owner(uid):
            return
            
        try:
            rem_id = int(context.args[0])
            if self.data.remove_user(rem_id):
                await update.message.reply_text(f"✅ Removed `{rem_id}`")
            else:
                await update.message.reply_text(f"⚠️ Cannot remove owner or not found")
        except:
            await update.message.reply_text("❌ Usage: /remove [user_id]")
            
    async def broadcast(self, update, context):
        uid = update.effective_user.id
        if not self.data.is_owner(uid):
            return
            
        if not context.args:
            await update.message.reply_text("❌ Usage: /broadcast [message]")
            return
            
        msg = " ".join(context.args)
        sent = await self.send_to_all(f"📢 *Broadcast*\n\n{msg}", None)
        await update.message.reply_text(f"✅ Sent to {sent} users")
        
    # ========== RUN ==========
    
    async def run(self):
        print("\n" + "="*50)
        print("🚀 MICROWORKERS BOT STARTING...")
        print("="*50)
        print(f"👑 Owner: {OWNER_ID}")
        print(f"📊 Users: {len(self.data.get_users())}")
        print("="*50 + "\n")
        
        # Send startup to owner
        try:
            bot = Bot(token=self.token)
            await bot.send_message(
                chat_id=OWNER_ID,
                text="✅ *Bot Started!*\n\n"
                     f"👑 Owner: `{OWNER_ID}`\n"
                     f"📊 Users: `{len(self.data.get_users())}`",
                parse_mode='Markdown'
            )
        except:
            pass
            
        # Create application
        app = Application.builder().token(self.token).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("status", self.status))
        app.add_handler(CommandHandler("test", self.test))
        app.add_handler(CommandHandler("help", self.help))
        app.add_handler(CommandHandler("users", self.users))
        app.add_handler(CommandHandler("add", self.add))
        app.add_handler(CommandHandler("remove", self.remove))
        app.add_handler(CommandHandler("broadcast", self.broadcast))
        
        # Start monitoring
        asyncio.create_task(self.monitor())
        
        # Start bot - FIXED: using run_polling directly
        logger.info("✅ Bot is running!")
        await app.run_polling()

# ==================== WEB SERVER ====================

async def web_server():
    app = web.Application()
    
    async def home(request):
        return web.Response(
            text=f"""
            <html>
                <head><title>MicroWorkers Bot</title></head>
                <body style="font-family: Arial; padding: 40px; background: #f0f2f5;">
                    <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                        <h1 style="color: #1a73e8;">🚀 MicroWorkers Bot</h1>
                        <p style="font-size: 18px;">Status: <span style="color: green; font-weight: bold;">✅ ONLINE</span></p>
                        <p>👑 Owner ID: <code>{OWNER_ID}</code></p>
                        <p>📊 <a href="/health">Health Check</a></p>
                    </div>
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
    logger.info(f"🌐 Web: http://0.0.0.0:{PORT}")

# ==================== MAIN ====================

async def main():
    # Start web server
    await web_server()
    
    # Create and run bot
    bot = MicroWorkersBot()
    await bot.run()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped")
    except Exception as e:
        logger.error(f"💥 Error: {e}")
