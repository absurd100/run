import logging
import asyncio
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup

# Konfigurasi
API_ID = 1234567 # Ambil dari my.telegram.org
API_HASH = "your_api_hash"
TOKEN = "8547852944:AAFAGy3owqlPNRxT1j8UajTWygHqFATwxFw"
OWNER_ID = 8471902501 
TIMEOUT_SECONDS = 600 

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

app = Client("anon_bot", api_id=API_ID, api_hash=API_HASH, bot_token=TOKEN)

user_data = {} 
queue = []

async def show_menu(user_id):
    if user_id not in user_data or not user_data[user_id]['identity']:
        return

    identity = user_data[user_id]['identity']
    warna = "cewe" if identity == "cewe" else "cowo"
    reply_keyboard = ReplyKeyboardMarkup(
        [['🔍 Cari cewe', '🔍 Cari cowo'], ['⚙️ Ganti Identitas']],
        resize_keyboard=True
    )

    await app.send_message(
        chat_id=user_id,
        text=f"Gender Anda: {warna}\nmau obrol sm sp?",
        reply_markup=reply_keyboard
    )

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(_, message):
    user_id = message.from_user.id
    user_data[user_id] = {'identity': None, 'partner': None, 'searching_for': None, 'last_activity': datetime.now()}

    reply_keyboard = ReplyKeyboardMarkup([['👧 cewe', '🧒 cowo']], resize_keyboard=True, one_time_keyboard=True)
    await message.reply_text(
        "Selamat datang! Pilih identitas gender kamu:",
        reply_markup=reply_keyboard,
    )

@app.on_message(filters.command("broadcast") & filters.private)
async def broadcast_cmd(_, message):
    if message.from_user.id != OWNER_ID:
        return

    msg_text = " ".join(message.command[1:])
    if not msg_text:
        await message.reply_text("Gunakan: /broadcast [pesan]")
        return

    count = 0
    for uid in list(user_data.keys()):
        try:
            await app.send_message(chat_id=uid, text=f"📢 **PENGUMUMAN:**\n\n{msg_text}")
            count += 1
        except:
            continue

    await message.reply_text(f"Berhasil mengirim broadcast ke {count} user.")

async def timeout_checker():
    """Looping pengecekan timeout (Pengganti JobQueue)"""
    while True:
        await asyncio.sleep(30)
        now = datetime.now()
        to_disconnect = []

        for uid, data in user_data.items():
            if data['partner']:
                diff = (now - data['last_activity']).total_seconds()
                if diff > TIMEOUT_SECONDS:
                    to_disconnect.append(uid)

        for uid in to_disconnect:
            partner_id = user_data[uid]['partner']
            if not partner_id: continue

            user_data[uid]['partner'] = None
            if partner_id in user_data:
                user_data[partner_id]['partner'] = None

            for target in [uid, partner_id]:
                try:
                    await app.send_message(target, "⚠️ Chat dihentikan otomatis karena tidak ada interaksi selama 10 menit.")
                    await show_menu(target)
                except: pass

@app.on_message(filters.private)
async def handle_message_pyro(_, message):
    user_id = message.from_user.id
    if user_id not in user_data:
        user_data[user_id] = {'identity': None, 'partner': None, 'searching_for': None, 'last_activity': datetime.now()}

    user = user_data[user_id]
    user['last_activity'] = datetime.now()
    text = message.text if message.text else ""

    # 1. Pilih Identitas
    if text in ['👧 cewe', '🧒 cowo']:
        user['identity'] = "cewe" if "cewe" in text else "cowo"
        await show_menu(user_id)
        return

    # 2. Ganti Identitas
    if text == '⚙️ Ganti Identitas':
        await start_cmd(_, message)
        return

    # 3. Logika Chatting & Stop
    if user['partner']:
        partner_id = user['partner']
        if text in ['/stop', '🛑 Berhenti']:
            user['partner'] = None
            if partner_id in user_data:
                user_data[partner_id]['partner'] = None

            await message.reply_text("Chat dihentikan. Cache dibersihkan.")
            try:
                await app.send_message(partner_id, "Partner telah menghentikan obrolan.")
                await show_menu(partner_id)
            except: pass
            await show_menu(user_id)
        else:
            try:
                await message.copy(chat_id=partner_id)
            except:
                await message.reply_text("Gagal. Partner memblokir bot.")
        return

    # 4. Batal Cari
    if text == 'Batal':
        global queue
        queue = [q for q in queue if q['id'] != user_id]
        await message.reply_text("Pencarian dibatalkan.")
        await show_menu(user_id)
        return

    # 5. Mencari Pasangan
    if text in ['🔍 Cari cewe', '🔍 Cari cowo']:
        searching_for = "cewe" if "cewe" in text else "cowo"
        my_ident = user['identity']

        if not my_ident:
            await start_cmd(_, message)
            return

        match_idx = -1
        for i, q in enumerate(queue):
            if q['identity'] == searching_for and q['searching_for'] == my_ident:
                match_idx = i
                break

        if match_idx != -1:
            p = queue.pop(match_idx)
            pid = p['id']
            user['partner'] = pid
            user_data[pid]['partner'] = user_id

            msg = "Pasangan ditemukan! Silakan chat.\nKlik 🛑 Berhenti untuk berhenti."
            btn = ReplyKeyboardMarkup([['🛑 Berhenti']], resize_keyboard=True)

            await app.send_message(pid, msg, reply_markup=btn)
            await message.reply_text(msg, reply_markup=btn)
        else:
            queue[:] = [q for q in queue if q['id'] != user_id]
            queue.append({'id': user_id, 'identity': my_ident, 'searching_for': searching_for})
            await message.reply_text("Mencari...", reply_markup=ReplyKeyboardMarkup([['Batal']], resize_keyboard=True))

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(timeout_checker())
    print(">>> BOT ANONIM 2026 (PYROGRAM) BERJALAN <<<")
    app.run()
