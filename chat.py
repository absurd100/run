import logging
import asyncio
from datetime import datetime
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Konfigurasi
TOKEN = "8547852944:AAFAGy3owqlPNRxT1j8UajTWygHqFATwxFw"
OWNER_ID = 8471902501  # GANTI DENGAN ID TELEGRAM ANDA (Cek di @userinfobot)
TIMEOUT_SECONDS = 600 # 10 Menit

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

user_data = {} # {user_id: {'identity': str, 'partner': int, 'searching_for': str, 'last_activity': datetime}}
queue = []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id] = {'identity': None, 'partner': None, 'searching_for': None, 'last_activity': datetime.now()}

    reply_keyboard = [['👧 cewe', '🧒 cowo']]
    await update.message.reply_text(
        "Selamat datang! Pilih identitas gender kamu:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
    )

async def show_menu(context: ContextTypes.DEFAULT_TYPE, user_id):
    if user_id not in user_data or not user_data[user_id]['identity']:
        return

    identity = user_data[user_id]['identity']
    warna = "cewe" if identity == "cewe" else "cowo"
    reply_keyboard = [['🔍 Cari cewe', '🔍 Cari cowo'], ['⚙️ Ganti Identitas']]

    await context.bot.send_message(
        chat_id=user_id,
        text=f"Gender Anda: {warna}\nmau obrol sm sp?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fitur khusus owner untuk mengirim pesan ke semua user"""
    if update.effective_user.id != OWNER_ID:
        return

    msg_text = " ".join(context.args)
    if not msg_text:
        await update.message.reply_text("Gunakan: /broadcast [pesan]")
        return

    count = 0
    for uid in user_data.keys():
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 **PENGUMUMAN:**\n\n{msg_text}", parse_mode="Markdown")
            count += 1
        except:
            continue

    await update.message.reply_text(f"Berhasil mengirim broadcast ke {count} user.")

async def timeout_checker(context: ContextTypes.DEFAULT_TYPE):
    """Memutuskan chat otomatis jika tidak ada aktifitas selama 10 menit"""
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

        # Hapus Cache Partner (Disconnect)
        user_data[uid]['partner'] = None
        user_data[partner_id]['partner'] = None

        for target in [uid, partner_id]:
            try:
                await context.bot.send_message(target, "⚠️ Chat dihentikan otomatis karena tidak ada interaksi selama 10 menit.")
                await show_menu(context, target)
            except: pass

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data:
        user_data[user_id] = {'identity': None, 'partner': None, 'searching_for': None, 'last_activity': datetime.now()}

    user = user_data[user_id]
    user['last_activity'] = datetime.now() # Update setiap ada pesan
    text = update.message.text if update.message.text else ""

    # 1. Pilih Identitas
    if text in ['👧 cewe', '🧒 cowo']:
        user['identity'] = "cewe" if "cewe" in text else "cowo"
        await show_menu(context, user_id)
        return

    # 2. Ganti Identitas
    if text == '⚙️ Ganti Identitas':
        await start(update, context)
        return

    # 3. Logika Chatting & Stop
    if user['partner']:
        partner_id = user['partner']
        if text == '/stop' or text == '🛑 Berhenti':
            # Hapus Cache Partner
            user['partner'] = None
            if partner_id in user_data:
                user_data[partner_id]['partner'] = None

            await update.message.reply_text("Chat dihentikan. Cache dibersihkan.")
            try:
                await context.bot.send_message(partner_id, "Partner telah menghentikan obrolan.")
                await show_menu(context, partner_id)
            except: pass
            await show_menu(context, user_id)
        else:
            try:
                await update.message.copy(chat_id=partner_id)
            except:
                await update.message.reply_text("Gagal. Partner memblokir bot.")
        return

    # 4. Batal Cari
    if text == 'Batal':
        global queue
        queue = [q for q in queue if q['id'] != user_id]
        await update.message.reply_text("Pencarian dibatalkan.")
        await show_menu(context, user_id)
        return

    # 5. Mencari Pasangan
    if text in ['🔍 Cari cewe', '🔍 Cari cowo']:
        searching_for = "cewe" if "cewe" in text else "cowo"
        my_ident = user['identity']

        if not my_ident:
            await start(update, context)
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

            await context.bot.send_message(pid, msg, reply_markup=btn)
            await update.message.reply_text(msg, reply_markup=btn)
        else:
            queue[:] = [q for q in queue if q['id'] != user_id]
            queue.append({'id': user_id, 'identity': my_ident, 'searching_for': searching_for})
            await update.message.reply_text("Mencari...", reply_markup=ReplyKeyboardMarkup([['Batal']], resize_keyboard=True))

def main():
    app = Application.builder().token(TOKEN).build()

    # Menjalankan pengecekan timeout setiap 30 detik
    job_queue = app.job_queue
    job_queue.run_repeating(timeout_checker, interval=30, first=10)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("stop", handle_message))

    print(">>> BOT ANONIM 2026 BERJALAN <<<")
    app.run_polling()

if __name__ == "__main__":
    main()
