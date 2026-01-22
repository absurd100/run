import time
#from datetime import datetime, timedelta, timezone
import os
import asyncio
import threading
import dns.resolver
# anu Tambahkan baris ini untuk memperbaiki error di Termux
dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['223.5.5.5', '223.6.6.6']

#import datetime
import hashlib
import re
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# 1. LOAD ENV DULU SEBELUM DIGUNAKAN
load_dotenv()

from http.server import BaseHTTPRequestHandler, HTTPServer
from pyrogram import Client, filters, idle
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient

# --- AMBIL KONFIGURASI DARI ENV ---
# Pastikan variabel ini didefinisikan SEBELUM membuat Client
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MONGO_URL = os.environ.get("MONGO_URL", "")
OWNER_ID = int(os.environ.get("OWNER_ID", 0))

# --- DATABASE SETUP ---
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client["antispam"]
config_db = db["status"]
messages_db = db["seen_messages"]
regex_db = db["regex_list"]

# --- INISIALISASI BOT ---
# Cukup satu saja, jangan duplikat
app = Client(
    "antispam_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    plugins=dict(root="plugins")  # Plugin akan otomatis terdeteksi di folder plugins
)

# --- HEALTH CHECK (UNTUK KOYEB/PAAS) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot Antispam is Online 2026")

def run_health_check():
    try:
        port = int(os.environ.get("PORT", 8000))
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        server.serve_forever()
    except Exception as e:
        print(f"Health check error: {e}")

threading.Thread(target=run_health_check, daemon=True).start()

# --- VARIABEL GLOBAL ---
delete_queue = asyncio.Queue()
GLOBAL_EXPIRY = 15
DEFAULT_LOCAL_EXPIRY = 3600
LINK_PATTERN = r"(https?://\S+|t\.me/\S+|www\.\S+)"

# --- WORKER: PENGHAPUS PESAN ---
async def delete_worker():
    while True:
        chat_id, message_ids = await delete_queue.get()
        try:
            await app.delete_messages(chat_id, message_ids)
            await asyncio.sleep(0.1) # Jeda singkat untuk menghindari flood
        except: pass
        finally:
            delete_queue.task_done()

async def auto_delete_reply(messages, delay=5):
    await asyncio.sleep(delay)
    for msg in messages:
        try: await delete_queue.put((msg.chat.id, [msg.id]))
        except: pass

# --- SETUP TTL DATABASE (6 JAM) ---
async def setup_db():
    await messages_db.create_index("createdAt", expireAfterSeconds=21600)
    print("✅ Database & TTL Index 6 Hours Active.")

async def get_config(chat_id):
    cfg = await config_db.find_one({"chat_id": chat_id})
    if not cfg:
        return {"local": True, "global": True, "expiry": DEFAULT_LOCAL_EXPIRY, "bio_check": False}
    return cfg

async def update_config(chat_id, key, value):
    await config_db.update_one({"chat_id": chat_id}, {"$set": {key: value}}, upsert=True)

async def is_admin(client, chat_id, user_id):
    if not user_id: return False
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except: return False

# --- LOGIKA CORE ---
@app.on_message(filters.group & ~filters.service, group=2)
async def main_core_filter(client, message):
    if not message.from_user: return
    cid, uid, mid = message.chat.id, message.from_user.id, message.id

    # 1. Pengecualian Admin
    if await is_admin(client, cid, uid): return
    cfg = await get_config(cid)

    # Filter Isi Pesan
    if not (message.text or message.caption): return
    content = (message.text or message.caption).strip()
    if content.startswith("/"): return

    # 3. REGEX BLACKLIST (Owner Only Patterns)
    async for reg in regex_db.find({}):
        if re.search(reg["pattern"], content, re.IGNORECASE):
            await delete_queue.put((cid, [mid]))
            return

    now_ts, now_dt = time.time(), datetime.now(timezone(timedelta(hours=7)))
    content_hash = hashlib.md5(content.encode()).hexdigest()

    # 4. ANTI DUPLIKASI LOKAL (Duplikasi di grup yang sama)
    local_key = f"loc_{cid}_{uid}_{content_hash}"
    existing_local = await messages_db.find_one({"_id": local_key})
    if cfg.get("local", True) and existing_local:
        if (now_ts - existing_local["time"]) < cfg.get("expiry", DEFAULT_LOCAL_EXPIRY):
            await delete_queue.put((cid, [existing_local["msg_id"], mid]))
            return

    # 5. ANTI DUPLIKASI GLOBAL (Duplikasi lintas grup)
    global_key = f"glob_{uid}_{content_hash}"
    existing_global = await messages_db.find_one({"_id": global_key})
    if existing_global:
        if (now_ts - existing_global["time"]) < GLOBAL_EXPIRY:
            locs = existing_global.get("locations", [])
            if [cid, mid] not in locs: locs.append([cid, mid])
            await messages_db.update_one({"_id": global_key}, {"$set": {"locations": locs, "createdAt": now_dt}})

            for loc_cid, loc_mid in locs:
                target_cfg = await get_config(loc_cid)
                if target_cfg.get("global", True):
                    await delete_queue.put((loc_cid, [loc_mid]))
            return
        else:
            await messages_db.update_one({"_id": global_key}, {"$set": {"time": now_ts, "createdAt": now_dt, "locations": [[cid, mid]]}})
    else:
        await messages_db.insert_one({"_id": global_key, "time": now_ts, "createdAt": now_dt, "locations": [[cid, mid]]})

    # Simpan status untuk pengecekan lokal berikutnya
    await messages_db.update_one({"_id": local_key}, {"$set": {"time": now_ts, "msg_id": mid, "createdAt": now_dt}}, upsert=True)

