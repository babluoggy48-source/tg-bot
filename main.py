#!/usr/bin/env python3
"""
MicroWorkers Bot - SIMPLE WORKING VERSION
Owner: 7977315501
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
from telegram.ext import Application, CommandHandler
from telegram.error import TelegramError

# ==================== CONFIG ====================

OWNER_ID = 7977315501
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
API_SECRET_KEY = 'f0737b7d3a2c4de47564a47ee55a59ea4f16947831848c86efafa0be926d003f'
VCODE_SECRET_KEY = '121b0fb13a9745890bf300f622e104ce39f5bc42ea8ec8915fd2bda02618d440'
API_BASE_URL = 'https://ttv.microworkers.com'
CHECK_INTERVAL = 60
PORT = int(os.environ.get('PORT', 10000))
RENDER_URL = 'https://tg-bot-hmpa.onrender.com'
DATA_FILE = 'users.json'

# ==================== LOGGING ====================

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s')
logger = logging.getLogger(__name__)

# ==================== DATA MANAGER ====================

class DataManager:
    def __init__(self):
        self.users = {OWNER_ID}
        self.load()
        
    def load(self):
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE) as f:
                    self.users = set(json.load(f).get('users', [])) | {OWNER_ID}
        except:
            pass
            
    def save(self):
        try:
            with open(DATA_FILE, 'w') as f:
                json.dump({'users': list(self.users)}, f)
        except:
            pass
            
    def is_owner(self, uid): return uid == OWNER_ID
    def is_user(self, uid): return uid in self.users
    def add(self, uid): 
        if uid not in self.users:
            self.users.add(uid)
            self.save()
            return True
        return False
    def remove(self, uid):
        if uid != OWNER_ID and uid in self.users:
            self.users.remove(uid)
            self.save()
            return True
        return False
    def get_all(self): return list(self.users)

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
        
    def _sign(self, ts, method, path):
        payload = f"{ts}{method}{path}"
        vcode = hmac.new(self.vcode_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        auth = hmac.new(self.api_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return {'X-API-Key': self.api_key, 'X-VCode': vcode, 'X-Auth': auth, 'X-Timestamp': ts}
        
    async def get_jobs(self):
        try:
            session = await self.get_session()
            ts = str(int(time.time() * 1000))
            path = '/api/v2/jobs?type=all&limit=100'
            headers = self._sign(ts, 'GET', path)
            headers['Content-Type'] = 'application/json'
            
            async with session.get(f"{self.base_url}{path}", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    jobs = data.get('jobs') if isinstance(data, dict) else data
                    if jobs:
                        logger.info(f"📊 Got {len(jobs)} jobs")
                    return jobs
        except Exception as e:
            logger.error(f"API error: {e}")
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
        
    async def send_to_all(self, text, keyboard=None):
        bot = Bot(token=self.token)
        sent = 0
        for uid in self.data.get_all():
            try:
                await bot.send_message(chat_id=uid, text=text, reply_markup=keyboard, parse_mode='Markdown')
                sent += 1
                await asyncio.sleep(0.1)
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
        logger.info(f"✅ Sent to {sent} users | {job['completed']}/{job['total']}")
        
        if len(self.cache) > 100:
            self.cache.clear()
            
    # ========== MONITORING ==========
    
    async def monitor(self):
        logger.info("🔍 Monitoring started...")
        while True:
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
            await update.message.reply_text("❌ Unauthorized")
            return
            
        msg = f"""🚀 *MicroWorkers Bot*

📌 *Job:* Email Submit + Click + Reply + Screenshot
⏱ *Interval:* {CHECK_INTERVAL}s
🌐 *Web:* {RENDER_URL}

"""
        if self.data.is_owner(uid):
            msg += """👑 *Owner Commands*
/users - List users
/add [id] - Add user
/remove [id] - Remove user
/broadcast [msg] - Broadcast

"""
            
        msg += """📱 *Commands*
