#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║      🔥 ULTIMATE TELEGRAM REPORT BOT v8.0 - ADMIN       ║
║  ⚡ Mass Report  🛡️ Anti-Ban  📊 Live Progress           ║
║  🎯 Saved Targets  💾 CSV Export  ⏰ Scheduler           ║
║  🏥 Health Monitor  🔄 Auto Proxy Rotation               ║
╚══════════════════════════════════════════════════════════╝
"""

import asyncio
import os
import json
import csv
import aiosqlite
import time
import random
import logging
from datetime import datetime, timedelta
from telethon import TelegramClient, events, Button, functions, types
from telethon.sessions import StringSession
from telethon.errors import (
    PhoneCodeInvalidError, SessionPasswordNeededError,
    FloodWaitError, UserBannedInChannelError,
    ChatAdminRequiredError, PeerFloodError,
    UserDeactivatedBanError, AuthKeyUnregisteredError
)

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler('bot.log'), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ── Report Categories ────────────────────────────────────
REPORT_CATEGORIES = {
    'spam': 2, 'scam': 4, 'porn': 5, 'violence': 5,
    'leak': 4, 'copyright': 2, 'harassment': 3,
    'illegal': 5, 'fake': 3, 'other': 1
}

CATEGORY_MAP = {
    '🚫 spam': 'spam', '💰 scam': 'scam', '🔞 porn': 'porn',
    '⚔️ violence': 'violence', '🔓 leak': 'leak', '©️ copyright': 'copyright',
    '😡 harassment': 'harassment', '⚖️ illegal': 'illegal',
    '🎭 fake': 'fake', '❓ other': 'other'
}

# ── Anti-Ban Delay Config ────────────────────────────────
SPEED_CONFIG = {
    'balanced': {'min': 2, 'max': 5, 'batch_pause': 10},
    'safe':     {'min': 5, 'max': 12, 'batch_pause': 20},
    'fast':     {'min': 0.5, 'max': 2, 'batch_pause': 5},
}


# ═══════════════════════════════════════════════════════════
#                     CORE BOT CLASS
# ═══════════════════════════════════════════════════════════

class UltraBot:
    def __init__(self):
        self.config_file  = 'config.json'
        self.proxy_file   = 'proxy.json'
        self.accounts_db  = 'accounts.db'
        self.reports_db   = 'reports.db'
        self.targets_db   = 'targets.db'

        self.config       = {}
        self.proxies      = {}
        self.active_clients    = {}
        self.pending_codes     = {}
        self.user_states       = {}
        self.authenticated_users = {}
        self.scheduled_tasks   = {}   # uid -> asyncio.Task
        self.proxy_index       = 0    # for round-robin proxy rotation
        self.bot_client        = None

        self.load_config()
        self.load_proxies()

    # ── Config ───────────────────────────────────────────

    def load_config(self):
        defaults = {
            "API_ID": "367859",
            "API_HASH": "bf8ce0c575b02e5ce444b0e7ea8",
            "BOT_TOKEN": "8641907928:AAEm-2QuuAX6hu_VqCjZjpbGwnhQhXO5Zq0",
            "ADMIN_IDS": [7302427268,8627378748],
            "ADMIN_PASSWORD": "none",
            "SESSION_TIMEOUT": 3600,
            "MAX_RETRIES": 5,
            "SPEED_MODE": "balanced",
            "MAX_CONCURRENT": 5
        }
        if not os.path.exists(self.config_file):
            with open(self.config_file, 'w') as f:
                json.dump(defaults, f, indent=4)
            print("❌ config.json created — fill it first!"); exit()

        with open(self.config_file, 'r') as f:
            self.config = json.load(f)

        if self.config.get('API_ID') == "ENTER_HERE":
            print("❌ Fill config.json first!"); exit()

    def load_proxies(self):
        if not os.path.exists(self.proxy_file):
            with open(self.proxy_file, 'w') as f:
                json.dump({"proxies": {}}, f, indent=4)
        else:
            with open(self.proxy_file, 'r') as f:
                self.proxies = json.load(f).get('proxies', {})

    def save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=4)

    # ── Database Init ─────────────────────────────────────

    async def init_db(self):
        async with aiosqlite.connect(self.accounts_db) as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                phone TEXT,
                session TEXT NOT NULL,
                proxy_name TEXT DEFAULT 'none',
                status TEXT DEFAULT 'active',
                health_score REAL DEFAULT 100.0,
                total_reports INTEGER DEFAULT 0,
                success_reports INTEGER DEFAULT 0,
                last_used DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_acc_status ON accounts(status)')
            await db.commit()

        async with aiosqlite.connect(self.reports_db) as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_name TEXT NOT NULL,
                target TEXT NOT NULL,
                target_type TEXT DEFAULT 'unknown',
                category TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                error_msg TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME
            )''')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_rep_status ON reports(status)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_rep_target ON reports(target)')
            await db.commit()

        async with aiosqlite.connect(self.targets_db) as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS saved_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT UNIQUE NOT NULL,
                target TEXT NOT NULL,
                category TEXT DEFAULT 'spam',
                note TEXT,
                report_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')
            await db.execute('''CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                label TEXT,
                target TEXT NOT NULL,
                category TEXT NOT NULL,
                accounts TEXT NOT NULL,
                interval_min INTEGER DEFAULT 60,
                runs INTEGER DEFAULT 0,
                max_runs INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                next_run DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')
            await db.commit()

    # ── Auth ──────────────────────────────────────────────

    def is_admin(self, uid):
        return uid in self.config.get('ADMIN_IDS', [])

    def is_authenticated(self, uid):
        ts = self.authenticated_users.get(uid)
        if ts:
            if time.time() - ts < self.config.get('SESSION_TIMEOUT', 3600):
                return True
            del self.authenticated_users[uid]
        return False

    def authenticate_user(self, uid):
        self.authenticated_users[uid] = time.time()

    # ── Proxy ─────────────────────────────────────────────

    def get_proxy_config(self, proxy_name):
        if not proxy_name or proxy_name == 'none':
            return None
        p = self.proxies.get(proxy_name)
        if not p:
            return None
        base = (p.get('type', 'socks5'), p['host'], p['port'])
        if 'username' in p:
            return base + (True, p['username'], p['password'])
        return base

    def next_proxy(self):
        """Round-robin proxy rotation"""
        keys = list(self.proxies.keys())
        if not keys:
            return None
        key = keys[self.proxy_index % len(keys)]
        self.proxy_index += 1
        return key

    # ── Client Management ─────────────────────────────────

    async def get_client(self, account_name):
        if account_name in self.active_clients:
            c = self.active_clients[account_name]
            if c.is_connected():
                return c
            del self.active_clients[account_name]

        async with aiosqlite.connect(self.accounts_db) as db:
            async with db.execute(
                'SELECT session, proxy_name FROM accounts WHERE name=? AND status="active"',
                (account_name,)
            ) as cur:
                row = await cur.fetchone()
        if not row:
            return None

        session, proxy_name = row
        proxy = self.get_proxy_config(proxy_name)
        try:
            client = TelegramClient(
                StringSession(session),
                int(self.config['API_ID']),
                self.config['API_HASH'],
                proxy=proxy,
                connection_retries=10,
                retry_delay=3,
                request_retries=5
            )
            await client.connect()
            if await client.is_user_authorized():
                self.active_clients[account_name] = client
                return client
            await client.disconnect()
        except Exception as e:
            log.error(f"get_client({account_name}): {e}")
        return None

    async def disconnect_all(self):
        for name, client in list(self.active_clients.items()):
            try:
                await client.disconnect()
            except:
                pass
        self.active_clients.clear()

    # ── Account Operations ────────────────────────────────

    async def add_account_from_session(self, name, session_str, phone=None, proxy_name=None):
        try:
            proxy = self.get_proxy_config(proxy_name)
            if proxy_name and proxy_name != 'none' and not proxy:
                return False, f"❌ Proxy '{proxy_name}' not found"

            client = TelegramClient(
                StringSession(session_str),
                int(self.config['API_ID']),
                self.config['API_HASH'],
                proxy=proxy,
                connection_retries=5
            )
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                return False, "❌ Session expired or invalid!"

            me = await client.get_me()
            async with aiosqlite.connect(self.accounts_db) as db:
                await db.execute(
                    'INSERT OR REPLACE INTO accounts (name,phone,session,proxy_name,status,health_score,last_used) VALUES(?,?,?,?,?,?,?)',
                    (name, me.phone or phone, session_str, proxy_name or 'none', 'active', 100.0, datetime.now())
                )
                await db.commit()
            await client.disconnect()
            return True, f"✅ **{name}** Added!\n👤 {me.first_name} | 📱 +{me.phone}"
        except Exception as e:
            return False, f"❌ {str(e)[:80]}"

    async def add_account_flow(self, name, phone, proxy_name=None):
        try:
            proxy = self.get_proxy_config(proxy_name)
            if proxy_name and proxy_name != 'none' and not proxy:
                return False, f"❌ Proxy '{proxy_name}' not found"

            # ✅ StringSession use karo taaki session.save() proper string de
            client = TelegramClient(
                StringSession(), int(self.config['API_ID']),
                self.config['API_HASH'], proxy=proxy,
                connection_retries=10, retry_delay=3
            )
            await client.connect()
            if await client.is_user_authorized():
                me = await client.get_me()
                session = client.session.save()
                async with aiosqlite.connect(self.accounts_db) as db:
                    await db.execute(
                        'INSERT OR REPLACE INTO accounts (name,phone,session,proxy_name,status,health_score,last_used) VALUES(?,?,?,?,?,?,?)',
                        (name, me.phone, session, proxy_name or 'none', 'active', 100.0, datetime.now())
                    )
                    await db.commit()
                await client.disconnect()
                return True, f"✅ {name} already authorized!\n👤 {me.first_name} | 📱 +{me.phone}"

            await client.send_code_request(phone)
            self.pending_codes[name] = {'client': client, 'phone': phone, 'proxy_name': proxy_name}
            return True, f"📱 Code sent to `{phone}`"
        except Exception as e:
            return False, f"❌ {str(e)[:80]}"

    async def verify_account_code(self, name, code, password=None):
        try:
            if name not in self.pending_codes:
                return False, "❌ No pending code — dobara ➕ Add Account try karo"
            data = self.pending_codes[name]
            client   = data['client']
            phone    = data['phone']
            proxy_name = data.get('proxy_name')

            try:
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                if not password:
                    return False, "🔐 2FA password chahiye!\nFormat: `OTP|password`\nExample: `12345|mypass123`"
                await client.sign_in(password=password)
            except PhoneCodeInvalidError:
                return False, "❌ OTP galat hai! Dobara check karo."
            except Exception as e:
                return False, f"❌ Sign in error: {str(e)[:60]}"

            me = await client.get_me()
            if not me:
                return False, "❌ Account info nahi mila!"

            # Session string save karo
            session = StringSession.save(client.session)
            if not session:
                return False, "❌ Session save nahi hua — dobara try karo"

            async with aiosqlite.connect(self.accounts_db) as db:
                await db.execute(
                    'INSERT OR REPLACE INTO accounts (name,phone,session,proxy_name,status,health_score,last_used) VALUES(?,?,?,?,?,?,?)',
                    (name, str(me.phone or ''), session, proxy_name or 'none', 'active', 100.0, datetime.now())
                )
                await db.commit()

            await client.disconnect()
            del self.pending_codes[name]
            return True, (
                f"✅ **Account Add Ho Gaya!**\n\n"
                f"👤 Naam: {me.first_name or ''} {me.last_name or ''}\n"
                f"📱 Phone: +{me.phone}\n"
                f"🆔 ID: {me.id}\n"
                f"🟢 Status: Active"
            )
        except Exception as e:
            return False, f"❌ Error: {str(e)[:80]}"

    async def delete_account(self, name):
        try:
            if name in self.active_clients:
                try: await self.active_clients[name].disconnect()
                except: pass
                del self.active_clients[name]
            async with aiosqlite.connect(self.accounts_db) as db:
                await db.execute('DELETE FROM accounts WHERE name=?', (name,))
                await db.commit()
            return True, f"🗑️ **{name}** deleted!"
        except Exception as e:
            return False, f"❌ {str(e)[:60]}"

    async def export_session(self, name):
        try:
            async with aiosqlite.connect(self.accounts_db) as db:
                async with db.execute('SELECT session FROM accounts WHERE name=?', (name,)) as cur:
                    row = await cur.fetchone()
            return (row[0], "✅") if row else (None, "❌ Not found")
        except Exception as e:
            return None, f"❌ {str(e)[:50]}"

    async def get_all_accounts(self, status=None):
        q = 'SELECT name,phone,proxy_name,status,health_score,total_reports,success_reports FROM accounts'
        if status:
            q += f' WHERE status="{status}"'
        q += ' ORDER BY last_used DESC'
        async with aiosqlite.connect(self.accounts_db) as db:
            async with db.execute(q) as cur:
                return await cur.fetchall()

    # ── Health Check ──────────────────────────────────────

    async def check_account_health(self, name):
        """Check if account is alive and update health score"""
        client = await self.get_client(name)
        if not client:
            async with aiosqlite.connect(self.accounts_db) as db:
                await db.execute('UPDATE accounts SET status="banned",health_score=0 WHERE name=?', (name,))
                await db.commit()
            return False, "🔴 BANNED/DEAD"
        try:
            me = await client.get_me()
            async with aiosqlite.connect(self.accounts_db) as db:
                await db.execute('UPDATE accounts SET status="active",health_score=100 WHERE name=?', (name,))
                await db.commit()
            return True, f"🟢 ACTIVE — {me.first_name}"
        except UserDeactivatedBanError:
            async with aiosqlite.connect(self.accounts_db) as db:
                await db.execute('UPDATE accounts SET status="banned",health_score=0 WHERE name=?', (name,))
                await db.commit()
            return False, "🔴 DEACTIVATED/BANNED"
        except Exception as e:
            return None, f"🟡 UNKNOWN — {str(e)[:40]}"

    async def health_check_all(self):
        accounts = await self.get_all_accounts()
        results = []
        for row in accounts:
            name = row[0]
            ok, msg = await self.check_account_health(name)
            results.append((name, ok, msg))
            await asyncio.sleep(1)
        return results

    # ── Target Info ───────────────────────────────────────

    async def get_target_info(self, target, account_name=None):
        """Fetch full info about a target using any available account"""
        if not account_name:
            accounts = await self.get_all_accounts('active')
            if not accounts:
                return None, "❌ No active accounts"
            account_name = accounts[0][0]

        client = await self.get_client(account_name)
        if not client:
            return None, "❌ Account offline"

        try:
            target_clean = target.strip().lstrip('@').lstrip('-')
            entity = await client.get_entity(target_clean)

            info = {'raw': entity}
            if hasattr(entity, 'bot') and entity.bot:
                info['type'] = '🤖 Bot'
            elif hasattr(entity, 'broadcast') and entity.broadcast:
                info['type'] = '📡 Channel'
            elif hasattr(entity, 'megagroup') and entity.megagroup:
                info['type'] = '👥 Supergroup'
            elif hasattr(entity, 'gigagroup') and entity.gigagroup:
                info['type'] = '🏟️ Broadcast Group'
            elif isinstance(entity, types.User):
                info['type'] = '👤 User'
            else:
                info['type'] = '❓ Unknown'

            # Basic fields
            info['id'] = entity.id
            info['username'] = f"@{entity.username}" if getattr(entity, 'username', None) else "None"
            info['first_name'] = getattr(entity, 'first_name', '') or ''
            info['last_name']  = getattr(entity, 'last_name', '') or ''
            info['title']      = getattr(entity, 'title', '') or ''
            info['phone']      = getattr(entity, 'phone', '') or 'Hidden'
            info['verified']   = '✅' if getattr(entity, 'verified', False) else '❌'
            info['restricted'] = '⚠️ YES' if getattr(entity, 'restricted', False) else 'No'
            info['scam']       = '🚨 YES' if getattr(entity, 'scam', False) else 'No'
            info['fake']       = '🎭 YES' if getattr(entity, 'fake', False) else 'No'

            # For channels/groups - get participant count
            if info['type'] in ('📡 Channel', '👥 Supergroup', '🏟️ Broadcast Group'):
                try:
                    full = await client(functions.channels.GetFullChannelRequest(channel=entity))
                    info['members'] = full.full_chat.participants_count
                    info['description'] = (full.full_chat.about or '')[:100]
                except:
                    info['members'] = '?'
                    info['description'] = ''

            return info, "✅"
        except Exception as e:
            return None, f"❌ {str(e)[:80]}"

    # ── Reporting Engine ──────────────────────────────────

    async def _smart_delay(self):
        """Anti-ban smart delay"""
        mode = self.config.get('SPEED_MODE', 'balanced')
        cfg  = SPEED_CONFIG.get(mode, SPEED_CONFIG['balanced'])
        delay = random.uniform(cfg['min'], cfg['max'])
        await asyncio.sleep(delay)

    def _get_report_reason(self, category):
        """Category ko real Telegram report reason mein convert karo"""
        from telethon.tl.types import (
            InputReportReasonSpam,
            InputReportReasonViolence,
            InputReportReasonPornography,
            InputReportReasonChildAbuse,
            InputReportReasonIllegalDrugs,
            InputReportReasonPersonalDetails,
            InputReportReasonOther,
            InputReportReasonCopyright,
            InputReportReasonFake,
        )
        reasons = {
            'spam':       InputReportReasonSpam(),
            'scam':       InputReportReasonSpam(),
            'porn':       InputReportReasonPornography(),
            'violence':   InputReportReasonViolence(),
            'leak':       InputReportReasonPersonalDetails(),
            'copyright':  InputReportReasonCopyright(),
            'harassment': InputReportReasonViolence(),
            'illegal':    InputReportReasonIllegalDrugs(),
            'fake':       InputReportReasonFake(),
            'other':      InputReportReasonOther(),
        }
        return reasons.get(category, InputReportReasonSpam())

    async def report_single(self, account_name, target, category='spam'):
        """Real Telegram report — ek account se"""
        from telethon.tl.functions.account import ReportPeerRequest
        from telethon.tl.functions.channels import ReportSpamRequest
        from telethon.tl.types import InputPeerUser, InputPeerChannel

        max_retries = self.config.get('MAX_RETRIES', 5)

        for attempt in range(1, max_retries + 1):
            try:
                client = await self.get_client(account_name)
                if not client:
                    return False, account_name, "Account offline"

                target_clean = target.strip().lstrip('@').lstrip('-')
                entity   = await client.get_entity(target_clean)
                e_type   = self._detect_type(entity)
                severity = REPORT_CATEGORIES.get(category, 1)
                reason   = self._get_report_reason(category)

                # ✅ REAL Telegram Report API
                await client(ReportPeerRequest(
                    peer=entity,
                    reason=reason,
                    message=f"Reporting for {category}"
                ))

                # DB log
                async with aiosqlite.connect(self.reports_db) as db:
                    await db.execute(
                        'INSERT INTO reports (account_name,target,target_type,category,status,completed_at) VALUES(?,?,?,?,?,?)',
                        (account_name, target_clean, e_type, category, 'sent', datetime.now())
                    )
                    await db.commit()

                # Account stats
                async with aiosqlite.connect(self.accounts_db) as db:
                    await db.execute(
                        'UPDATE accounts SET total_reports=total_reports+1, success_reports=success_reports+1, last_used=? WHERE name=?',
                        (datetime.now(), account_name)
                    )
                    await db.commit()

                await self._smart_delay()
                return True, account_name, f"Lv{severity} {e_type}"

            except FloodWaitError as e:
                wait = min(e.seconds + 2, 30)
                log.warning(f"{account_name} FloodWait {e.seconds}s")
                if attempt < max_retries:
                    await asyncio.sleep(wait)
                else:
                    return False, account_name, f"FloodWait {e.seconds}s"

            except (UserDeactivatedBanError, AuthKeyUnregisteredError):
                async with aiosqlite.connect(self.accounts_db) as db:
                    await db.execute('UPDATE accounts SET status="banned",health_score=0 WHERE name=?', (account_name,))
                    await db.commit()
                if account_name in self.active_clients:
                    del self.active_clients[account_name]
                return False, account_name, "BANNED"

            except PeerFloodError:
                async with aiosqlite.connect(self.accounts_db) as db:
                    await db.execute('UPDATE accounts SET health_score=MAX(0,health_score-20) WHERE name=?', (account_name,))
                    await db.commit()
                return False, account_name, "PeerFlood — cooling down"

            except Exception as e:
                if attempt < max_retries:
                    await asyncio.sleep(3)
                else:
                    # Log failure
                    async with aiosqlite.connect(self.reports_db) as db:
                        await db.execute(
                            'INSERT INTO reports (account_name,target,target_type,category,status,error_msg) VALUES(?,?,?,?,?,?)',
                            (account_name, target, 'unknown', category, 'failed', str(e)[:100])
                        )
                        await db.commit()
                    return False, account_name, str(e)[:60]

        return False, account_name, "Max retries exceeded"

    async def report_post(self, account_name, post_link, category='spam'):
        """Real Telegram post report — specific message report karo"""
        from telethon.tl.functions.messages import ReportRequest

        max_retries = self.config.get('MAX_RETRIES', 5)

        for attempt in range(1, max_retries + 1):
            try:
                channel, msg_id = self.parse_post_link(post_link)
                if not channel or not msg_id:
                    return False, account_name, "❌ Invalid link!"

                client = await self.get_client(account_name)
                if not client:
                    return False, account_name, "Account offline"

                entity   = await client.get_entity(channel)
                reason   = self._get_report_reason(category)
                severity = REPORT_CATEGORIES.get(category, 1)

                # ✅ REAL Telegram Message Report API
                await client(ReportRequest(
                    peer=entity,
                    id=[msg_id],
                    reason=reason,
                    message=f"Reporting post for {category}"
                ))

                # DB log
                async with aiosqlite.connect(self.reports_db) as db:
                    await db.execute(
                        'INSERT INTO reports (account_name,target,target_type,category,status,completed_at) VALUES(?,?,?,?,?,?)',
                        (account_name, post_link, 'post', category, 'sent', datetime.now())
                    )
                    await db.commit()

                # Account stats
                async with aiosqlite.connect(self.accounts_db) as db:
                    await db.execute(
                        'UPDATE accounts SET total_reports=total_reports+1, success_reports=success_reports+1, last_used=? WHERE name=?',
                        (datetime.now(), account_name)
                    )
                    await db.commit()

                await self._smart_delay()
                return True, account_name, f"✅ Post reported | Lv{severity}"

            except FloodWaitError as e:
                wait = min(e.seconds + 2, 30)
                if attempt < max_retries:
                    await asyncio.sleep(wait)
                else:
                    return False, account_name, f"FloodWait {e.seconds}s"

            except (UserDeactivatedBanError, AuthKeyUnregisteredError):
                async with aiosqlite.connect(self.accounts_db) as db:
                    await db.execute('UPDATE accounts SET status="banned",health_score=0 WHERE name=?', (account_name,))
                    await db.commit()
                return False, account_name, "BANNED"

            except PeerFloodError:
                async with aiosqlite.connect(self.accounts_db) as db:
                    await db.execute('UPDATE accounts SET health_score=MAX(0,health_score-20) WHERE name=?', (account_name,))
                    await db.commit()
                return False, account_name, "PeerFlood"

            except Exception as e:
                if attempt < max_retries:
                    await asyncio.sleep(3)
                else:
                    return False, account_name, str(e)[:60]

        return False, account_name, "Max retries exceeded"

    def _detect_type(self, entity):
        if hasattr(entity, 'bot') and entity.bot: return 'bot'
        if hasattr(entity, 'broadcast') and entity.broadcast: return 'channel'
        if hasattr(entity, 'megagroup') and entity.megagroup: return 'group'
        return 'user'

    async def mass_report(self, target, category, account_names=None, progress_cb=None):
        """
        Report target from ALL (or specified) accounts CONCURRENTLY.
        progress_cb(done, total, success, failed) called after each account.
        """
        if account_names is None:
            rows = await self.get_all_accounts('active')
            account_names = [r[0] for r in rows]

        if not account_names:
            return [], 0, 0

        max_concurrent = self.config.get('MAX_CONCURRENT', 5)
        semaphore = asyncio.Semaphore(max_concurrent)
        results   = []
        success   = 0
        failed    = 0
        done      = 0

        async def _report_one(acc):
            nonlocal success, failed, done
            async with semaphore:
                ok, name, msg = await self.report_single(acc, target, category)
                results.append((ok, name, msg))
                done += 1
                if ok: success += 1
                else:  failed  += 1
                if progress_cb:
                    await progress_cb(done, len(account_names), success, failed)

        await asyncio.gather(*[_report_one(a) for a in account_names])
        return results, success, failed

    # ── Saved Targets ─────────────────────────────────────

    async def save_target(self, label, target, category, note=''):
        async with aiosqlite.connect(self.targets_db) as db:
            try:
                await db.execute(
                    'INSERT INTO saved_targets (label,target,category,note) VALUES(?,?,?,?)',
                    (label, target, category, note)
                )
                await db.commit()
                return True, f"✅ Target `{label}` saved!"
            except:
                return False, "❌ Label already exists"

    async def get_saved_targets(self):
        async with aiosqlite.connect(self.targets_db) as db:
            async with db.execute('SELECT label,target,category,note,report_count FROM saved_targets ORDER BY report_count DESC') as cur:
                return await cur.fetchall()

    async def delete_saved_target(self, label):
        async with aiosqlite.connect(self.targets_db) as db:
            await db.execute('DELETE FROM saved_targets WHERE label=?', (label,))
            await db.commit()
        return True, f"🗑️ `{label}` deleted"

    async def update_target_count(self, target):
        async with aiosqlite.connect(self.targets_db) as db:
            await db.execute('UPDATE saved_targets SET report_count=report_count+1 WHERE target=?', (target,))
            await db.commit()

    def parse_post_link(self, link):
        """
        Parse post link aur channel + message_id nikalo
        Formats:
          https://t.me/channelname/123
          https://t.me/c/1234567890/123  (private channel)
          t.me/channelname/123
        """
        import re
        link = link.strip()

        # Private channel format: t.me/c/CHANNEL_ID/MSG_ID
        m = re.search(r't\.me/c/(\d+)/(\d+)', link)
        if m:
            channel_id = int('-100' + m.group(1))
            msg_id     = int(m.group(2))
            return channel_id, msg_id

        # Public channel format: t.me/username/MSG_ID
        m = re.search(r't\.me/([^/]+)/(\d+)', link)
        if m:
            channel = m.group(1)
            msg_id  = int(m.group(2))
            return channel, msg_id

        return None, None

    async def mass_report_post(self, post_link, category, account_names=None, progress_cb=None):
        """Saare accounts se ek post report karo"""
        if account_names is None:
            rows = await self.get_all_accounts('active')
            account_names = [r[0] for r in rows]

        if not account_names:
            return [], 0, 0

        max_concurrent = self.config.get('MAX_CONCURRENT', 5)
        semaphore = asyncio.Semaphore(max_concurrent)
        results   = []
        success   = 0
        failed    = 0
        done      = 0

        async def _one(acc):
            nonlocal success, failed, done
            async with semaphore:
                ok, name, msg = await self.report_post(acc, post_link, category)
                results.append((ok, name, msg))
                done += 1
                if ok: success += 1
                else:  failed  += 1
                if progress_cb:
                    await progress_cb(done, len(account_names), success, failed)

        await asyncio.gather(*[_one(a) for a in account_names])
        return results, success, failed

    # ── Join / Leave ──────────────────────────────────────

    async def join_group(self, account_name, target):
        """Account se group/channel join karo"""
        from telethon.tl.functions.channels import JoinChannelRequest
        from telethon.tl.functions.messages import ImportChatInviteRequest
        try:
            client = await self.get_client(account_name)
            if not client:
                return False, account_name, "Account offline"

            target = target.strip()

            # Invite link hai toh alag se handle karo
            if 'joinchat' in target or '+' in target:
                # Extract invite hash
                import re
                hash_match = re.search(r'(?:joinchat/|\+)([a-zA-Z0-9_-]+)', target)
                if hash_match:
                    invite_hash = hash_match.group(1)
                    await client(ImportChatInviteRequest(invite_hash))
                    await self._smart_delay()
                    return True, account_name, "✅ Joined via invite"
                return False, account_name, "❌ Invalid invite link"

            # Public username
            target_clean = target.lstrip('@')
            entity = await client.get_entity(target_clean)
            await client(JoinChannelRequest(entity))
            await self._smart_delay()
            return True, account_name, "✅ Joined"

        except FloodWaitError as e:
            return False, account_name, f"FloodWait {e.seconds}s"
        except (UserDeactivatedBanError, AuthKeyUnregisteredError):
            async with aiosqlite.connect(self.accounts_db) as db:
                await db.execute('UPDATE accounts SET status="banned",health_score=0 WHERE name=?', (account_name,))
                await db.commit()
            return False, account_name, "BANNED"
        except Exception as e:
            err = str(e)
            if 'already' in err.lower():
                return True, account_name, "✅ Already member"
            return False, account_name, str(e)[:50]

    async def leave_group(self, account_name, target):
        """Account se group/channel leave karo"""
        from telethon.tl.functions.channels import LeaveChannelRequest
        try:
            client = await self.get_client(account_name)
            if not client:
                return False, account_name, "Account offline"

            target_clean = target.strip().lstrip('@')
            entity = await client.get_entity(target_clean)
            await client(LeaveChannelRequest(entity))
            await self._smart_delay()
            return True, account_name, "✅ Left"

        except FloodWaitError as e:
            return False, account_name, f"FloodWait {e.seconds}s"
        except (UserDeactivatedBanError, AuthKeyUnregisteredError):
            async with aiosqlite.connect(self.accounts_db) as db:
                await db.execute('UPDATE accounts SET status="banned",health_score=0 WHERE name=?', (account_name,))
                await db.commit()
            return False, account_name, "BANNED"
        except Exception as e:
            return False, account_name, str(e)[:50]

    async def mass_join(self, target, account_names=None, progress_cb=None):
        """Saare accounts se group join karo"""
        if account_names is None:
            rows = await self.get_all_accounts('active')
            account_names = [r[0] for r in rows]
        if not account_names:
            return [], 0, 0

        max_concurrent = self.config.get('MAX_CONCURRENT', 3)  # Join ke liye slow rakho
        semaphore = asyncio.Semaphore(max_concurrent)
        results = []; success = 0; failed = 0; done = 0

        async def _one(acc):
            nonlocal success, failed, done
            async with semaphore:
                ok, name, msg = await self.join_group(acc, target)
                results.append((ok, name, msg))
                done += 1
                if ok: success += 1
                else:  failed  += 1
                if progress_cb:
                    await progress_cb(done, len(account_names), success, failed)

        await asyncio.gather(*[_one(a) for a in account_names])
        return results, success, failed

    async def mass_leave(self, target, account_names=None, progress_cb=None):
        """Saare accounts se group leave karo"""
        if account_names is None:
            rows = await self.get_all_accounts('active')
            account_names = [r[0] for r in rows]
        if not account_names:
            return [], 0, 0

        max_concurrent = self.config.get('MAX_CONCURRENT', 3)
        semaphore = asyncio.Semaphore(max_concurrent)
        results = []; success = 0; failed = 0; done = 0

        async def _one(acc):
            nonlocal success, failed, done
            async with semaphore:
                ok, name, msg = await self.leave_group(acc, target)
                results.append((ok, name, msg))
                done += 1
                if ok: success += 1
                else:  failed  += 1
                if progress_cb:
                    await progress_cb(done, len(account_names), success, failed)

        await asyncio.gather(*[_one(a) for a in account_names])
        return results, success, failed

    async def create_schedule(self, uid, label, target, category, account_names, interval_min, max_runs=0):
        accounts_str = ','.join(account_names)
        next_run = datetime.now() + timedelta(minutes=interval_min)
        async with aiosqlite.connect(self.targets_db) as db:
            await db.execute(
                'INSERT INTO schedules (user_id,label,target,category,accounts,interval_min,max_runs,next_run) VALUES(?,?,?,?,?,?,?,?)',
                (uid, label, target, category, accounts_str, interval_min, max_runs, next_run)
            )
            await db.commit()
            async with db.execute('SELECT last_insert_rowid()') as cur:
                sid = (await cur.fetchone())[0]
        return sid

    async def get_schedules(self, uid=None):
        q = 'SELECT id,label,target,category,interval_min,runs,max_runs,active,next_run FROM schedules'
        if uid:
            q += f' WHERE user_id={uid}'
        q += ' ORDER BY id DESC'
        async with aiosqlite.connect(self.targets_db) as db:
            async with db.execute(q) as cur:
                return await cur.fetchall()

    async def delete_schedule(self, sid):
        async with aiosqlite.connect(self.targets_db) as db:
            await db.execute('DELETE FROM schedules WHERE id=?', (sid,))
            await db.commit()

    async def run_scheduler(self):
        """Background task — runs pending schedules"""
        while True:
            try:
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                async with aiosqlite.connect(self.targets_db) as db:
                    async with db.execute(
                        'SELECT id,user_id,label,target,category,accounts,interval_min,runs,max_runs FROM schedules WHERE active=1 AND next_run <= ?',
                        (now,)
                    ) as cur:
                        due = await cur.fetchall()

                for row in due:
                    sid, uid, label, target, category, accounts_str, interval_min, runs, max_runs = row
                    accounts = [a.strip() for a in accounts_str.split(',') if a.strip()]
                    _, success, failed = await self.mass_report(target, category, accounts)

                    new_runs = runs + 1
                    next_run = datetime.now() + timedelta(minutes=interval_min)

                    async with aiosqlite.connect(self.targets_db) as db:
                        if max_runs > 0 and new_runs >= max_runs:
                            await db.execute('UPDATE schedules SET active=0,runs=? WHERE id=?', (new_runs, sid))
                            status_note = "🏁 Completed (max runs reached)"
                        else:
                            await db.execute('UPDATE schedules SET runs=?,next_run=? WHERE id=?', (new_runs, next_run, sid))
                            status_note = f"⏰ Next: {next_run.strftime('%H:%M')}"
                        await db.commit()

                    # Notify admin
                    if self.bot_client and uid:
                        try:
                            await self.bot_client.send_message(uid,
                                f"⏰ **SCHEDULE RUN** — `{label}`\n"
                                f"🎯 {target} | 📂 {category}\n"
                                f"✅ {success} sent | ❌ {failed} failed\n"
                                f"🔄 Run #{new_runs} | {status_note}"
                            )
                        except:
                            pass

            except Exception as e:
                log.error(f"Scheduler error: {e}")

            await asyncio.sleep(30)  # Check every 30 seconds

    # ── CSV Export ────────────────────────────────────────

    async def export_reports_csv(self, target_filter=None):
        q = 'SELECT account_name,target,target_type,category,status,timestamp,completed_at FROM reports'
        params = []
        if target_filter:
            q += ' WHERE target=?'
            params.append(target_filter.strip().lstrip('@'))
        q += ' ORDER BY timestamp DESC'

        async with aiosqlite.connect(self.reports_db) as db:
            async with db.execute(q, params) as cur:
                rows = await cur.fetchall()

        if not rows:
            return None, "❌ No reports found"

        filename = f"reports_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        os.makedirs('exports', exist_ok=True)
        path = f"exports/{filename}"
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['Account', 'Target', 'Type', 'Category', 'Status', 'Time', 'Completed'])
            w.writerows(rows)

        return path, f"✅ {len(rows)} records exported"

    # ── Auto Message ──────────────────────────────────────

    async def send_message(self, account_name, target, message):
        """Ek account se message bhejo"""
        from telethon.tl.functions.messages import SendMessageRequest
        try:
            client = await self.get_client(account_name)
            if not client:
                return False, account_name, "Account offline"

            target_clean = target.strip().lstrip('@')
            entity = await client.get_entity(target_clean)
            await client.send_message(entity, message)
            await self._smart_delay()
            return True, account_name, "✅ Message sent"
        except FloodWaitError as e:
            return False, account_name, f"FloodWait {e.seconds}s"
        except (UserDeactivatedBanError, AuthKeyUnregisteredError):
            async with aiosqlite.connect(self.accounts_db) as db:
                await db.execute('UPDATE accounts SET status="banned",health_score=0 WHERE name=?', (account_name,))
                await db.commit()
            return False, account_name, "BANNED"
        except Exception as e:
            return False, account_name, str(e)[:60]

    async def mass_message(self, target, message, account_names=None, progress_cb=None):
        """Saare accounts se message bhejo"""
        if account_names is None:
            rows = await self.get_all_accounts('active')
            account_names = [r[0] for r in rows]
        if not account_names:
            return [], 0, 0

        semaphore = asyncio.Semaphore(self.config.get('MAX_CONCURRENT', 3))
        results = []; success = 0; failed = 0; done = 0

        async def _one(acc):
            nonlocal success, failed, done
            async with semaphore:
                ok, name, msg = await self.send_message(acc, target, message)
                results.append((ok, name, msg))
                done += 1
                if ok: success += 1
                else:  failed += 1
                if progress_cb:
                    await progress_cb(done, len(account_names), success, failed)

        await asyncio.gather(*[_one(a) for a in account_names])
        return results, success, failed

    # ── Username Change ───────────────────────────────────

    async def change_username(self, account_name, new_username):
        """Account ka username change karo"""
        from telethon.tl.functions.account import UpdateUsernameRequest
        try:
            client = await self.get_client(account_name)
            if not client:
                return False, account_name, "Account offline"

            username = new_username.strip().lstrip('@')
            await client(UpdateUsernameRequest(username=username))
            return True, account_name, f"✅ Username: @{username}"
        except FloodWaitError as e:
            return False, account_name, f"FloodWait {e.seconds}s"
        except (UserDeactivatedBanError, AuthKeyUnregisteredError):
            async with aiosqlite.connect(self.accounts_db) as db:
                await db.execute('UPDATE accounts SET status="banned",health_score=0 WHERE name=?', (account_name,))
                await db.commit()
            return False, account_name, "BANNED"
        except Exception as e:
            return False, account_name, str(e)[:60]

    # ── Profile Changer ───────────────────────────────────

    async def change_profile(self, account_name, first_name=None, last_name=None, bio=None):
        """Account ki profile change karo"""
        from telethon.tl.functions.account import UpdateProfileRequest
        try:
            client = await self.get_client(account_name)
            if not client:
                return False, account_name, "Account offline"

            kwargs = {}
            if first_name is not None: kwargs['first_name'] = first_name
            if last_name  is not None: kwargs['last_name']  = last_name
            if bio        is not None: kwargs['about']       = bio

            await client(UpdateProfileRequest(**kwargs))
            return True, account_name, "✅ Profile updated"
        except Exception as e:
            return False, account_name, str(e)[:60]

    async def change_photo(self, account_name, photo_path):
        """Account ki profile photo change karo"""
        from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest
        from telethon.tl.functions.photos import GetUserPhotosRequest
        try:
            client = await self.get_client(account_name)
            if not client:
                return False, account_name, "Account offline"

            uploaded = await client.upload_file(photo_path)
            await client(UploadProfilePhotoRequest(file=uploaded))
            return True, account_name, "✅ Photo changed"
        except Exception as e:
            return False, account_name, str(e)[:60]

    # ── Mute / Unmute ─────────────────────────────────────

    async def mute_group(self, account_name, target, mute=True):
        """Group/Channel mute ya unmute karo"""
        from telethon.tl.functions.account import UpdateNotifySettingsRequest
        from telethon.tl.types import InputNotifyPeer, InputPeerNotifySettings
        try:
            client = await self.get_client(account_name)
            if not client:
                return False, account_name, "Account offline"

            target_clean = target.strip().lstrip('@')
            entity = await client.get_entity(target_clean)
            mute_until = 2147483647 if mute else 0  # Max int = forever mute

            await client(UpdateNotifySettingsRequest(
                peer=InputNotifyPeer(peer=entity),
                settings=InputPeerNotifySettings(
                    mute_until=mute_until,
                    show_previews=not mute
                )
            ))
            action = "🔇 Muted" if mute else "🔔 Unmuted"
            return True, account_name, f"✅ {action}"
        except Exception as e:
            return False, account_name, str(e)[:60]

    async def mass_mute(self, target, mute=True, account_names=None, progress_cb=None):
        """Saare accounts se group mute/unmute karo"""
        if account_names is None:
            rows = await self.get_all_accounts('active')
            account_names = [r[0] for r in rows]
        if not account_names:
            return [], 0, 0

        semaphore = asyncio.Semaphore(self.config.get('MAX_CONCURRENT', 5))
        results = []; success = 0; failed = 0; done = 0

        async def _one(acc):
            nonlocal success, failed, done
            async with semaphore:
                ok, name, msg = await self.mute_group(acc, target, mute)
                results.append((ok, name, msg))
                done += 1
                if ok: success += 1
                else:  failed += 1
                if progress_cb:
                    await progress_cb(done, len(account_names), success, failed)

        await asyncio.gather(*[_one(a) for a in account_names])
        return results, success, failed

    # ── Account Info ──────────────────────────────────────

    async def get_account_info(self, account_name):
        """Account ki puri details nikalo"""
        try:
            client = await self.get_client(account_name)
            if not client:
                return None, "Account offline"

            me = await client.get_me()
            if not me:
                return None, "Info nahi mili"

            # Total reports from DB
            async with aiosqlite.connect(self.reports_db) as db:
                async with db.execute('SELECT COUNT(*), SUM(CASE WHEN status="sent" THEN 1 ELSE 0 END) FROM reports WHERE account_name=?', (account_name,)) as c:
                    row = await c.fetchone()
                    total_rep = row[0] or 0
                    success_rep = row[1] or 0

            async with aiosqlite.connect(self.accounts_db) as db:
                async with db.execute('SELECT proxy_name, health_score, last_used, created_at FROM accounts WHERE name=?', (account_name,)) as c:
                    acc_row = await c.fetchone()

            proxy    = acc_row[0] if acc_row else 'none'
            health   = acc_row[1] if acc_row else 100
            last_use = acc_row[2] if acc_row else 'N/A'
            created  = acc_row[3] if acc_row else 'N/A'

            return {
                'name':        account_name,
                'first_name':  me.first_name or '',
                'last_name':   me.last_name or '',
                'username':    f"@{me.username}" if me.username else "None",
                'phone':       f"+{me.phone}" if me.phone else "Hidden",
                'id':          me.id,
                'bot':         '🤖 Yes' if me.bot else '👤 No',
                'verified':    '✅ Yes' if me.verified else '❌ No',
                'premium':     '💎 Yes' if getattr(me, 'premium', False) else '❌ No',
                'restricted':  '⚠️ Yes' if me.restricted else '✅ No',
                'proxy':       proxy,
                'health':      health,
                'total_rep':   total_rep,
                'success_rep': success_rep,
                'last_use':    str(last_use)[:16],
                'created':     str(created)[:16],
            }, "✅"
        except Exception as e:
            return None, str(e)[:60]

    # ── Flood Test ────────────────────────────────────────

    async def flood_test(self, account_name):
        """Account connection test karo — ping check"""
        import time as _time
        try:
            client = await self.get_client(account_name)
            if not client:
                return False, account_name, "❌ Offline / Cannot connect"

            start = _time.time()
            me    = await client.get_me()
            ping  = round((_time.time() - start) * 1000)

            # Check recent flood history
            async with aiosqlite.connect(self.reports_db) as db:
                async with db.execute(
                    'SELECT COUNT(*) FROM reports WHERE account_name=? AND timestamp > datetime("now", "-1 hour")',
                    (account_name,)
                ) as c:
                    recent = (await c.fetchone())[0]

            status = "🟢 Excellent" if ping < 300 else "🟡 Good" if ping < 800 else "🔴 Slow"
            risk   = "🟢 Low" if recent < 5 else "🟡 Medium" if recent < 15 else "🔴 High"

            return True, account_name, {
                'ping':    ping,
                'status':  status,
                'name':    me.first_name or account_name,
                'recent':  recent,
                'risk':    risk,
            }
        except FloodWaitError as e:
            return False, account_name, f"⏳ FloodWait {e.seconds}s"
        except (UserDeactivatedBanError, AuthKeyUnregisteredError):
            async with aiosqlite.connect(self.accounts_db) as db:
                await db.execute('UPDATE accounts SET status="banned",health_score=0 WHERE name=?', (account_name,))
                await db.commit()
            return False, account_name, "🔴 BANNED"
        except Exception as e:
            return False, account_name, f"❌ {str(e)[:50]}"

    # ── Live Report Counter ───────────────────────────────

    async def get_live_stats(self):
        """Real time report statistics"""
        async with aiosqlite.connect(self.reports_db) as db:
            # Last 1 hour
            async with db.execute(
                'SELECT COUNT(*), SUM(CASE WHEN status="sent" THEN 1 ELSE 0 END) FROM reports WHERE timestamp > datetime("now", "-1 hour")'
            ) as c:
                row = await c.fetchone()
                last_hour_total   = row[0] or 0
                last_hour_success = row[1] or 0

            # Last 24 hours
            async with db.execute(
                'SELECT COUNT(*), SUM(CASE WHEN status="sent" THEN 1 ELSE 0 END) FROM reports WHERE timestamp > datetime("now", "-24 hours")'
            ) as c:
                row = await c.fetchone()
                last_day_total   = row[0] or 0
                last_day_success = row[1] or 0

            # All time
            async with db.execute('SELECT COUNT(*), SUM(CASE WHEN status="sent" THEN 1 ELSE 0 END) FROM reports') as c:
                row = await c.fetchone()
                all_total   = row[0] or 0
                all_success = row[1] or 0

            # Last 5 reports
            async with db.execute(
                'SELECT account_name, target, category, status, timestamp FROM reports ORDER BY timestamp DESC LIMIT 5'
            ) as c:
                recent = await c.fetchall()

        return {
            'hour':   (last_hour_total,   last_hour_success),
            'day':    (last_day_total,    last_day_success),
            'all':    (all_total,         all_success),
            'recent': recent,
        }

    # ── Mass Vote ─────────────────────────────────────────

    async def vote_poll(self, account_name, poll_link, option_index=0):
        """Poll mein vote karo"""
        from telethon.tl.functions.messages import SendVoteRequest
        try:
            client = await self.get_client(account_name)
            if not client:
                return False, account_name, "Account offline"

            channel, msg_id = self.parse_post_link(poll_link)
            if not channel or not msg_id:
                return False, account_name, "❌ Invalid poll link"

            entity  = await client.get_entity(channel)
            message = await client.get_messages(entity, ids=msg_id)
            if not message or not message.media:
                return False, account_name, "❌ Poll nahi mili"

            poll    = message.media
            if not hasattr(poll, 'poll'):
                return False, account_name, "❌ Ye poll nahi hai"

            answers = poll.poll.answers
            if option_index >= len(answers):
                option_index = 0

            await client(SendVoteRequest(
                peer=entity,
                msg_id=msg_id,
                options=[answers[option_index].option]
            ))
            await self._smart_delay()
            return True, account_name, f"✅ Voted: {answers[option_index].text}"

        except FloodWaitError as e:
            return False, account_name, f"FloodWait {e.seconds}s"
        except (UserDeactivatedBanError, AuthKeyUnregisteredError):
            async with aiosqlite.connect(self.accounts_db) as db:
                await db.execute('UPDATE accounts SET status="banned",health_score=0 WHERE name=?', (account_name,))
                await db.commit()
            return False, account_name, "BANNED"
        except Exception as e:
            return False, account_name, str(e)[:60]

    async def mass_vote(self, poll_link, option_index=0, account_names=None, progress_cb=None):
        if account_names is None:
            rows = await self.get_all_accounts('active')
            account_names = [r[0] for r in rows]
        if not account_names:
            return [], 0, 0
        semaphore = asyncio.Semaphore(self.config.get('MAX_CONCURRENT', 3))
        results = []; success = 0; failed = 0; done = 0

        async def _one(acc):
            nonlocal success, failed, done
            async with semaphore:
                ok, name, msg = await self.vote_poll(acc, poll_link, option_index)
                results.append((ok, name, msg))
                done += 1
                if ok: success += 1
                else:  failed  += 1
                if progress_cb: await progress_cb(done, len(account_names), success, failed)

        await asyncio.gather(*[_one(a) for a in account_names])
        return results, success, failed

    # ── Mass Forward ──────────────────────────────────────

    async def forward_message(self, account_name, from_link, to_target):
        """Message forward karo"""
        try:
            client = await self.get_client(account_name)
            if not client:
                return False, account_name, "Account offline"

            channel, msg_id = self.parse_post_link(from_link)
            if not channel or not msg_id:
                return False, account_name, "❌ Invalid source link"

            from_entity = await client.get_entity(channel)
            to_entity   = await client.get_entity(to_target.strip().lstrip('@'))
            await client.forward_messages(to_entity, msg_id, from_entity)
            await self._smart_delay()
            return True, account_name, "✅ Forwarded"

        except FloodWaitError as e:
            return False, account_name, f"FloodWait {e.seconds}s"
        except (UserDeactivatedBanError, AuthKeyUnregisteredError):
            async with aiosqlite.connect(self.accounts_db) as db:
                await db.execute('UPDATE accounts SET status="banned",health_score=0 WHERE name=?', (account_name,))
                await db.commit()
            return False, account_name, "BANNED"
        except Exception as e:
            return False, account_name, str(e)[:60]

    async def mass_forward(self, from_link, to_target, account_names=None, progress_cb=None):
        if account_names is None:
            rows = await self.get_all_accounts('active')
            account_names = [r[0] for r in rows]
        if not account_names:
            return [], 0, 0
        semaphore = asyncio.Semaphore(self.config.get('MAX_CONCURRENT', 3))
        results = []; success = 0; failed = 0; done = 0

        async def _one(acc):
            nonlocal success, failed, done
            async with semaphore:
                ok, name, msg = await self.forward_message(acc, from_link, to_target)
                results.append((ok, name, msg))
                done += 1
                if ok: success += 1
                else:  failed  += 1
                if progress_cb: await progress_cb(done, len(account_names), success, failed)

        await asyncio.gather(*[_one(a) for a in account_names])
        return results, success, failed

    # ── Mass View ─────────────────────────────────────────

    async def view_post(self, account_name, post_link):
        """Channel post view karo (view count badhao)"""
        from telethon.tl.functions.messages import GetMessagesViewsRequest
        try:
            client = await self.get_client(account_name)
            if not client:
                return False, account_name, "Account offline"

            channel, msg_id = self.parse_post_link(post_link)
            if not channel or not msg_id:
                return False, account_name, "❌ Invalid link"

            entity = await client.get_entity(channel)
            await client(GetMessagesViewsRequest(
                peer=entity,
                id=[msg_id],
                increment=True
            ))
            await self._smart_delay()
            return True, account_name, "✅ View added"

        except FloodWaitError as e:
            return False, account_name, f"FloodWait {e.seconds}s"
        except (UserDeactivatedBanError, AuthKeyUnregisteredError):
            async with aiosqlite.connect(self.accounts_db) as db:
                await db.execute('UPDATE accounts SET status="banned",health_score=0 WHERE name=?', (account_name,))
                await db.commit()
            return False, account_name, "BANNED"
        except Exception as e:
            return False, account_name, str(e)[:60]

    async def mass_view(self, post_link, account_names=None, progress_cb=None):
        if account_names is None:
            rows = await self.get_all_accounts('active')
            account_names = [r[0] for r in rows]
        if not account_names:
            return [], 0, 0
        semaphore = asyncio.Semaphore(self.config.get('MAX_CONCURRENT', 5))
        results = []; success = 0; failed = 0; done = 0

        async def _one(acc):
            nonlocal success, failed, done
            async with semaphore:
                ok, name, msg = await self.view_post(acc, post_link)
                results.append((ok, name, msg))
                done += 1
                if ok: success += 1
                else:  failed  += 1
                if progress_cb: await progress_cb(done, len(account_names), success, failed)

        await asyncio.gather(*[_one(a) for a in account_names])
        return results, success, failed

    # ── Mass Block ────────────────────────────────────────

    async def block_user(self, account_name, target):
        """User ko block karo"""
        from telethon.tl.functions.contacts import BlockRequest
        try:
            client = await self.get_client(account_name)
            if not client:
                return False, account_name, "Account offline"

            entity = await client.get_entity(target.strip().lstrip('@'))
            await client(BlockRequest(id=entity))
            await self._smart_delay()
            return True, account_name, "✅ Blocked"

        except FloodWaitError as e:
            return False, account_name, f"FloodWait {e.seconds}s"
        except (UserDeactivatedBanError, AuthKeyUnregisteredError):
            async with aiosqlite.connect(self.accounts_db) as db:
                await db.execute('UPDATE accounts SET status="banned",health_score=0 WHERE name=?', (account_name,))
                await db.commit()
            return False, account_name, "BANNED"
        except Exception as e:
            return False, account_name, str(e)[:60]

    async def mass_block(self, target, account_names=None, progress_cb=None):
        if account_names is None:
            rows = await self.get_all_accounts('active')
            account_names = [r[0] for r in rows]
        if not account_names:
            return [], 0, 0
        semaphore = asyncio.Semaphore(self.config.get('MAX_CONCURRENT', 5))
        results = []; success = 0; failed = 0; done = 0

        async def _one(acc):
            nonlocal success, failed, done
            async with semaphore:
                ok, name, msg = await self.block_user(acc, target)
                results.append((ok, name, msg))
                done += 1
                if ok: success += 1
                else:  failed  += 1
                if progress_cb: await progress_cb(done, len(account_names), success, failed)

        await asyncio.gather(*[_one(a) for a in account_names])
        return results, success, failed

    # ── Mass Contact ──────────────────────────────────────

    async def add_contact(self, account_name, phone, first_name, last_name=''):
        """Contact add karo"""
        from telethon.tl.functions.contacts import ImportContactsRequest
        from telethon.tl.types import InputPhoneContact
        try:
            client = await self.get_client(account_name)
            if not client:
                return False, account_name, "Account offline"

            await client(ImportContactsRequest(contacts=[
                InputPhoneContact(
                    client_id=random.randint(0, 999999),
                    phone=phone,
                    first_name=first_name,
                    last_name=last_name
                )
            ]))
            await self._smart_delay()
            return True, account_name, f"✅ Contact added: {first_name}"

        except FloodWaitError as e:
            return False, account_name, f"FloodWait {e.seconds}s"
        except (UserDeactivatedBanError, AuthKeyUnregisteredError):
            async with aiosqlite.connect(self.accounts_db) as db:
                await db.execute('UPDATE accounts SET status="banned",health_score=0 WHERE name=?', (account_name,))
                await db.commit()
            return False, account_name, "BANNED"
        except Exception as e:
            return False, account_name, str(e)[:60]

    async def mass_add_contact(self, phone, first_name, last_name='', account_names=None, progress_cb=None):
        if account_names is None:
            rows = await self.get_all_accounts('active')
            account_names = [r[0] for r in rows]
        if not account_names:
            return [], 0, 0
        semaphore = asyncio.Semaphore(self.config.get('MAX_CONCURRENT', 3))
        results = []; success = 0; failed = 0; done = 0

        async def _one(acc):
            nonlocal success, failed, done
            async with semaphore:
                ok, name, msg = await self.add_contact(acc, phone, first_name, last_name)
                results.append((ok, name, msg))
                done += 1
                if ok: success += 1
                else:  failed  += 1
                if progress_cb: await progress_cb(done, len(account_names), success, failed)

        await asyncio.gather(*[_one(a) for a in account_names])
        return results, success, failed

    # ── Session Checker ───────────────────────────────────

    async def check_all_sessions(self):
        """Saare sessions check karo — expired dhundo"""
        accounts = await self.get_all_accounts()
        results  = []
        for row in accounts:
            name = row[0]
            try:
                client = await self.get_client(name)
                if not client:
                    status = "🔴 EXPIRED/BANNED"
                    async with aiosqlite.connect(self.accounts_db) as db:
                        await db.execute('UPDATE accounts SET status="banned",health_score=0 WHERE name=?', (name,))
                        await db.commit()
                else:
                    me     = await client.get_me()
                    status = f"🟢 ACTIVE — {me.first_name}"
                    async with aiosqlite.connect(self.accounts_db) as db:
                        await db.execute('UPDATE accounts SET status="active",health_score=100 WHERE name=?', (name,))
                        await db.commit()
            except Exception as e:
                status = f"🔴 ERROR — {str(e)[:30]}"
            results.append((name, status))
            await asyncio.sleep(0.5)
        return results

    # ── IP Checker ────────────────────────────────────────

    async def check_account_ip(self, account_name):
        """Account ka DC (Data Center) info nikalo"""
        try:
            client = await self.get_client(account_name)
            if not client:
                return None, "Account offline"

            me = await client.get_me()
            dc = client.session.dc_id

            DC_INFO = {
                1: "🇺🇸 USA (Miami)",
                2: "🇳🇱 Netherlands (Amsterdam)",
                3: "🇺🇸 USA (Miami)",
                4: "🇳🇱 Netherlands (Amsterdam)",
                5: "🇸🇬 Singapore",
            }
            dc_name = DC_INFO.get(dc, f"DC{dc}")
            return {
                'account': account_name,
                'name':    me.first_name or '',
                'dc':      dc,
                'location': dc_name,
                'phone':   f"+{me.phone}" if me.phone else "Hidden",
            }, "✅"
        except Exception as e:
            return None, str(e)[:60]

    # ── Auto Rejoin ───────────────────────────────────────

    async def start_auto_rejoin(self, target, account_names=None):
        """Banned accounts ko auto rejoin karo"""
        if account_names is None:
            rows = await self.get_all_accounts()
            account_names = [r[0] for r in rows]

        rejoined = []
        for acc in account_names:
            client = await self.get_client(acc)
            if not client:
                # Try to rejoin
                ok, _, msg = await self.join_group(acc, target)
                if ok:
                    rejoined.append(acc)
                    async with aiosqlite.connect(self.accounts_db) as db:
                        await db.execute('UPDATE accounts SET status="active",health_score=50 WHERE name=?', (acc,))
                        await db.commit()
            await asyncio.sleep(1)
        return rejoined

    # ── Spam Filter Bypass ────────────────────────────────

    def _bypass_text(self, message):
        """Smart text modification to bypass spam filters"""
        import unicodedata
        # Method 1: Zero width spaces add karo
        zwsp = '\u200b'
        result = zwsp.join(list(message))

        # Method 2: Similar looking unicode chars replace karo
        replacements = {
            'a': 'а', 'e': 'е', 'o': 'о', 'p': 'р',
            'c': 'с', 'x': 'х', 'A': 'А', 'E': 'Е',
            'O': 'О', 'B': 'В', 'H': 'Н', 'M': 'М',
        }
        # Only replace a few chars to keep readable
        count = 0
        result2 = ""
        for ch in message:
            if ch in replacements and count < 3:
                result2 += replacements[ch]
                count += 1
            else:
                result2 += ch

        return result2

    async def bypass_send(self, account_name, target, message):
        """Spam filter bypass karke message bhejo"""
        try:
            client = await self.get_client(account_name)
            if not client:
                return False, account_name, "Account offline"

            target_clean  = target.strip().lstrip('@')
            entity        = await client.get_entity(target_clean)
            bypass_msg    = self._bypass_text(message)
            await client.send_message(entity, bypass_msg)
            await self._smart_delay()
            return True, account_name, "✅ Sent (bypassed)"

        except FloodWaitError as e:
            return False, account_name, f"FloodWait {e.seconds}s"
        except (UserDeactivatedBanError, AuthKeyUnregisteredError):
            async with aiosqlite.connect(self.accounts_db) as db:
                await db.execute('UPDATE accounts SET status="banned",health_score=0 WHERE name=?', (account_name,))
                await db.commit()
            return False, account_name, "BANNED"
        except Exception as e:
            return False, account_name, str(e)[:60]

    async def mass_bypass_send(self, target, message, account_names=None, progress_cb=None):
        if account_names is None:
            rows = await self.get_all_accounts('active')
            account_names = [r[0] for r in rows]
        if not account_names:
            return [], 0, 0
        semaphore = asyncio.Semaphore(self.config.get('MAX_CONCURRENT', 3))
        results = []; success = 0; failed = 0; done = 0

        async def _one(acc):
            nonlocal success, failed, done
            async with semaphore:
                ok, name, msg = await self.bypass_send(acc, target, message)
                results.append((ok, name, msg))
                done += 1
                if ok: success += 1
                else:  failed  += 1
                if progress_cb: await progress_cb(done, len(account_names), success, failed)

        await asyncio.gather(*[_one(a) for a in account_names])
        return results, success, failed

    # ── Report Timer ──────────────────────────────────────

    async def get_report_timer_stats(self):
        """Report bhejne mein kitna time laga — average"""
        async with aiosqlite.connect(self.reports_db) as db:
            async with db.execute('''
                SELECT 
                    COUNT(*) as total,
                    AVG(CASE WHEN status="sent" THEN 1 ELSE 0 END) * 100 as success_rate,
                    MIN(timestamp) as first_report,
                    MAX(timestamp) as last_report,
                    COUNT(DISTINCT account_name) as accounts_used,
                    COUNT(DISTINCT target) as unique_targets
                FROM reports
            ''') as c:
                row = await c.fetchone()

            async with db.execute('''
                SELECT category, COUNT(*), 
                AVG(CASE WHEN status="sent" THEN 1.0 ELSE 0.0 END)*100
                FROM reports GROUP BY category ORDER BY 2 DESC
            ''') as c:
                by_cat = await c.fetchall()

        return {
            'total':    row[0] or 0,
            'rate':     row[1] or 0,
            'first':    str(row[2] or 'N/A')[:16],
            'last':     str(row[3] or 'N/A')[:16],
            'accounts': row[4] or 0,
            'targets':  row[5] or 0,
            'by_cat':   by_cat,
        }

    # ── Log Viewer ────────────────────────────────────────

    def get_logs(self, lines=30):
        """bot.log se last N lines nikalo"""
        try:
            if not os.path.exists('bot.log'):
                return "❌ Log file nahi mili"
            with open('bot.log', 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
            last = all_lines[-lines:] if len(all_lines) >= lines else all_lines
            return ''.join(last)
        except Exception as e:
            return f"❌ Log read error: {e}"

    # ── Stats ─────────────────────────────────────────────

    async def get_stats(self):
        async with aiosqlite.connect(self.reports_db) as db:
            async with db.execute('SELECT COUNT(*) FROM reports') as c:
                total = (await c.fetchone())[0]
            async with db.execute('SELECT COUNT(*) FROM reports WHERE status="sent"') as c:
                sent = (await c.fetchone())[0]
            async with db.execute(
                'SELECT account_name, COUNT(*), SUM(CASE WHEN status="sent" THEN 1 ELSE 0 END) FROM reports GROUP BY account_name ORDER BY 2 DESC LIMIT 8'
            ) as c:
                per_acc = await c.fetchall()
            async with db.execute(
                'SELECT target, COUNT(*) as cnt FROM reports GROUP BY target ORDER BY cnt DESC LIMIT 5'
            ) as c:
                top_targets = await c.fetchall()
            async with db.execute(
                'SELECT category, COUNT(*) FROM reports GROUP BY category ORDER BY 2 DESC'
            ) as c:
                by_category = await c.fetchall()

        async with aiosqlite.connect(self.accounts_db) as db:
            async with db.execute('SELECT COUNT(*) FROM accounts WHERE status="active"') as c:
                active_accs = (await c.fetchone())[0]
            async with db.execute('SELECT COUNT(*) FROM accounts WHERE status="banned"') as c:
                banned_accs = (await c.fetchone())[0]

        return {
            'total': total, 'sent': sent, 'failed': total - sent,
            'rate': (sent / total * 100) if total else 0,
            'per_account': per_acc, 'top_targets': top_targets,
            'by_category': by_category,
            'active_accounts': active_accs, 'banned_accounts': banned_accs
        }


# ═══════════════════════════════════════════════════════════
#                      BOT INSTANCE
# ═══════════════════════════════════════════════════════════

bot = UltraBot()


# ═══════════════════════════════════════════════════════════
#                      KEYBOARDS
# ═══════════════════════════════════════════════════════════

def kb_login():
    return [[Button.text("🔐 Login")]]

def kb_main():
    return [
        [Button.text("➕ Add Account"),      Button.text("📤 Import Session")],
        [Button.text("📦 ZIP Import"),       Button.text("📖 Read OTP")],
        [Button.text("📋 Accounts"),         Button.text("📥 Export Session")],
        [Button.text("🗑️ Delete Account"),   Button.text("🏥 Health Check")],
        [Button.text("🎯 Report"),           Button.text("💥 Mass Report")],
        [Button.text("📝 Post Report"),      Button.text("💥 Mass Post Report")],
        [Button.text("👥 Join Group"),       Button.text("🚪 Leave Group")],
        [Button.text("🔇 Mute Group"),       Button.text("🔔 Unmute Group")],
        [Button.text("📨 Auto Message"),     Button.text("💬 Bypass Message")],
        [Button.text("👤 Username Change"),  Button.text("🖼️ Profile Changer")],
        [Button.text("📱 Account Info"),     Button.text("🌐 IP Checker")],
        [Button.text("🗳️ Mass Vote"),        Button.text("📢 Mass Forward")],
        [Button.text("👁️ Mass View"),        Button.text("🔔 Mass Subscribe")],
        [Button.text("🚫 Mass Block"),       Button.text("📞 Mass Contact")],
        [Button.text("🔑 Session Checker"),  Button.text("🔄 Auto Rejoin")],
        [Button.text("⚡ Flood Test"),        Button.text("📊 Live Counter")],
        [Button.text("⏱️ Report Timer"),     Button.text("📋 Log Viewer")],
        [Button.text("🔥 Batch Targets"),    Button.text("⏰ Scheduler")],
        [Button.text("💾 Saved Targets"),    Button.text("🔍 Target Info")],
        [Button.text("📊 Statistics"),       Button.text("📤 Export CSV")],
        [Button.text("⚙️ Settings"),         Button.text("❌ Logout")],
    ]

def kb_category():
    return [
        [Button.text("🚫 spam"),  Button.text("💰 scam"),     Button.text("🔞 porn")],
        [Button.text("⚔️ violence"), Button.text("🔓 leak"), Button.text("©️ copyright")],
        [Button.text("😡 harassment"), Button.text("⚖️ illegal"), Button.text("🎭 fake")],
        [Button.text("❓ other"), Button.text("❌ Back")],
    ]

def kb_back():
    return [[Button.text("❌ Back")]]

def kb_proxy():
    keys = list(bot.proxies.keys()) if bot.proxies else []
    rows = [[Button.text(k)] for k in keys]
    rows.append([Button.text("🔄 Auto Rotate")])
    rows.append([Button.text("none")])
    rows.append([Button.text("❌ Back")])
    return rows

def kb_accounts(accounts):
    rows = [[Button.text(row[0])] for row in accounts]
    rows.append([Button.text("❌ Back")])
    return rows

def kb_settings():
    return [
        [Button.text("⚡ Speed: Fast"),    Button.text("🛡️ Speed: Safe")],
        [Button.text("⚖️ Speed: Balanced"), Button.text("🔢 Max Concurrent")],
        [Button.text("❌ Back")],
    ]


# ═══════════════════════════════════════════════════════════
#                     ACCESS GUARD
# ═══════════════════════════════════════════════════════════

MENU_BUTTONS = {
    '🔐 Login', '❌ Logout', '❌ Back', '➕ Add Account', '📤 Import Session',
    '📦 ZIP Import', '📖 Read OTP',
    '📥 Export Session', '📋 Accounts', '🌐 Proxies', '📊 Statistics',
    '👤 Report', '🎯 Report', '💥 Mass Report', '🔥 Batch Targets',
    '📝 Post Report', '💥 Mass Post Report',
    '👥 Join Group', '🚪 Leave Group',
    '🔇 Mute Group', '🔔 Unmute Group', '🔔 Mass Subscribe',
    '📨 Auto Message', '👤 Username Change',
    '🖼️ Profile Changer', '📱 Account Info',
    '⚡ Flood Test', '📊 Live Counter',
    '🗳️ Mass Vote', '📢 Mass Forward',
    '👁️ Mass View', '🚫 Mass Block',
    '📞 Mass Contact', '🔑 Session Checker',
    '🔄 Auto Rejoin', '💬 Bypass Message',
    '⏱️ Report Timer', '📋 Log Viewer',
    '🌐 IP Checker',
    '⏰ Scheduler', '💾 Saved Targets', '🔍 Target Info', '📤 Export CSV',
    '⚙️ Settings', '🏥 Health Check', '🗑️ Delete Account',
    '⚡ Speed: Fast', '🛡️ Speed: Safe', '⚖️ Speed: Balanced', '🔢 Max Concurrent',
    '✏️ Change Name/Bio', '🖼️ Change Photo',
    '/start'
}

async def guard(event):
    uid = event.sender_id
    if not bot.is_admin(uid):
        await event.reply("🚫 Admin only!")
        return False
    if not bot.is_authenticated(uid):
        await event.reply("❌ Login first!", buttons=kb_login())
        return False
    return True


# ═══════════════════════════════════════════════════════════
#                   EVENT HANDLERS
# ═══════════════════════════════════════════════════════════

@events.register(events.NewMessage(pattern=r'/start', incoming=True))
async def h_start(event):
    uid = event.sender_id
    if not bot.is_admin(uid):
        await event.reply("🚫 Admin only bot!"); return
    if bot.is_authenticated(uid):
        await event.reply(
            "🔥 **ULTRA REPORT BOT v8.0**\n\n"
            "⚡ Mass Report | 🛡️ Anti-Ban | 🎯 Smart Target\n"
            "💾 Saved Targets | ⏰ Scheduler | 📊 Live Stats",
            buttons=kb_main()
        )
    else:
        await event.reply("🔥 **ULTRA REPORT BOT v8.0**\n\n🔐 Authentication required.", buttons=kb_login())


@events.register(events.NewMessage(pattern=r'🔐 Login', incoming=True))
async def h_login(event):
    uid = event.sender_id
    if not bot.is_admin(uid):
        await event.reply("🚫 Admin only!"); return
    
    # Agar password none/empty hai toh seedha login
    pwd = bot.config.get('ADMIN_PASSWORD', '')
    if not pwd or pwd.lower() == 'none':
        bot.authenticate_user(uid)
        await event.reply("✅ **LOGIN SUCCESS** 🎉\n\nWelcome, Admin!", buttons=kb_main())
        return
    
    await event.reply("🔑 Enter admin password:", buttons=kb_back())
    bot.user_states[uid] = {'step': 'login_password'}


@events.register(events.NewMessage(pattern=r'❌ Logout', incoming=True))
async def h_logout(event):
    uid = event.sender_id
    bot.authenticated_users.pop(uid, None)
    bot.user_states.pop(uid, None)
    await event.reply("👋 Logged out!", buttons=kb_login())


@events.register(events.NewMessage(pattern=r'❌ Back', incoming=True))
async def h_back(event):
    uid = event.sender_id
    bot.user_states.pop(uid, None)
    await event.reply("🔙 Main menu", buttons=kb_main())


# ── Account Management ────────────────────────────────────

@events.register(events.NewMessage(pattern=r'➕ Add Account', incoming=True))
async def h_add(event):
    if not await guard(event): return
    await event.reply("📝 Account name:", buttons=kb_back())
    bot.user_states[event.sender_id] = {'step': 'add_name'}

@events.register(events.NewMessage(pattern=r'📤 Import Session', incoming=True))
async def h_import(event):
    if not await guard(event): return
    await event.reply("📝 Account name:", buttons=kb_back())
    bot.user_states[event.sender_id] = {'step': 'import_name'}

@events.register(events.NewMessage(pattern=r'📦 ZIP Import', incoming=True))
async def h_zip_import(event):
    if not await guard(event): return
    await event.reply(
        "📦 **ZIP Import**\n\n"
        "Tdata ya Session ka ZIP file bhejo.\n"
        "Bot automatically session extract karke add kar dega!\n\n"
        "⚠️ ZIP mein `.session` file ya Tdata folder hona chahiye.",
        buttons=kb_back()
    )
    bot.user_states[event.sender_id] = {'step': 'zip_name'}

@events.register(events.NewMessage(pattern=r'📖 Read OTP', incoming=True))
async def h_read_otp(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts:
        await event.reply("❌ Koi active account nahi hai!", buttons=kb_main())
        return
    await event.reply("📱 Konse account ka OTP padhna hai?", buttons=kb_accounts(accounts))
    bot.user_states[event.sender_id] = {'step': 'read_otp_select'}

@events.register(events.NewMessage(pattern=r'📥 Export Session', incoming=True))
async def h_export(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts()
    if not accounts: await event.reply("❌ No accounts!", buttons=kb_main()); return
    await event.reply("📥 Select account:", buttons=kb_accounts(accounts))
    bot.user_states[event.sender_id] = {'step': 'export_select'}

@events.register(events.NewMessage(pattern=r'🗑️ Delete Account', incoming=True))
async def h_delete_acc(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts()
    if not accounts: await event.reply("❌ No accounts!", buttons=kb_main()); return
    await event.reply("🗑️ Select account to DELETE:", buttons=kb_accounts(accounts))
    bot.user_states[event.sender_id] = {'step': 'delete_acc_select'}

@events.register(events.NewMessage(pattern=r'📋 Accounts', incoming=True))
async def h_list(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts()
    if not accounts: await event.reply("📱 No accounts!", buttons=kb_main()); return
    lines = [f"📱 **{len(accounts)} ACCOUNTS**\n"]
    for name, phone, proxy, status, health, total, success in accounts:
        em = '🟢' if status == 'active' else '🔴' if status == 'banned' else '🟡'
        rate = f"{(success/total*100):.0f}%" if total else "N/A"
        px = f" 🌐{proxy}" if proxy and proxy != 'none' else ""
        lines.append(f"{em} `{name}` — {phone or 'N/A'}{px}\n   📊 {total} reports | ✅ {rate} | 💚 {health:.0f}hp")
    await event.reply('\n'.join(lines), buttons=kb_main())

@events.register(events.NewMessage(pattern=r'🏥 Health Check', incoming=True))
async def h_health(event):
    if not await guard(event): return
    msg = await event.reply("🏥 Checking all accounts... please wait")
    results = await bot.health_check_all()
    if not results:
        await msg.edit("❌ No accounts to check!"); return
    lines = ["🏥 **HEALTH REPORT**\n"]
    for name, ok, status in results:
        lines.append(f"• `{name}` — {status}")
    await msg.edit('\n'.join(lines), buttons=kb_main())


# ── Reporting ─────────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'🎯 Report', incoming=True))
async def h_report(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    await event.reply("👤 Select account:", buttons=kb_accounts(accounts))
    bot.user_states[event.sender_id] = {'step': 'report_account'}

@events.register(events.NewMessage(pattern=r'💥 Mass Report', incoming=True))
async def h_mass(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    await event.reply(
        f"💥 **MASS REPORT**\n\n"
        f"Will use ALL {len(accounts)} active accounts simultaneously.\n\n"
        f"🎯 Enter target (@username or ID):",
        buttons=kb_back()
    )
    bot.user_states[event.sender_id] = {'step': 'mass_target', 'all_accounts': True}

@events.register(events.NewMessage(pattern=r'📝 Post Report', incoming=True))
async def h_post_report(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    await event.reply("👤 Account select karo:", buttons=kb_accounts(accounts))
    bot.user_states[event.sender_id] = {'step': 'post_report_account'}

@events.register(events.NewMessage(pattern=r'💥 Mass Post Report', incoming=True))
async def h_mass_post_report(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    await event.reply(
        f"💥 **MASS POST REPORT**\n\n"
        f"Saare {len(accounts)} accounts ek post ko report karenge!\n\n"
        f"📎 Post ka link daalo:\n"
        f"Format: `https://t.me/channelname/123`",
        buttons=kb_back()
    )
    bot.user_states[event.sender_id] = {'step': 'mass_post_link'}


@events.register(events.NewMessage(pattern=r'🔥 Batch Targets', incoming=True))
async def h_batch(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    await event.reply(
        "🔥 **BATCH TARGETS**\n\n"
        "Multiple targets ek saath report karo!\n"
        "Comma se alag karo:\n"
        "`@user1, @user2, @channel1`\n\n"
        "Saare active accounts har target ko report karenge!",
        buttons=kb_back()
    )
    bot.user_states[event.sender_id] = {'step': 'batch_targets_input'}


@events.register(events.NewMessage(pattern=r'👥 Join Group', incoming=True))
async def h_join_group(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    await event.reply(
        f"👥 **MASS JOIN**\n\n"
        f"Saare **{len(accounts)}** accounts join karenge!\n\n"
        f"Group/Channel daalo:\n"
        f"• Public: `@groupname`\n"
        f"• Private invite: `https://t.me/+AbCdEfGhIjK`",
        buttons=kb_back()
    )
    bot.user_states[event.sender_id] = {'step': 'join_target'}


@events.register(events.NewMessage(pattern=r'🚪 Leave Group', incoming=True))
async def h_leave_group(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    await event.reply(
        f"🚪 **MASS LEAVE**\n\n"
        f"Saare **{len(accounts)}** accounts leave karenge!\n\n"
        f"Group/Channel @username daalo:\n"
        f"• `@groupname`",
        buttons=kb_back()
    )
    bot.user_states[event.sender_id] = {'step': 'leave_target'}


# ── Mute / Unmute ─────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'🔇 Mute Group', incoming=True))
async def h_mute(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    await event.reply(
        f"🔇 **MASS MUTE**\n\n"
        f"Saare **{len(accounts)}** accounts mute karenge!\n\n"
        f"Group/Channel daalo: `@groupname`",
        buttons=kb_back()
    )
    bot.user_states[event.sender_id] = {'step': 'mute_target', 'mute': True}

@events.register(events.NewMessage(pattern=r'🔔 Unmute Group', incoming=True))
async def h_unmute(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    await event.reply(
        f"🔔 **MASS UNMUTE**\n\n"
        f"Saare **{len(accounts)}** accounts unmute karenge!\n\n"
        f"Group/Channel daalo: `@groupname`",
        buttons=kb_back()
    )
    bot.user_states[event.sender_id] = {'step': 'mute_target', 'mute': False}


# ── Auto Message ──────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'📨 Auto Message', incoming=True))
async def h_auto_msg(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    await event.reply(
        f"📨 **AUTO MESSAGE**\n\n"
        f"Saare **{len(accounts)}** accounts se message jaayega!\n\n"
        f"Target daalo (@username ya ID):",
        buttons=kb_back()
    )
    bot.user_states[event.sender_id] = {'step': 'msg_target'}


# ── Username Change ───────────────────────────────────────

@events.register(events.NewMessage(pattern=r'👤 Username Change', incoming=True))
async def h_username(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    await event.reply("👤 Account select karo:", buttons=kb_accounts(accounts))
    bot.user_states[event.sender_id] = {'step': 'username_account'}


# ── Profile Changer ───────────────────────────────────────

@events.register(events.NewMessage(pattern=r'🖼️ Profile Changer', incoming=True))
async def h_profile(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    kb = [
        [Button.text("✏️ Change Name/Bio")],
        [Button.text("🖼️ Change Photo")],
        [Button.text("❌ Back")],
    ]
    await event.reply(
        "🖼️ **PROFILE CHANGER**\n\nKya change karna hai?",
        buttons=kb
    )
    bot.user_states[event.sender_id] = {'step': 'profile_choice'}


# ── Account Info ──────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'📱 Account Info', incoming=True))
async def h_acc_info(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    await event.reply("📱 Account select karo:", buttons=kb_accounts(accounts))
    bot.user_states[event.sender_id] = {'step': 'acc_info_select'}


# ── Flood Test ────────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'⚡ Flood Test', incoming=True))
async def h_flood_test(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return

    msg_obj = await event.reply(f"⚡ Testing {len(accounts)} accounts...")
    lines   = ["⚡ **FLOOD TEST RESULTS**\n"]

    for row in accounts:
        name = row[0]
        ok, _, result = await bot.flood_test(name)
        if ok and isinstance(result, dict):
            lines.append(
                f"{result['status']} `{name}`\n"
                f"   🏓 Ping: {result['ping']}ms | "
                f"⚠️ Risk: {result['risk']} | "
                f"📊 Last hr: {result['recent']}"
            )
        else:
            lines.append(f"🔴 `{name}` — {result}")

    await msg_obj.edit('\n'.join(lines), buttons=kb_main())


# ── Live Counter ──────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'📊 Live Counter', incoming=True))
async def h_live_counter(event):
    if not await guard(event): return
    s = await bot.get_live_stats()
    h_total, h_ok = s['hour'];  d_total, d_ok = s['day'];  a_total, a_ok = s['all']

    recent_lines = []
    for acc, tgt, cat, status, ts in s['recent']:
        em = '✅' if status == 'sent' else '❌'
        recent_lines.append(f"  {em} `{acc}` → {tgt} [{cat}] {str(ts)[:16]}")

    text = (
        f"📊 **LIVE REPORT COUNTER**\n\n"
        f"⏱️ **Last 1 Hour:**\n"
        f"   Total: {h_total} | ✅ {h_ok} | ❌ {h_total - h_ok}\n\n"
        f"📅 **Last 24 Hours:**\n"
        f"   Total: {d_total} | ✅ {d_ok} | ❌ {d_total - d_ok}\n\n"
        f"🏆 **All Time:**\n"
        f"   Total: {a_total} | ✅ {a_ok} | ❌ {a_total - a_ok}\n"
        f"   Rate: {(a_ok/a_total*100):.1f}%" if a_total else "   Rate: N/A"
    )
    text += f"\n\n🕐 **Last 5 Reports:**\n" + ('\n'.join(recent_lines) if recent_lines else "  None yet")
    await event.reply(text, buttons=kb_main())


# ── Mass Vote ─────────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'🗳️ Mass Vote', incoming=True))
async def h_mass_vote(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    await event.reply(
        f"🗳️ **MASS VOTE**\n\n"
        f"Saare **{len(accounts)}** accounts vote karenge!\n\n"
        f"Poll ka link daalo:\n`https://t.me/channelname/123`",
        buttons=kb_back()
    )
    bot.user_states[event.sender_id] = {'step': 'vote_link'}


# ── Mass Forward ──────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'📢 Mass Forward', incoming=True))
async def h_mass_forward(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    await event.reply(
        f"📢 **MASS FORWARD**\n\n"
        f"Saare **{len(accounts)}** accounts forward karenge!\n\n"
        f"Source post link daalo:\n`https://t.me/channelname/123`",
        buttons=kb_back()
    )
    bot.user_states[event.sender_id] = {'step': 'forward_source'}


# ── Mass View ─────────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'👁️ Mass View', incoming=True))
async def h_mass_view(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    await event.reply(
        f"👁️ **MASS VIEW**\n\n"
        f"Saare **{len(accounts)}** accounts post view karenge!\n"
        f"_(View count badhega)_\n\n"
        f"Post link daalo:\n`https://t.me/channelname/123`",
        buttons=kb_back()
    )
    bot.user_states[event.sender_id] = {'step': 'view_link'}


# ── Mass Subscribe ────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'🔔 Mass Subscribe', incoming=True))
async def h_mass_subscribe(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    await event.reply(
        f"🔔 **MASS SUBSCRIBE**\n\n"
        f"Saare **{len(accounts)}** accounts subscribe karenge!\n"
        f"_(Same as Join — channel subscribe karo)_\n\n"
        f"Channel daalo: `@channelname`\n"
        f"ya invite link: `https://t.me/+xxxxx`",
        buttons=kb_back()
    )
    bot.user_states[event.sender_id] = {'step': 'subscribe_target'}


# ── Mass Block ────────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'🚫 Mass Block', incoming=True))
async def h_mass_block(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    await event.reply(
        f"🚫 **MASS BLOCK**\n\n"
        f"Saare **{len(accounts)}** accounts block karenge!\n\n"
        f"@username ya ID daalo:",
        buttons=kb_back()
    )
    bot.user_states[event.sender_id] = {'step': 'block_target'}


# ── Mass Contact ──────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'📞 Mass Contact', incoming=True))
async def h_mass_contact(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    await event.reply(
        f"📞 **MASS CONTACT ADD**\n\n"
        f"Saare **{len(accounts)}** accounts mein contact add hoga!\n\n"
        f"Daalo: `+91XXXXXXXXXX|FirstName|LastName`\n"
        f"Example: `+919876543210|Rahul|Singh`",
        buttons=kb_back()
    )
    bot.user_states[event.sender_id] = {'step': 'contact_input'}


# ── Session Checker ───────────────────────────────────────

@events.register(events.NewMessage(pattern=r'🔑 Session Checker', incoming=True))
async def h_session_check(event):
    if not await guard(event): return
    msg_obj = await event.reply("🔑 Saare sessions check kar raha hoon...")
    results = await bot.check_all_sessions()
    lines   = ["🔑 **SESSION CHECKER**\n"]
    active  = sum(1 for _, s in results if '🟢' in s)
    dead    = sum(1 for _, s in results if '🔴' in s)
    for name, status in results:
        lines.append(f"• `{name}` — {status}")
    lines.append(f"\n✅ Active: {active} | 🔴 Dead/Expired: {dead}")
    await msg_obj.edit('\n'.join(lines), buttons=kb_main())


# ── IP Checker ────────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'🌐 IP Checker', incoming=True))
async def h_ip_check(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    msg_obj = await event.reply("🌐 DC info nikaal raha hoon...")
    lines   = ["🌐 **IP / DC CHECKER**\n"]
    for row in accounts:
        name = row[0]
        info, status = await bot.check_account_ip(name)
        if info:
            lines.append(
                f"📱 `{name}`\n"
                f"   👤 {info['name']} | 📱 {info['phone']}\n"
                f"   🌍 DC{info['dc']} — {info['location']}"
            )
        else:
            lines.append(f"❌ `{name}` — {status}")
    await msg_obj.edit('\n'.join(lines), buttons=kb_main())


# ── Auto Rejoin ───────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'🔄 Auto Rejoin', incoming=True))
async def h_auto_rejoin(event):
    if not await guard(event): return
    await event.reply(
        "🔄 **AUTO REJOIN**\n\n"
        "Offline/banned accounts ko rejoin karaata hai!\n\n"
        "Group/Channel daalo: `@groupname`",
        buttons=kb_back()
    )
    bot.user_states[event.sender_id] = {'step': 'rejoin_target'}


# ── Bypass Message ────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'💬 Bypass Message', incoming=True))
async def h_bypass_msg(event):
    if not await guard(event): return
    accounts = await bot.get_all_accounts('active')
    if not accounts: await event.reply("❌ No active accounts!", buttons=kb_main()); return
    await event.reply(
        f"💬 **BYPASS MESSAGE**\n\n"
        f"Spam filter bypass karke message bhejta hai!\n"
        f"Saare **{len(accounts)}** accounts se jaayega.\n\n"
        f"Target daalo (@username ya ID):",
        buttons=kb_back()
    )
    bot.user_states[event.sender_id] = {'step': 'bypass_target'}


# ── Report Timer ──────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'⏱️ Report Timer', incoming=True))
async def h_report_timer(event):
    if not await guard(event): return
    s = await bot.get_report_timer_stats()
    cat_lines = '\n'.join(
        f"   {cat}: {cnt} (✅{rate:.0f}%)"
        for cat, cnt, rate in s['by_cat']
    ) if s['by_cat'] else "   None"

    text = (
        f"⏱️ **REPORT TIMER & STATS**\n\n"
        f"📊 Total Reports: **{s['total']}**\n"
        f"✅ Success Rate: **{s['rate']:.1f}%**\n"
        f"👥 Accounts Used: **{s['accounts']}**\n"
        f"🎯 Unique Targets: **{s['targets']}**\n"
        f"📅 First Report: `{s['first']}`\n"
        f"🕐 Last Report: `{s['last']}`\n\n"
        f"📂 **By Category:**\n{cat_lines}"
    )
    await event.reply(text, buttons=kb_main())


# ── Log Viewer ────────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'📋 Log Viewer', incoming=True))
async def h_log_viewer(event):
    if not await guard(event): return
    logs = bot.get_logs(30)
    if len(logs) > 3500:
        logs = "...(truncated)...\n" + logs[-3000:]
    await event.reply(
        f"📋 **BOT LOGS (Last 30 lines)**\n\n```\n{logs}\n```",
        buttons=kb_main()
    )


async def h_saved(event):
    if not await guard(event): return
    saved = await bot.get_saved_targets()
    lines = ["💾 **SAVED TARGETS**\n"]
    if saved:
        for label, target, cat, note, cnt in saved:
            lines.append(f"• `{label}` → {target} [{cat}] 🔁{cnt}")
            if note: lines.append(f"  📝 {note}")
    else:
        lines.append("No saved targets yet.")
    lines.append("\nOptions:")
    kb = [
        [Button.text("💾 Save New Target")],
        [Button.text("🚀 Report Saved Target")],
        [Button.text("🗑️ Delete Saved Target")],
        [Button.text("❌ Back")],
    ]
    await event.reply('\n'.join(lines), buttons=kb)

@events.register(events.NewMessage(pattern=r'💾 Save New Target', incoming=True))
async def h_save_new(event):
    if not await guard(event): return
    await event.reply("📝 Enter: `label|@target|category|optional note`\nExample: `spammer1|@bad_user|spam|Very annoying`", buttons=kb_back())
    bot.user_states[event.sender_id] = {'step': 'save_target_input'}

@events.register(events.NewMessage(pattern=r'🚀 Report Saved Target', incoming=True))
async def h_report_saved(event):
    if not await guard(event): return
    saved = await bot.get_saved_targets()
    if not saved: await event.reply("❌ No saved targets!", buttons=kb_main()); return
    kb = [[Button.text(row[0])] for row in saved]
    kb.append([Button.text("❌ Back")])
    await event.reply("🚀 Select saved target:", buttons=kb)
    bot.user_states[event.sender_id] = {'step': 'report_saved_select', 'saved_targets': {r[0]: r for r in saved}}

@events.register(events.NewMessage(pattern=r'🗑️ Delete Saved Target', incoming=True))
async def h_del_saved(event):
    if not await guard(event): return
    saved = await bot.get_saved_targets()
    if not saved: await event.reply("❌ No saved targets!", buttons=kb_main()); return
    kb = [[Button.text(row[0])] for row in saved]
    kb.append([Button.text("❌ Back")])
    await event.reply("🗑️ Select target to delete:", buttons=kb)
    bot.user_states[event.sender_id] = {'step': 'del_saved_select'}


# ── Target Info ───────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'🔍 Target Info', incoming=True))
async def h_info(event):
    if not await guard(event): return
    await event.reply("🔍 Enter @username or ID to lookup:", buttons=kb_back())
    bot.user_states[event.sender_id] = {'step': 'info_target'}


# ── Scheduler ─────────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'⏰ Scheduler', incoming=True))
async def h_scheduler(event):
    if not await guard(event): return
    uid = event.sender_id
    schedules = await bot.get_schedules(uid)
    lines = ["⏰ **SCHEDULER**\n"]
    if schedules:
        for sid, label, target, cat, interval, runs, max_runs, active, next_run in schedules:
            status = "🟢" if active else "⬛"
            max_str = f"/{max_runs}" if max_runs else "∞"
            lines.append(f"{status} [{sid}] `{label}` — {target}\n   📂{cat} | ⏱{interval}min | 🔁{runs}{max_str} | 🕐{next_run[:16]}")
    else:
        lines.append("No scheduled tasks yet.")

    kb = [
        [Button.text("➕ New Schedule")],
        [Button.text("🗑️ Delete Schedule")],
        [Button.text("❌ Back")],
    ]
    await event.reply('\n'.join(lines), buttons=kb)

@events.register(events.NewMessage(pattern=r'➕ New Schedule', incoming=True))
async def h_new_schedule(event):
    if not await guard(event): return
    await event.reply(
        "➕ **New Schedule**\n\nEnter details:\n"
        "`label|@target|category|interval_minutes|max_runs`\n\n"
        "Example: `daily_spam|@badchannel|spam|60|24`\n"
        "_(max_runs=0 means run forever)_",
        buttons=kb_back()
    )
    bot.user_states[event.sender_id] = {'step': 'new_schedule_input'}

@events.register(events.NewMessage(pattern=r'🗑️ Delete Schedule', incoming=True))
async def h_del_schedule(event):
    if not await guard(event): return
    uid = event.sender_id
    schedules = await bot.get_schedules(uid)
    if not schedules: await event.reply("❌ No schedules!", buttons=kb_main()); return
    kb = [[Button.text(f"[{s[0]}] {s[1]}")] for s in schedules]
    kb.append([Button.text("❌ Back")])
    await event.reply("🗑️ Select schedule to delete:", buttons=kb)
    bot.user_states[uid] = {'step': 'del_schedule_select'}


# ── Stats & Export ────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'📊 Statistics', incoming=True))
async def h_stats(event):
    if not await guard(event): return
    s = await bot.get_stats()
    rate = f"{s['rate']:.1f}%"

    cat_lines = ' | '.join(f"{cat}:{cnt}" for cat, cnt in s['by_category'])
    acc_lines = '\n'.join(
        f"  • `{a}`: {cnt} (✅{int(sc/cnt*100) if cnt else 0}%)"
        for a, cnt, sc in s['per_account']
    )
    tgt_lines = '\n'.join(f"  • `{t}`: {c}" for t, c in s['top_targets'])

    text = (
        f"📊 **STATISTICS**\n\n"
        f"📈 Total: **{s['total']}** | ✅ Sent: **{s['sent']}** | ❌ Failed: **{s['failed']}**\n"
        f"📊 Success Rate: **{rate}**\n"
        f"🟢 Active Accounts: **{s['active_accounts']}** | 🔴 Banned: **{s['banned_accounts']}**\n\n"
        f"📂 **By Category:** {cat_lines}\n\n"
        f"🏆 **Top Accounts:**\n{acc_lines or 'None'}\n\n"
        f"🎯 **Top Targets:**\n{tgt_lines or 'None'}"
    )
    await event.reply(text, buttons=kb_main())

@events.register(events.NewMessage(pattern=r'📤 Export CSV', incoming=True))
async def h_export_csv(event):
    if not await guard(event): return
    await event.reply("📤 Export all reports? Or enter @target to filter:", buttons=kb_back())
    bot.user_states[event.sender_id] = {'step': 'export_csv_filter'}


# ── Settings ──────────────────────────────────────────────

@events.register(events.NewMessage(pattern=r'⚙️ Settings', incoming=True))
async def h_settings(event):
    if not await guard(event): return
    mode  = bot.config.get('SPEED_MODE', 'balanced')
    conc  = bot.config.get('MAX_CONCURRENT', 5)
    text  = (
        f"⚙️ **SETTINGS**\n\n"
        f"⚡ Speed Mode: **{mode}**\n"
        f"🔢 Max Concurrent: **{conc}**\n\n"
        f"Choose:"
    )
    await event.reply(text, buttons=kb_settings())

@events.register(events.NewMessage(pattern=r'⚡ Speed: Fast', incoming=True))
async def h_speed_fast(event):
    if not await guard(event): return
    bot.config['SPEED_MODE'] = 'fast'; bot.save_config()
    await event.reply("⚡ Speed set to **FAST** (flood risk!)", buttons=kb_main())

@events.register(events.NewMessage(pattern=r'🛡️ Speed: Safe', incoming=True))
async def h_speed_safe(event):
    if not await guard(event): return
    bot.config['SPEED_MODE'] = 'safe'; bot.save_config()
    await event.reply("🛡️ Speed set to **SAFE** (anti-ban mode)", buttons=kb_main())

@events.register(events.NewMessage(pattern=r'⚖️ Speed: Balanced', incoming=True))
async def h_speed_bal(event):
    if not await guard(event): return
    bot.config['SPEED_MODE'] = 'balanced'; bot.save_config()
    await event.reply("⚖️ Speed set to **BALANCED**", buttons=kb_main())

@events.register(events.NewMessage(pattern=r'🔢 Max Concurrent', incoming=True))
async def h_max_conc(event):
    if not await guard(event): return
    await event.reply("🔢 Enter max concurrent accounts (1-20):", buttons=kb_back())
    bot.user_states[event.sender_id] = {'step': 'set_max_concurrent'}


# ═══════════════════════════════════════════════════════════
#                   MAIN TEXT HANDLER
# ═══════════════════════════════════════════════════════════

@events.register(events.NewMessage(incoming=True))
async def h_text(event):
    uid  = event.sender_id
    text = event.text.strip()

    if text in MENU_BUTTONS: return
    if uid not in bot.user_states: return

    state = bot.user_states[uid]
    step  = state['step']

    # ── LOGIN ─────────────────────────────────────────────
    if step == 'login_password':
        if text == bot.config.get('ADMIN_PASSWORD'):
            bot.authenticate_user(uid)
            await event.reply("✅ **LOGIN SUCCESS** 🎉\n\nWelcome, Admin!", buttons=kb_main())
        else:
            await event.reply("❌ Wrong password!", buttons=kb_login())
        del bot.user_states[uid]; return

    if not bot.is_authenticated(uid):
        await event.reply("❌ Login first!", buttons=kb_login())
        bot.user_states.pop(uid, None); return

    # ── ADD ACCOUNT (Phone se) ────────────────────────────
    if step == 'add_name':
        # Validate name
        if not text or len(text) < 1:
            await event.reply("❌ Sahi naam daalo!", buttons=kb_back()); return
        state['name'] = text
        state['step'] = 'add_phone'
        await event.reply(
            f"✅ Account naam: **{text}**\n\n📱 Phone number daalo:\nFormat: `+91XXXXXXXXXX`",
            buttons=kb_back()
        )

    elif step == 'add_phone':
        phone = text.strip()
        # Auto add + if missing
        if not phone.startswith('+'):
            phone = '+' + phone
        state['phone'] = phone
        state['step'] = 'add_sending'
        msg_obj = await event.reply(f"📤 `{phone}` pe OTP bhej raha hoon...")
        ok, msg = await bot.add_account_flow(state['name'], phone, None)
        if ok and "Code sent" in msg:
            state['step'] = 'add_verify'
            await msg_obj.edit(
                f"✅ OTP bheja gaya `{phone}` pe!\n\n"
                f"📩 **Telegram ka OTP daalo:**\n"
                f"_(2FA hai toh: `12345|password` format mein)_",
                buttons=kb_back()
            )
        else:
            await msg_obj.edit(f"❌ Error: {msg}", buttons=kb_main())
            del bot.user_states[uid]

    elif step == 'add_verify':
        parts = text.strip().split('|', 1)
        code     = parts[0].strip()
        password = parts[1].strip() if len(parts) > 1 else None
        msg_obj  = await event.reply("⏳ Verify kar raha hoon...")
        ok, msg  = await bot.verify_account_code(state['name'], code, password)
        await msg_obj.edit(msg, buttons=kb_main())
        del bot.user_states[uid]

    # ── IMPORT SESSION ────────────────────────────────────

    elif step == 'import_name':
        if not text:
            await event.reply("❌ Naam daalo!", buttons=kb_back()); return
        state['name'] = text
        state['step'] = 'import_session'
        await event.reply(
            f"✅ Account naam: **{text}**\n\n"
            f"📋 **Session string paste karo:**\n"
            f"_(Bahut lambi string hoti hai jo `1AgAB...` se shuru hoti hai)_",
            buttons=kb_back()
        )

    elif step == 'import_session':
        session_str = text.strip()
        if len(session_str) < 50:
            await event.reply(
                "❌ **Invalid session string!**\n\n"
                "Session string bahut lambi hoti hai.\n"
                "Sahi string paste karo.",
                buttons=kb_back()
            ); return
        msg_obj = await event.reply("⏳ Session verify kar raha hoon...")
        ok, msg = await bot.add_account_from_session(state['name'], session_str, None, None)
        await msg_obj.edit(msg, buttons=kb_main())
        del bot.user_states[uid]

    # ── ZIP IMPORT ────────────────────────────────────────
    elif step == 'zip_name':
        if not text:
            await event.reply("❌ Naam daalo!", buttons=kb_back()); return
        state['name'] = text
        state['step'] = 'zip_wait'
        await event.reply(
            f"✅ Account naam: **{text}**\n\n"
            f"📦 Ab ZIP file bhejo!",
            buttons=kb_back()
        )

    # ── READ OTP ──────────────────────────────────────────
    elif step == 'read_otp_select':
        acc_name = text.strip()
        msg_obj  = await event.reply("⏳ OTP dhundh raha hoon...")
        try:
            client = await bot.get_client(acc_name)
            if not client:
                await msg_obj.edit("❌ Account connect nahi hua!", buttons=kb_main())
                del bot.user_states[uid]
                return

            import re as _re
            otp_found = []
            async for message in client.iter_messages('777000', limit=10):
                if message.text:
                    codes = _re.findall(r'\b\d{5,6}\b', message.text)
                    if codes:
                        otp_found.append({
                            'code': codes[0],
                            'text': message.text[:200],
                            'date': message.date.strftime('%Y-%m-%d %H:%M:%S')
                        })

            if otp_found:
                lines = [f"📖 **OTP Results — {acc_name}**\n"]
                for i, item in enumerate(otp_found[:5], 1):
                    lines.append(
                        f"**{i}.** 🔑 Code: `{item['code']}`\n"
                        f"   📅 {item['date']}\n"
                        f"   💬 _{item['text'][:100]}_\n"
                    )
                await msg_obj.edit('\n'.join(lines), buttons=kb_main())
            else:
                await msg_obj.edit(
                    f"⚠️ **{acc_name}** ke inbox mein koi OTP nahi mila!\n"
                    f"(777000 se last 10 messages check kiye)",
                    buttons=kb_main()
                )
        except Exception as e:
            await msg_obj.edit(f"❌ Error: {str(e)[:100]}", buttons=kb_main())
        del bot.user_states[uid]

    # ── EXPORT SESSION ────────────────────────────────────
    elif step == 'export_select':
        acc_name = text.strip()
        msg_obj  = await event.reply("⏳ Session nikaal raha hoon...")
        session, msg = await bot.export_session(acc_name)
        if session:
            # Session string bahut lambi hoti hai - 2 parts mein bhejo
            await msg_obj.edit(
                f"📥 **SESSION EXPORT**\n\n"
                f"🏷️ Account: `{acc_name}`\n"
                f"📊 Status: Active\n\n"
                f"⚠️ Neeche session string hai — copy karke safe rakhlo:",
                buttons=kb_main()
            )
            # Session string alag message mein bhejo taaki copy karna aasaan ho
            await event.respond(f"`{session}`")
        else:
            await msg_obj.edit(f"❌ {msg}", buttons=kb_main())
        del bot.user_states[uid]

    # ── JOIN GROUP ────────────────────────────────────────
    elif step == 'join_target':
        target   = text.strip()
        accounts = await bot.get_all_accounts('active')
        total    = len(accounts)
        msg_obj  = await event.reply(
            f"👥 **MASS JOIN SHURU**\n\n"
            f"🎯 {target}\n"
            f"👥 {total} accounts\n\n"
            f"⏳ 0/{total} done..."
        )
        last_edit = [time.time()]

        async def join_progress(done, total, success, failed):
            if time.time() - last_edit[0] > 2:
                bar = '█' * int(done/total*10) + '░' * (10 - int(done/total*10))
                try:
                    await msg_obj.edit(
                        f"👥 **MASS JOIN**\n\n"
                        f"🎯 {target}\n"
                        f"[{bar}] {done}/{total}\n"
                        f"✅ {success} | ❌ {failed}"
                    )
                    last_edit[0] = time.time()
                except: pass

        results, success, failed = await bot.mass_join(target, progress_cb=join_progress)
        failed_accs = [name for ok, name, _ in results if not ok]
        fail_text   = f"\n❌ Failed: {', '.join(failed_accs[:5])}" if failed_accs else ""

        await msg_obj.edit(
            f"👥 **MASS JOIN COMPLETE**\n\n"
            f"🎯 {target}\n"
            f"✅ Joined: {success}/{total}\n"
            f"❌ Failed: {failed}{fail_text}",
            buttons=kb_main()
        )
        del bot.user_states[uid]

    # ── LEAVE GROUP ───────────────────────────────────────
    elif step == 'leave_target':
        target   = text.strip()
        accounts = await bot.get_all_accounts('active')
        total    = len(accounts)
        msg_obj  = await event.reply(
            f"🚪 **MASS LEAVE SHURU**\n\n"
            f"🎯 {target}\n"
            f"👥 {total} accounts\n\n"
            f"⏳ 0/{total} done..."
        )
        last_edit = [time.time()]

        async def leave_progress(done, total, success, failed):
            if time.time() - last_edit[0] > 2:
                bar = '█' * int(done/total*10) + '░' * (10 - int(done/total*10))
                try:
                    await msg_obj.edit(
                        f"🚪 **MASS LEAVE**\n\n"
                        f"🎯 {target}\n"
                        f"[{bar}] {done}/{total}\n"
                        f"✅ {success} | ❌ {failed}"
                    )
                    last_edit[0] = time.time()
                except: pass

        results, success, failed = await bot.mass_leave(target, progress_cb=leave_progress)
        failed_accs = [name for ok, name, _ in results if not ok]
        fail_text   = f"\n❌ Failed: {', '.join(failed_accs[:5])}" if failed_accs else ""

        await msg_obj.edit(
            f"🚪 **MASS LEAVE COMPLETE**\n\n"
            f"🎯 {target}\n"
            f"✅ Left: {success}/{total}\n"
            f"❌ Failed: {failed}{fail_text}",
            buttons=kb_main()
        )
        del bot.user_states[uid]

    # ── DELETE ACCOUNT ────────────────────────────────────
    elif step == 'delete_acc_select':
        ok, msg = await bot.delete_account(text)
        await event.reply(msg, buttons=kb_main()); del bot.user_states[uid]

    # ── MUTE / UNMUTE ─────────────────────────────────────
    elif step == 'mute_target':
        target    = text.strip()
        do_mute   = state.get('mute', True)
        action    = "🔇 MUTE" if do_mute else "🔔 UNMUTE"
        accounts  = await bot.get_all_accounts('active')
        total     = len(accounts)
        msg_obj   = await event.reply(f"{action} — {target}\n⏳ {total} accounts...")
        last_edit = [time.time()]

        async def mute_progress(done, total, success, failed):
            if time.time() - last_edit[0] > 2:
                bar = '█' * int(done/total*10) + '░' * (10 - int(done/total*10))
                try:
                    await msg_obj.edit(f"{action}\n🎯 {target}\n[{bar}] {done}/{total}\n✅{success} ❌{failed}")
                    last_edit[0] = time.time()
                except: pass

        results, success, failed = await bot.mass_mute(target, mute=do_mute, progress_cb=mute_progress)
        await msg_obj.edit(
            f"{'🔇' if do_mute else '🔔'} **{'MUTED' if do_mute else 'UNMUTED'} COMPLETE**\n\n"
            f"🎯 {target}\n✅ {success}/{total} | ❌ {failed}",
            buttons=kb_main()
        )
        del bot.user_states[uid]

    # ── AUTO MESSAGE ──────────────────────────────────────
    elif step == 'msg_target':
        state['target'] = text
        state['step']   = 'msg_text'
        await event.reply(
            f"✅ Target: `{text}`\n\n"
            f"📝 Bhejne wala message likho:",
            buttons=kb_back()
        )

    elif step == 'msg_text':
        message  = text
        target   = state['target']
        accounts = await bot.get_all_accounts('active')
        total    = len(accounts)
        msg_obj  = await event.reply(f"📨 Message bhej raha hoon {total} accounts se...")
        last_edit = [time.time()]

        async def msg_progress(done, total, success, failed):
            if time.time() - last_edit[0] > 2:
                bar = '█' * int(done/total*10) + '░' * (10 - int(done/total*10))
                try:
                    await msg_obj.edit(f"📨 **AUTO MESSAGE**\n🎯 {target}\n[{bar}] {done}/{total}\n✅{success} ❌{failed}")
                    last_edit[0] = time.time()
                except: pass

        results, success, failed = await bot.mass_message(target, message, progress_cb=msg_progress)
        await msg_obj.edit(
            f"📨 **MESSAGE SENT**\n\n"
            f"🎯 {target}\n"
            f"✅ Sent: {success}/{total}\n"
            f"❌ Failed: {failed}",
            buttons=kb_main()
        )
        del bot.user_states[uid]

    # ── USERNAME CHANGE ───────────────────────────────────
    elif step == 'username_account':
        state['account'] = text
        state['step']    = 'username_new'
        await event.reply(
            f"✅ Account: **{text}**\n\n"
            f"👤 Naya username daalo:\n"
            f"_(bina @ ke, sirf letters/numbers/underscore)_",
            buttons=kb_back()
        )

    elif step == 'username_new':
        msg_obj = await event.reply("⏳ Username change kar raha hoon...")
        ok, _, result = await bot.change_username(state['account'], text)
        await msg_obj.edit(
            f"{'✅' if ok else '❌'} **Username Change**\n\n"
            f"🏷️ Account: `{state['account']}`\n"
            f"💬 {result}",
            buttons=kb_main()
        )
        del bot.user_states[uid]

    # ── PROFILE CHANGER ───────────────────────────────────
    elif step == 'profile_choice':
        if text == '✏️ Change Name/Bio':
            accounts = await bot.get_all_accounts('active')
            await event.reply("📱 Account select karo:", buttons=kb_accounts(accounts))
            state['step'] = 'profile_acc_name'
        elif text == '🖼️ Change Photo':
            accounts = await bot.get_all_accounts('active')
            await event.reply("📱 Account select karo:", buttons=kb_accounts(accounts))
            state['step'] = 'profile_acc_photo'

    elif step == 'profile_acc_name':
        state['account'] = text
        state['step']    = 'profile_name_input'
        await event.reply(
            f"✅ Account: **{text}**\n\n"
            f"Profile daalo is format mein:\n"
            f"`FirstName|LastName|Bio`\n\n"
            f"Example: `John|Doe|Hello World`\n"
            f"_(koi ek chhod sakte ho — sirf | raho)_\n"
            f"Example sirf bio: `||My new bio`",
            buttons=kb_back()
        )

    elif step == 'profile_name_input':
        parts  = text.split('|', 2)
        fname  = parts[0].strip() if len(parts) > 0 else None
        lname  = parts[1].strip() if len(parts) > 1 else None
        bio    = parts[2].strip() if len(parts) > 2 else None
        fname  = fname  if fname  else None
        lname  = lname  if lname  else None
        bio    = bio    if bio    else None
        msg_obj = await event.reply("⏳ Profile update kar raha hoon...")
        ok, _, result = await bot.change_profile(state['account'], fname, lname, bio)
        await msg_obj.edit(
            f"{'✅' if ok else '❌'} **Profile Updated**\n\n"
            f"🏷️ Account: `{state['account']}`\n"
            f"👤 Name: {fname or '-'} {lname or '-'}\n"
            f"📝 Bio: {bio or '-'}\n"
            f"💬 {result}",
            buttons=kb_main()
        )
        del bot.user_states[uid]

    elif step == 'profile_acc_photo':
        state['account'] = text
        state['step']    = 'profile_photo_input'
        await event.reply(
            f"✅ Account: **{text}**\n\n"
            f"🖼️ Photo bhejo (image file send karo yahan):",
            buttons=kb_back()
        )

    elif step == 'profile_photo_input':
        # Photo as file
        if event.photo or event.document:
            msg_obj = await event.reply("⏳ Photo download kar raha hoon...")
            path    = await event.download_media(file='temp_photo.jpg')
            ok, _, result = await bot.change_photo(state['account'], path)
            try: os.remove(path)
            except: pass
            await msg_obj.edit(
                f"{'✅' if ok else '❌'} **Photo Changed**\n\n"
                f"🏷️ `{state['account']}`\n💬 {result}",
                buttons=kb_main()
            )
            del bot.user_states[uid]
        else:
            await event.reply("❌ Photo bhejo! Text nahi.", buttons=kb_back())
            return

    # ── ACCOUNT INFO ──────────────────────────────────────
    elif step == 'acc_info_select':
        msg_obj = await event.reply("⏳ Info nikaal raha hoon...")
        info, status = await bot.get_account_info(text)
        if not info:
            await msg_obj.edit(f"❌ {status}", buttons=kb_main())
        else:
            await msg_obj.edit(
                f"📱 **ACCOUNT INFO**\n\n"
                f"🏷️ Bot Name: `{info['name']}`\n"
                f"👤 Name: {info['first_name']} {info['last_name']}\n"
                f"🔗 Username: {info['username']}\n"
                f"📱 Phone: {info['phone']}\n"
                f"🆔 ID: `{info['id']}`\n"
                f"🤖 Bot: {info['bot']}\n"
                f"✅ Verified: {info['verified']}\n"
                f"💎 Premium: {info['premium']}\n"
                f"⚠️ Restricted: {info['restricted']}\n"
                f"🌐 Proxy: {info['proxy']}\n"
                f"💚 Health: {info['health']:.0f}%\n"
                f"📊 Reports: {info['total_rep']} (✅{info['success_rep']})\n"
                f"🕐 Last Used: {info['last_use']}\n"
                f"📅 Added: {info['created']}",
                buttons=kb_main()
            )
        del bot.user_states[uid]

    # ── MASS VOTE ─────────────────────────────────────────
    elif step == 'vote_link':
        state['poll_link'] = text
        state['step']      = 'vote_option'
        await event.reply(
            f"✅ Poll link: `{text}`\n\n"
            f"Konsa option? (0 se shuru)\n"
            f"0 = Pehla option\n1 = Doosra option\n2 = Teesra option",
            buttons=kb_back()
        )

    elif step == 'vote_option':
        try: option = int(text.strip())
        except: option = 0
        accounts  = await bot.get_all_accounts('active')
        total     = len(accounts)
        msg_obj   = await event.reply(f"🗳️ Voting... 0/{total}")
        last_edit  = [time.time()]

        async def vote_prog(done, total, success, failed):
            if time.time() - last_edit[0] > 2:
                bar = '█'*int(done/total*10)+'░'*(10-int(done/total*10))
                try:
                    await msg_obj.edit(f"🗳️ **MASS VOTE**\n[{bar}] {done}/{total}\n✅{success} ❌{failed}")
                    last_edit[0] = time.time()
                except: pass

        results, success, failed = await bot.mass_vote(state['poll_link'], option, progress_cb=vote_prog)
        await msg_obj.edit(
            f"🗳️ **VOTE COMPLETE**\n\nOption: #{option}\n✅ {success}/{total} voted\n❌ {failed} failed",
            buttons=kb_main()
        )
        del bot.user_states[uid]

    # ── MASS FORWARD ──────────────────────────────────────
    elif step == 'forward_source':
        state['source'] = text
        state['step']   = 'forward_dest'
        await event.reply(
            f"✅ Source: `{text}`\n\n"
            f"Kahan forward karein? (@username daalo):",
            buttons=kb_back()
        )

    elif step == 'forward_dest':
        source    = state['source']
        dest      = text.strip()
        accounts  = await bot.get_all_accounts('active')
        total     = len(accounts)
        msg_obj   = await event.reply(f"📢 Forwarding... 0/{total}")
        last_edit  = [time.time()]

        async def fwd_prog(done, total, success, failed):
            if time.time() - last_edit[0] > 2:
                bar = '█'*int(done/total*10)+'░'*(10-int(done/total*10))
                try:
                    await msg_obj.edit(f"📢 **MASS FORWARD**\n[{bar}] {done}/{total}\n✅{success} ❌{failed}")
                    last_edit[0] = time.time()
                except: pass

        results, success, failed = await bot.mass_forward(source, dest, progress_cb=fwd_prog)
        await msg_obj.edit(
            f"📢 **FORWARD COMPLETE**\n\n→ {dest}\n✅ {success}/{total}\n❌ {failed}",
            buttons=kb_main()
        )
        del bot.user_states[uid]

    # ── MASS VIEW ─────────────────────────────────────────
    elif step == 'view_link':
        link      = text.strip()
        accounts  = await bot.get_all_accounts('active')
        total     = len(accounts)
        msg_obj   = await event.reply(f"👁️ Views badha raha hoon... 0/{total}")
        last_edit  = [time.time()]

        async def view_prog(done, total, success, failed):
            if time.time() - last_edit[0] > 2:
                bar = '█'*int(done/total*10)+'░'*(10-int(done/total*10))
                try:
                    await msg_obj.edit(f"👁️ **MASS VIEW**\n[{bar}] {done}/{total}\n✅{success} ❌{failed}")
                    last_edit[0] = time.time()
                except: pass

        results, success, failed = await bot.mass_view(link, progress_cb=view_prog)
        await msg_obj.edit(
            f"👁️ **VIEW COMPLETE**\n\n🔗 {link}\n✅ +{success} views added\n❌ {failed} failed",
            buttons=kb_main()
        )
        del bot.user_states[uid]

    # ── MASS SUBSCRIBE ────────────────────────────────────
    elif step == 'subscribe_target':
        # Subscribe = Join
        target    = text.strip()
        accounts  = await bot.get_all_accounts('active')
        total     = len(accounts)
        msg_obj   = await event.reply(f"🔔 Subscribing... 0/{total}")
        last_edit  = [time.time()]

        async def sub_prog(done, total, success, failed):
            if time.time() - last_edit[0] > 2:
                bar = '█'*int(done/total*10)+'░'*(10-int(done/total*10))
                try:
                    await msg_obj.edit(f"🔔 **MASS SUBSCRIBE**\n[{bar}] {done}/{total}\n✅{success} ❌{failed}")
                    last_edit[0] = time.time()
                except: pass

        results, success, failed = await bot.mass_join(target, progress_cb=sub_prog)
        await msg_obj.edit(
            f"🔔 **SUBSCRIBE COMPLETE**\n\n🎯 {target}\n✅ {success}/{total} subscribed\n❌ {failed} failed",
            buttons=kb_main()
        )
        del bot.user_states[uid]

    # ── MASS BLOCK ────────────────────────────────────────
    elif step == 'block_target':
        target    = text.strip()
        accounts  = await bot.get_all_accounts('active')
        total     = len(accounts)
        msg_obj   = await event.reply(f"🚫 Blocking... 0/{total}")
        last_edit  = [time.time()]

        async def blk_prog(done, total, success, failed):
            if time.time() - last_edit[0] > 2:
                bar = '█'*int(done/total*10)+'░'*(10-int(done/total*10))
                try:
                    await msg_obj.edit(f"🚫 **MASS BLOCK**\n[{bar}] {done}/{total}\n✅{success} ❌{failed}")
                    last_edit[0] = time.time()
                except: pass

        results, success, failed = await bot.mass_block(target, progress_cb=blk_prog)
        await msg_obj.edit(
            f"🚫 **BLOCK COMPLETE**\n\n🎯 {target}\n✅ {success}/{total} blocked\n❌ {failed} failed",
            buttons=kb_main()
        )
        del bot.user_states[uid]

    # ── MASS CONTACT ──────────────────────────────────────
    elif step == 'contact_input':
        parts = text.split('|')
        if len(parts) < 2:
            await event.reply("❌ Format: `+91XXXXXXXXXX|FirstName|LastName`", buttons=kb_back()); return
        phone  = parts[0].strip()
        fname  = parts[1].strip() if len(parts) > 1 else "Contact"
        lname  = parts[2].strip() if len(parts) > 2 else ""
        accounts  = await bot.get_all_accounts('active')
        total     = len(accounts)
        msg_obj   = await event.reply(f"📞 Contact add kar raha hoon... 0/{total}")
        last_edit  = [time.time()]

        async def contact_prog(done, total, success, failed):
            if time.time() - last_edit[0] > 2:
                try:
                    await msg_obj.edit(f"📞 **MASS CONTACT**\n{done}/{total}\n✅{success} ❌{failed}")
                    last_edit[0] = time.time()
                except: pass

        results, success, failed = await bot.mass_add_contact(phone, fname, lname, progress_cb=contact_prog)
        await msg_obj.edit(
            f"📞 **CONTACT ADDED**\n\n📱 {phone}\n👤 {fname} {lname}\n✅ {success}/{total}\n❌ {failed}",
            buttons=kb_main()
        )
        del bot.user_states[uid]

    # ── AUTO REJOIN ───────────────────────────────────────
    elif step == 'rejoin_target':
        target   = text.strip()
        msg_obj  = await event.reply(f"🔄 Rejoining offline accounts to {target}...")
        rejoined = await bot.start_auto_rejoin(target)
        if rejoined:
            await msg_obj.edit(
                f"🔄 **AUTO REJOIN COMPLETE**\n\n"
                f"🎯 {target}\n"
                f"✅ Rejoined: {len(rejoined)}\n"
                f"Accounts: {', '.join(rejoined[:10])}",
                buttons=kb_main()
            )
        else:
            await msg_obj.edit("✅ Saare accounts already active hain!", buttons=kb_main())
        del bot.user_states[uid]

    # ── BYPASS MESSAGE ────────────────────────────────────
    elif step == 'bypass_target':
        state['target'] = text
        state['step']   = 'bypass_text'
        await event.reply(
            f"✅ Target: `{text}`\n\n"
            f"💬 Message likho (spam filter bypass hoga):",
            buttons=kb_back()
        )

    elif step == 'bypass_text':
        message   = text
        target    = state['target']
        accounts  = await bot.get_all_accounts('active')
        total     = len(accounts)
        msg_obj   = await event.reply(f"💬 Bypass message bhej raha hoon... 0/{total}")
        last_edit  = [time.time()]

        async def bypass_prog(done, total, success, failed):
            if time.time() - last_edit[0] > 2:
                bar = '█'*int(done/total*10)+'░'*(10-int(done/total*10))
                try:
                    await msg_obj.edit(f"💬 **BYPASS MSG**\n[{bar}] {done}/{total}\n✅{success} ❌{failed}")
                    last_edit[0] = time.time()
                except: pass

        results, success, failed = await bot.mass_bypass_send(target, message, progress_cb=bypass_prog)
        await msg_obj.edit(
            f"💬 **BYPASS COMPLETE**\n\n🎯 {target}\n✅ {success}/{total} sent\n❌ {failed} failed",
            buttons=kb_main()
        )
        del bot.user_states[uid]
    elif step == 'post_report_account':
        state['account'] = text
        state['step']    = 'post_report_link'
        await event.reply(
            f"✅ Account: **{text}**\n\n"
            f"📎 Post link daalo:\n"
            f"`https://t.me/channelname/123`\n"
            f"ya private channel:\n"
            f"`https://t.me/c/1234567890/123`",
            buttons=kb_back()
        )

    elif step == 'post_report_link':
        link = text.strip()
        channel, msg_id = bot.parse_post_link(link)
        if not channel or not msg_id:
            await event.reply(
                "❌ **Invalid Link!**\n\n"
                "Sahi format:\n"
                "`https://t.me/channelname/123`",
                buttons=kb_back()
            ); return
        state['post_link'] = link
        state['step']      = 'post_report_category'
        await event.reply(
            f"🔗 Link: `{link}`\n"
            f"🆔 Message ID: `{msg_id}`\n\n"
            f"📂 Category select karo:",
            buttons=kb_category()
        )

    elif step == 'post_report_category':
        cat = CATEGORY_MAP.get(text)
        if not cat:
            await event.reply("❌ Buttons se category chuno!", buttons=kb_category()); return
        msg_obj = await event.reply("⏳ Post report bhej raha hoon...")
        ok, _, result = await bot.report_post(state['account'], state['post_link'], cat)
        await msg_obj.edit(
            f"{'✅' if ok else '❌'} **Post Report Result**\n\n"
            f"🔗 {state['post_link']}\n"
            f"📂 {cat}\n"
            f"💬 {result}",
            buttons=kb_main()
        )
        del bot.user_states[uid]

    # ── MASS POST REPORT ──────────────────────────────────
    elif step == 'mass_post_link':
        link = text.strip()
        channel, msg_id = bot.parse_post_link(link)
        if not channel or not msg_id:
            await event.reply(
                "❌ **Invalid Link!**\n\n"
                "Sahi format:\n"
                "`https://t.me/channelname/123`",
                buttons=kb_back()
            ); return
        state['post_link'] = link
        state['step']      = 'mass_post_category'
        await event.reply(
            f"✅ Link valid hai!\n"
            f"🔗 `{link}`\n"
            f"🆔 Message ID: `{msg_id}`\n\n"
            f"📂 Category select karo:",
            buttons=kb_category()
        )

    elif step == 'mass_post_category':
        cat = CATEGORY_MAP.get(text)
        if not cat:
            await event.reply("❌ Buttons se category chuno!", buttons=kb_category()); return

        accounts = await bot.get_all_accounts('active')
        total    = len(accounts)
        link     = state['post_link']

        msg_obj  = await event.reply(
            f"💥 **MASS POST REPORT SHURU**\n\n"
            f"🔗 {link}\n"
            f"📂 {cat}\n"
            f"👥 {total} accounts\n\n"
            f"⏳ 0/{total} done..."
        )

        last_edit = [time.time()]

        async def on_progress(done, total, success, failed):
            if time.time() - last_edit[0] > 2:
                bar = '█' * int(done/total*10) + '░' * (10 - int(done/total*10))
                try:
                    await msg_obj.edit(
                        f"💥 **MASS POST REPORT**\n\n"
                        f"🔗 {link}\n"
                        f"📂 {cat}\n"
                        f"[{bar}] {done}/{total}\n"
                        f"✅ {success} | ❌ {failed}"
                    )
                    last_edit[0] = time.time()
                except: pass

        results, success, failed = await bot.mass_report_post(link, cat, progress_cb=on_progress)

        failed_accs = [name for ok, name, _ in results if not ok]
        fail_text   = f"\n❌ Failed: {', '.join(failed_accs[:5])}" if failed_accs else ""

        await msg_obj.edit(
            f"💥 **MASS POST REPORT COMPLETE**\n\n"
            f"🔗 {link}\n"
            f"📂 {cat}\n"
            f"✅ Success: {success}/{total}\n"
            f"❌ Failed: {failed}{fail_text}",
            buttons=kb_main()
        )
        del bot.user_states[uid]

    # ── SINGLE REPORT ─────────────────────────────────────
    elif step == 'report_account':
        state['account'] = text; state['step'] = 'report_target'
        await event.reply("🎯 Enter target (@username or ID):", buttons=kb_back())

    elif step == 'report_target':
        state['target'] = text; state['step'] = 'report_category'
        await event.reply("📂 Select category:", buttons=kb_category())

    elif step == 'report_category':
        cat = CATEGORY_MAP.get(text)
        if not cat:
            await event.reply("❌ Choose from buttons!", buttons=kb_category()); return
        msg_obj = await event.reply("⏳ Sending report...")
        ok, _, result = await bot.report_single(state['account'], state['target'], cat)
        await msg_obj.edit(
            f"{'✅' if ok else '❌'} **Report Result**\n\n"
            f"🎯 {state['target']}\n📂 {cat}\n💬 {result}",
            buttons=kb_main()
        )
        await bot.update_target_count(state['target'])
        del bot.user_states[uid]

    # ── MASS REPORT ───────────────────────────────────────
    elif step == 'mass_target':
        state['target'] = text; state['step'] = 'mass_category'
        await event.reply("📂 Select category:", buttons=kb_category())

    elif step == 'mass_category':
        cat = CATEGORY_MAP.get(text)
        if not cat:
            await event.reply("❌ Choose from buttons!", buttons=kb_category()); return

        accounts = await bot.get_all_accounts('active')
        total    = len(accounts)
        target   = state['target']

        msg_obj  = await event.reply(f"💥 **MASS REPORT STARTED**\n\n🎯 {target} | 📂 {cat}\n👥 {total} accounts\n\n⏳ 0/{total} done...")

        last_edit = [time.time()]

        async def on_progress(done, total, success, failed):
            if time.time() - last_edit[0] > 2:  # Edit every 2s to avoid flood
                bar = '█' * int(done/total*10) + '░' * (10 - int(done/total*10))
                try:
                    await msg_obj.edit(
                        f"💥 **MASS REPORT**\n\n"
                        f"🎯 {target} | 📂 {cat}\n"
                        f"[{bar}] {done}/{total}\n"
                        f"✅ {success} | ❌ {failed}"
                    )
                    last_edit[0] = time.time()
                except: pass

        results, success, failed = await bot.mass_report(target, cat, progress_cb=on_progress)
        await bot.update_target_count(target)

        # Final result
        failed_accs = [name for ok, name, _ in results if not ok]
        fail_text = f"\n❌ Failed: {', '.join(failed_accs[:5])}" if failed_accs else ""

        await msg_obj.edit(
            f"💥 **MASS REPORT COMPLETE**\n\n"
            f"🎯 {target} | 📂 {cat}\n"
            f"✅ Success: {success}/{total}\n"
            f"❌ Failed: {failed}{fail_text}",
            buttons=kb_main()
        )
        del bot.user_states[uid]

    # ── BATCH TARGETS ─────────────────────────────────────
    elif step == 'batch_targets_input':
        targets = [t.strip() for t in text.split(',') if t.strip()]
        if not targets:
            await event.reply("❌ Invalid input!", buttons=kb_back()); return
        state['targets'] = targets; state['step'] = 'batch_category'
        await event.reply(f"📂 Select category for {len(targets)} targets:", buttons=kb_category())

    elif step == 'batch_category':
        cat = CATEGORY_MAP.get(text)
        if not cat:
            await event.reply("❌ Choose from buttons!", buttons=kb_category()); return

        targets = state['targets']
        msg_obj = await event.reply(f"🔥 **BATCH REPORT**\n\n{len(targets)} targets | 📂 {cat}\n\nStarting...")

        grand_ok, grand_fail = 0, 0
        for i, tgt in enumerate(targets):
            _, ok, fail = await bot.mass_report(tgt, cat)
            grand_ok += ok; grand_fail += fail
            await bot.update_target_count(tgt)
            try:
                await msg_obj.edit(
                    f"🔥 **BATCH REPORT**\n\n"
                    f"Progress: {i+1}/{len(targets)} targets\n"
                    f"✅ {grand_ok} | ❌ {grand_fail}"
                )
            except: pass
            await asyncio.sleep(3)

        await msg_obj.edit(
            f"🔥 **BATCH COMPLETE**\n\n"
            f"📋 Targets: {len(targets)}\n"
            f"✅ Total sent: {grand_ok}\n"
            f"❌ Total failed: {grand_fail}",
            buttons=kb_main()
        )
        del bot.user_states[uid]

    # ── SAVED TARGETS ─────────────────────────────────────
    elif step == 'save_target_input':
        parts = [p.strip() for p in text.split('|')]
        if len(parts) < 3:
            await event.reply("❌ Format: `label|@target|category|note`", buttons=kb_back()); return
        label = parts[0]; tgt = parts[1]; cat = parts[2]
        note  = parts[3] if len(parts) > 3 else ''
        if cat not in REPORT_CATEGORIES:
            await event.reply(f"❌ Invalid category: {cat}", buttons=kb_back()); return
        ok, msg = await bot.save_target(label, tgt, cat, note)
        await event.reply(msg, buttons=kb_main()); del bot.user_states[uid]

    elif step == 'report_saved_select':
        saved_map = state.get('saved_targets', {})
        if text not in saved_map:
            await event.reply("❌ Not found!", buttons=kb_back()); return
        _, tgt, cat, _, _ = saved_map[text]
        msg_obj = await event.reply(f"🚀 Running mass report on `{text}`...")
        _, success, failed = await bot.mass_report(tgt, cat)
        await bot.update_target_count(tgt)
        await msg_obj.edit(
            f"🚀 **SAVED TARGET REPORTED**\n\n🏷️ {text}\n🎯 {tgt}\n📂 {cat}\n✅ {success} | ❌ {failed}",
            buttons=kb_main()
        )
        del bot.user_states[uid]

    elif step == 'del_saved_select':
        ok, msg = await bot.delete_saved_target(text)
        await event.reply(msg, buttons=kb_main()); del bot.user_states[uid]

    # ── TARGET INFO ───────────────────────────────────────
    elif step == 'info_target':
        msg_obj = await event.reply("🔍 Looking up info...")
        info, status = await bot.get_target_info(text)
        if not info:
            await msg_obj.edit(f"❌ {status}", buttons=kb_main())
        else:
            name_str = f"{info['first_name']} {info['last_name']}".strip() or info['title']
            members  = f"\n👥 Members: {info.get('members', 'N/A')}" if 'members' in info else ""
            desc     = f"\n📝 Bio: {info['description'][:80]}" if info.get('description') else ""
            report_count = 0
            async with aiosqlite.connect(bot.reports_db) as db:
                async with db.execute('SELECT COUNT(*) FROM reports WHERE target=?', (text.lstrip('@'),)) as c:
                    report_count = (await c.fetchone())[0]

            await msg_obj.edit(
                f"🔍 **TARGET INFO**\n\n"
                f"📌 Type: {info['type']}\n"
                f"👤 Name: {name_str}\n"
                f"🔗 Username: {info['username']}\n"
                f"🆔 ID: `{info['id']}`\n"
                f"📱 Phone: {info['phone']}"
                f"{members}{desc}\n"
                f"✅ Verified: {info['verified']}\n"
                f"⚠️ Restricted: {info['restricted']}\n"
                f"🚨 Scam Flag: {info['scam']}\n"
                f"🎭 Fake Flag: {info['fake']}\n"
                f"📊 Reports by us: {report_count}",
                buttons=kb_main()
            )
        del bot.user_states[uid]

    # ── SCHEDULER ─────────────────────────────────────────
    elif step == 'new_schedule_input':
        parts = [p.strip() for p in text.split('|')]
        if len(parts) < 5:
            await event.reply("❌ Format: `label|@target|category|interval_min|max_runs`", buttons=kb_back()); return
        label, tgt, cat, interval_str, max_str = parts[0], parts[1], parts[2], parts[3], parts[4]
        if cat not in REPORT_CATEGORIES:
            await event.reply(f"❌ Invalid category!", buttons=kb_back()); return
        try:
            interval = int(interval_str); max_runs = int(max_str)
        except:
            await event.reply("❌ Interval and max_runs must be numbers!", buttons=kb_back()); return

        accounts = await bot.get_all_accounts('active')
        acc_names = [r[0] for r in accounts]
        sid = await bot.create_schedule(uid, label, tgt, cat, acc_names, interval, max_runs)
        await event.reply(
            f"✅ **Schedule Created** [ID:{sid}]\n\n"
            f"🏷️ {label}\n🎯 {tgt}\n📂 {cat}\n"
            f"⏱️ Every {interval} min | 🔁 Max {max_runs or '∞'} runs\n"
            f"👥 {len(acc_names)} accounts assigned",
            buttons=kb_main()
        )
        del bot.user_states[uid]

    elif step == 'del_schedule_select':
        import re
        match = re.match(r'\[(\d+)\]', text)
        if match:
            sid = int(match.group(1))
            await bot.delete_schedule(sid)
            await event.reply(f"🗑️ Schedule [{sid}] deleted!", buttons=kb_main())
        else:
            await event.reply("❌ Invalid selection!", buttons=kb_back())
        del bot.user_states[uid]

    # ── CSV EXPORT ────────────────────────────────────────
    elif step == 'export_csv_filter':
        target_filter = None if text.lower() in ('all', 'yes', '') else text
        path, msg = await bot.export_reports_csv(target_filter)
        if path:
            await bot.bot_client.send_file(uid, path,
                caption=f"📤 **Reports Export**\n{msg}",
                buttons=kb_main()
            )
            try: os.remove(path)
            except: pass
        else:
            await event.reply(msg, buttons=kb_main())
        del bot.user_states[uid]

    # ── SETTINGS ──────────────────────────────────────────
    elif step == 'set_max_concurrent':
        try:
            val = int(text)
            if 1 <= val <= 20:
                bot.config['MAX_CONCURRENT'] = val
                bot.save_config()
                await event.reply(f"✅ Max concurrent set to **{val}**", buttons=kb_main())
            else:
                await event.reply("❌ Enter 1–20!", buttons=kb_back())
                return
        except:
            await event.reply("❌ Numbers only!", buttons=kb_back())
            return
        del bot.user_states[uid]


# ═══════════════════════════════════════════════════════════
#                        MAIN
# ═══════════════════════════════════════════════════════════

async def h_zip_file(event):
    """Handle ZIP file uploads for session import"""
    uid  = event.sender_id
    if not bot.is_admin(uid) or not bot.is_authenticated(uid):
        return
    state = bot.user_states.get(uid, {})
    if state.get('step') != 'zip_wait':
        return

    import zipfile, tempfile, shutil
    from telethon.sessions import StringSession

    doc  = event.document
    name = state.get('name', f'acc_{uid}')

    # Check if it's a ZIP
    file_name = doc.attributes[0].file_name if doc.attributes else ''
    if not file_name.lower().endswith('.zip'):
        await event.reply("❌ Sirf ZIP file bhejo!", buttons=kb_back())
        return

    msg_obj = await event.reply("⏳ ZIP download ho raha hai...")

    tmp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(tmp_dir, 'session.zip')

    try:
        # Download ZIP
        await bot.bot_client.download_media(event.message, zip_path)
        await msg_obj.edit("📦 ZIP extract ho raha hai...")

        # Extract ZIP
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(tmp_dir)

        # Find .session file
        session_file = None
        for root, dirs, files in os.walk(tmp_dir):
            for f in files:
                if f.endswith('.session') and f != 'session.zip':
                    session_file = os.path.join(root, f)
                    break
            if session_file:
                break

        if not session_file:
            await msg_obj.edit(
                "❌ ZIP mein `.session` file nahi mili!\n\n"
                "ZIP mein yeh hona chahiye:\n"
                "• `account.session` file\n"
                "• Ya session string wali koi `.session` file",
                buttons=kb_main()
            )
            del bot.user_states[uid]
            return

        await msg_obj.edit("🔑 Session verify ho rahi hai...")

        # Read session - try as SQLite first, then as string
        session_str = None
        try:
            import sqlite3
            conn = sqlite3.connect(session_file)
            cur  = conn.cursor()
            cur.execute("SELECT session_id FROM sessions LIMIT 1")
            row = cur.fetchone()
            conn.close()
            if row:
                session_str = row[0]
        except Exception:
            pass

        # If SQLite didn't work, try reading as text/string
        if not session_str:
            try:
                with open(session_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().strip()
                    if len(content) > 50:
                        session_str = content
            except Exception:
                pass

        if not session_str:
            await msg_obj.edit(
                "❌ Session file se data nahi nikla!\n"
                "Manually session string paste karo (`📤 Import Session` use karo).",
                buttons=kb_main()
            )
            del bot.user_states[uid]
            return

        ok, result_msg = await bot.add_account_from_session(name, session_str)
        await msg_obj.edit(result_msg, buttons=kb_main())
        del bot.user_states[uid]

    except zipfile.BadZipFile:
        await msg_obj.edit("❌ Invalid ZIP file!", buttons=kb_main())
        del bot.user_states[uid]
    except Exception as e:
        await msg_obj.edit(f"❌ Error: {str(e)[:100]}", buttons=kb_main())
        del bot.user_states[uid]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def main():
    await bot.init_db()
    log.info("✅ Database ready")

    bot.bot_client = TelegramClient(
        'bot_session',
        int(bot.config['API_ID']),
        bot.config['API_HASH']
    )
    await bot.bot_client.start(bot_token=bot.config['BOT_TOKEN'])
    log.info("✅ Bot client started")

    # Register all handlers
    handlers = [
        (h_start,        events.NewMessage(pattern=r'/start', incoming=True)),
        (h_login,        events.NewMessage(pattern=r'🔐 Login', incoming=True)),
        (h_logout,       events.NewMessage(pattern=r'❌ Logout', incoming=True)),
        (h_back,         events.NewMessage(pattern=r'❌ Back', incoming=True)),
        (h_add,          events.NewMessage(pattern=r'➕ Add Account', incoming=True)),
        (h_import,       events.NewMessage(pattern=r'📤 Import Session', incoming=True)),
        (h_zip_import,   events.NewMessage(pattern=r'📦 ZIP Import', incoming=True)),
        (h_read_otp,     events.NewMessage(pattern=r'📖 Read OTP', incoming=True)),
        (h_export,       events.NewMessage(pattern=r'📥 Export Session', incoming=True)),
        (h_list,         events.NewMessage(pattern=r'📋 Accounts', incoming=True)),
        (h_delete_acc,   events.NewMessage(pattern=r'🗑️ Delete Account', incoming=True)),
        (h_health,       events.NewMessage(pattern=r'🏥 Health Check', incoming=True)),
        (h_report,       events.NewMessage(pattern=r'🎯 Report', incoming=True)),
        (h_mass,         events.NewMessage(pattern=r'💥 Mass Report', incoming=True)),
        (h_post_report,      events.NewMessage(pattern=r'📝 Post Report', incoming=True)),
        (h_mass_post_report, events.NewMessage(pattern=r'💥 Mass Post Report', incoming=True)),
        (h_join_group,       events.NewMessage(pattern=r'👥 Join Group', incoming=True)),
        (h_leave_group,      events.NewMessage(pattern=r'🚪 Leave Group', incoming=True)),
        (h_mute,             events.NewMessage(pattern=r'🔇 Mute Group', incoming=True)),
        (h_unmute,           events.NewMessage(pattern=r'🔔 Unmute Group', incoming=True)),
        (h_auto_msg,         events.NewMessage(pattern=r'📨 Auto Message', incoming=True)),
        (h_username,         events.NewMessage(pattern=r'👤 Username Change', incoming=True)),
        (h_profile,          events.NewMessage(pattern=r'🖼️ Profile Changer', incoming=True)),
        (h_acc_info,         events.NewMessage(pattern=r'📱 Account Info', incoming=True)),
        (h_flood_test,       events.NewMessage(pattern=r'⚡ Flood Test', incoming=True)),
        (h_live_counter,     events.NewMessage(pattern=r'📊 Live Counter', incoming=True)),
        (h_mass_vote,        events.NewMessage(pattern=r'🗳️ Mass Vote', incoming=True)),
        (h_mass_forward,     events.NewMessage(pattern=r'📢 Mass Forward', incoming=True)),
        (h_mass_view,        events.NewMessage(pattern=r'👁️ Mass View', incoming=True)),
        (h_mass_subscribe,   events.NewMessage(pattern=r'🔔 Mass Subscribe', incoming=True)),
        (h_mass_block,       events.NewMessage(pattern=r'🚫 Mass Block', incoming=True)),
        (h_mass_contact,     events.NewMessage(pattern=r'📞 Mass Contact', incoming=True)),
        (h_session_check,    events.NewMessage(pattern=r'🔑 Session Checker', incoming=True)),
        (h_ip_check,         events.NewMessage(pattern=r'🌐 IP Checker', incoming=True)),
        (h_auto_rejoin,      events.NewMessage(pattern=r'🔄 Auto Rejoin', incoming=True)),
        (h_bypass_msg,       events.NewMessage(pattern=r'💬 Bypass Message', incoming=True)),
        (h_report_timer,     events.NewMessage(pattern=r'⏱️ Report Timer', incoming=True)),
        (h_log_viewer,       events.NewMessage(pattern=r'📋 Log Viewer', incoming=True)),
        (h_batch,        events.NewMessage(pattern=r'🔥 Batch Targets', incoming=True)),
        (h_saved,        events.NewMessage(pattern=r'💾 Saved Targets', incoming=True)),
        (h_save_new,     events.NewMessage(pattern=r'💾 Save New Target', incoming=True)),
        (h_report_saved, events.NewMessage(pattern=r'🚀 Report Saved Target', incoming=True)),
        (h_del_saved,    events.NewMessage(pattern=r'🗑️ Delete Saved Target', incoming=True)),
        (h_info,         events.NewMessage(pattern=r'🔍 Target Info', incoming=True)),
        (h_scheduler,    events.NewMessage(pattern=r'⏰ Scheduler', incoming=True)),
        (h_new_schedule, events.NewMessage(pattern=r'➕ New Schedule', incoming=True)),
        (h_del_schedule, events.NewMessage(pattern=r'🗑️ Delete Schedule', incoming=True)),
        (h_stats,        events.NewMessage(pattern=r'📊 Statistics', incoming=True)),
        (h_export_csv,   events.NewMessage(pattern=r'📤 Export CSV', incoming=True)),
        (h_settings,     events.NewMessage(pattern=r'⚙️ Settings', incoming=True)),
        (h_speed_fast,   events.NewMessage(pattern=r'⚡ Speed: Fast', incoming=True)),
        (h_speed_safe,   events.NewMessage(pattern=r'🛡️ Speed: Safe', incoming=True)),
        (h_speed_bal,    events.NewMessage(pattern=r'⚖️ Speed: Balanced', incoming=True)),
        (h_max_conc,     events.NewMessage(pattern=r'🔢 Max Concurrent', incoming=True)),
        (h_text,         events.NewMessage(incoming=True)),
    ]
    for handler, evt in handlers:
        bot.bot_client.add_event_handler(handler, evt)

    # ZIP file handler
    bot.bot_client.add_event_handler(h_zip_file, events.NewMessage(incoming=True, func=lambda e: e.document is not None))
    log.info("✅ All handlers registered")

    # Start background scheduler
    asyncio.create_task(bot.run_scheduler())
    log.info("✅ Scheduler started")

    print("\n" + "═"*50)
    print("  🔥 ULTRA REPORT BOT v8.0 is RUNNING")
    print("═"*50 + "\n")

    await bot.bot_client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