# --- COMMAND HANDLERS ---
@app.on_message(filters.command(["addregex", "delregex", "infobot"]) & filters.user(OWNER_ID))
async def owner_management(client, message):
    cmd = message.command[0].lower()
    if cmd == "addregex":
        if len(message.command) < 2: return await message.reply("Format: `/addregex pola`")
        pattern = " ".join(message.command[1:])
        try:
            re.compile(pattern)
            await regex_db.update_one({"pattern": pattern}, {"$set": {"pattern": pattern}}, upsert=True)
            await message.reply(f"✅ Regex `{pattern}` berhasil disimpan.")
        except: await message.reply("❌ Pattern Regex tidak valid!")
    elif cmd == "delregex":
        pattern = " ".join(message.command[1:])
        await regex_db.delete_one({"pattern": pattern})
        await message.reply(f"🗑 Regex `{pattern}` dihapus.")
    elif cmd == "infobot":
        res = [doc["pattern"] async for doc in regex_db.find({})]
        text_regex = "📋 **Daftar Blacklist Regex:**\n`" + "`\n`".join(res) + "`" if res else " 📋 **Daftar Regex:** Kosong."
        await message.reply(text_regex)

@app.on_message(filters.command("start") & filters.private)
async def start_private(client, message):
    me = await client.get_me()
    add_url = f"t.me/{me.username}?startgroup=true&admin=delete_messages"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("➕ Aktifkan Proteksi di Grup", url=add_url)]])
    await message.reply(f"👋 **Selamat Datang di Sistem Keamanan Bot Antispam**\n\n"
        "Saya adalah bot spesialis mitigasi spam massal lintas grup secara *real-time*.\n\n"
        "📖 **TUTORIAL PENGGUNAAN:**\n"
        "1. Klik tombol di bawah untuk menambahkan saya ke grup Anda.\n"
        "2. Pastikan saya diberikan hak akses sebagai **Administrator** dengan izin **Hapus Pesan (Delete Messages)**.\n"
        "3. Setelah aktif, saya akan memantau setiap pesan masuk secara otomatis.\n\n"
        "📋 **DAFTAR PERINTAH ADMIN GRUP:**\n"
        "• `/status` - Memeriksa konfigurasi keamanan grup saat ini.\n"
        "• `/setlocal [on/off]` - Mengaktifkan filter duplikasi konten dalam grup.\n"
        "• `/setglobal [on/off]` - Mengaktifkan filter berdasarkan database blacklist pusat.\n"
        "• `/biocheck [on/off]` - Menghapus pesan jika bio profil member ada link/username.\n"
        "• `/setwaktu [menit]` - Mengatur rentang waktu deteksi pengulangan pesan.\n"
        "• `/antigcast` - Verifikasi status proteksi grup.\n\n"
        "🛡 *Pengelolaan spam di grup Anda adalah fokus utama kami.*", reply_markup=keyboard)

@app.on_message(filters.command(["setlocal", "setglobal", "setwaktu", "status", "setbio", "antigcast"]) & filters.group)
async def admin_handlers(client, message):
    if not message.from_user: return
    cid, cmd = message.chat.id, message.command[0].lower()

    if cmd == "antigcast":
        me = await client.get_me()
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("👀 lihat detail bot", url=f"t.me/{me.username}?start=help")]])
        res = await message.reply("🛡 **Grup ini memiliki sistem Antispam**", reply_markup=keyboard)
        return asyncio.create_task(auto_delete_reply([message, res], 5))

    if not await is_admin(client, cid, message.from_user.id): return
    cfg = await get_config(cid)
    res = None

    if cmd == "status":
        text = (f"🖥 **DASHBOARD KEAMANAN GRUP**\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                f"📡 **Proteksi Lokal:** `{'AKTIF' if cfg.get('local', True) else 'OFF'}`\n"
                f"📡 **Proteksi Global:** `{'AKTIF' if cfg.get('global', True) else 'OFF'}`\n"
                f"📡 **Proteksi Bio Link:** `{'AKTIF' if cfg.get('bio_check', False) else 'OFF'}`\n"
                f"⏱ **Jendela Deteksi:** `{cfg.get('expiry', DEFAULT_LOCAL_EXPIRY)//60} Menit`\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯")
        res = await message.reply(text)
    elif cmd == "setwaktu":
        if len(message.command) > 1 and message.command[1].isdigit():
            m = int(message.command[1]); await update_config(cid, "expiry", m * 60)
            res = await message.reply(f"✅ Window lokal diatur ke: `{m} menit`.")
    elif cmd in ["setlocal", "setglobal", "setbio"]:
        if len(message.command) > 1:
            mode = message.command[1].lower() == "on"
            key = "bio_check" if cmd == "setbio" else ("local" if "local" in cmd else "global")
            await update_config(cid, key, mode)
            res = await message.reply(f"✅ `{key.upper()}` sekarang: `{'ON' if mode else 'OFF'}`.")

    if res: asyncio.create_task(auto_delete_reply([message, res], 10))

# --- BOOTSTRAP ---
async def main():
    await setup_db()
    asyncio.create_task(delete_worker())
    await app.start()
    print("🚀gass")
    await idle()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