/status - Bot status
/test - Test notification
/help - Help"""
        
        await update.message.reply_text(msg, parse_mode='Markdown', disable_web_page_preview=True)
        
    async def status(self, update, context):
        uid = update.effective_user.id
        if not self.data.is_user(uid):
            return
            
        uptime = datetime.now() - self.start_time
        await update.message.reply_text(
            f"📊 *Status*\n\n"
            f"Uptime: {str(uptime).split('.')[0]}\n"
            f"Checks: {self.stats['checks']}\n"
            f"Notifications: {self.stats['notifications']}\n"
            f"Users: {len(self.data.get_all())}",
            parse_mode='Markdown'
        )
        
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
        await update.message.reply_text("✅ Test sent!")
        
    async def help(self, update, context):
        uid = update.effective_user.id
        if not self.data.is_user(uid):
            return
            
        await update.message.reply_text(
            f"📚 *Help*\n\n"
            f"Monitors: Email Submit + Click + Reply + Screenshot\n\n"
            f"Commands:\n"
            f"/start - Welcome\n"
            f"/status - Status\n"
            f"/test - Test\n"
            f"/help - Help\n\n"
            f"Web: {RENDER_URL}",
            parse_mode='Markdown'
        )
        
    # ========== OWNER COMMANDS ==========
    
    async def users(self, update, context):
        uid = update.effective_user.id
        if not self.data.is_owner(uid):
            return
            
        msg = "👥 *Users*\n\n"
        for u in self.data.get_all():
            msg += f"{'👑' if u == OWNER_ID else '👤'} `{u}`\n"
        msg += f"\nTotal: {len(self.data.get_all())}"
        await update.message.reply_text(msg, parse_mode='Markdown')
        
    async def add(self, update, context):
        uid = update.effective_user.id
        if not self.data.is_owner(uid):
            return
            
        try:
            new = int(context.args[0])
            if self.data.add(new):
                await update.message.reply_text(f"✅ Added `{new}`")
            else:
                await update.message.reply_text(f"⚠️ Already exists")
        except:
            await update.message.reply_text("❌ Usage: /add [user_id]")
            
    async def remove(self, update, context):
        uid = update.effective_user.id
        if not self.data.is_owner(uid):
            return
            
        try:
            rem = int(context.args[0])
            if self.data.remove(rem):
                await update.message.reply_text(f"✅ Removed `{rem}`")
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
        sent = await self.send_to_all(f"📢 *Broadcast*\n\n{msg}")
        await update.message.reply_text(f"✅ Sent to {sent} users")
        
    # ========== RUN ==========
    
    async def run(self):
        print("\n" + "="*50)
        print("🚀 MICROWORKERS BOT")
        print("="*50)
        print(f"👑 Owner: {OWNER_ID}")
        print(f"📊 Users: {len(self.data.get_all())}")
        print(f"🌐 URL: {RENDER_URL}")
        print("="*50 + "\n")
        
        # Send startup to owner
        try:
            bot = Bot(token=self.token)
            await bot.send_message(
                chat_id=OWNER_ID,
                text=f"✅ *Bot Started!*\n\n👑 Owner: `{OWNER_ID}`\n📊 Users: `{len(self.data.get_all())}`\n🌐 {RENDER_URL}",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        except:
            pass
            
        # Create app
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
        
        # Start bot - SIMPLE
        logger.info("✅ Bot is running!")
        await app.run_polling()

# ==================== WEB SERVER ====================

async def web_server():
    app = web.Application()
    
    async def home(request):
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>MicroWorkers Bot</title>
        <style>
            body {{ font-family: Arial; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; margin: 0; padding: 20px; display: flex; justify-content: center; align-items: center; color: white; }}
            .card {{ background: rgba(255,255,255,0.1); backdrop-filter: blur(10px); border-radius: 20px; padding: 40px; max-width: 600px; }}
            h1 {{ margin: 0; }}
            .status {{ background: #10b981; display: inline-block; padding: 8px 20px; border-radius: 50px; margin: 20px 0; }}
            code {{ background: rgba(0,0,0,0.3); padding: 3px 8px; border-radius: 5px; }}
            .links {{ margin-top: 30px; }}
            .links a {{ color: white; text-decoration: none; padding: 10px 20px; background: rgba(255,255,255,0.2); border-radius: 50px; margin: 0 10px; }}
        </style>
        </head>
        <body>
            <div class="card">
                <h1>🚀 MicroWorkers Bot</h1>
                <div class="status">✅ ONLINE</div>
                <p><strong>👑 Owner:</strong> <code>{OWNER_ID}</code></p>
                <p><strong>📌 Job:</strong> Email Submit + Click + Reply + Screenshot</p>
                <p><strong>⏱ Interval:</strong> {CHECK_INTERVAL}s</p>
                <p><strong>🌐 URL:</strong> <code>{RENDER_URL}</code></p>
                <div class="links">
                    <a href="/health">🔍 Health</a>
                    <a href="https://t.me/{(await get_bot_username())}">📱 Bot</a>
                </div>
            </div>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')
        
    async def health(request):
        return web.json_response({'status': 'ok'})
        
    async def get_bot_username():
        try:
            me = await Bot(token=TELEGRAM_TOKEN).get_me()
            return me.username
        except:
            return "your_bot"
            
    app.router.add_get('/', home)
    app.router.add_get('/health', health)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"🌐 Web: {RENDER_URL}")

# ==================== MAIN ====================

async def main():
    """Main function"""
    # Start web server
    await web_server()
    
    # Create and run bot
    bot = MicroWorkersBot()
    await bot.run()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Stopped")
    except Exception as e:
        logger.error(f"💥 Error: {e}")
