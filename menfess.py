import logging, html, os, json, sys, subprocess, asyncio, signal
import requests  # <--- WAJIB TAMBAHKAN INI
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, MessageOriginChannel,
    LinkPreviewOptions # Pastikan ini ada di sini
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler, Defaults
)
from telegram.constants import ParseMode, ChatType

# --- 1. KONFIGURASI UTAMA ---
TOKEN = os.getenv("BOT_TOKEN", '8412972026:AAHkUMziUGDo__JGGoQUf8bKKnazX4P-sV8')
DEFAULT_CHANNEL = os.getenv("CH_ID", '@GALLERY_TPV')
MAIN_OWNER_ID = 7411619973
OWNER_ID = int(os.getenv("OWN_ID", MAIN_OWNER_ID))
URL_GITHUB = 'https://raw.githubusercontent.com/absurd100/test/main/balasan.txt'

IS_CLONE = os.getenv("IS_CLONE", "False") == "True"
suffix = f"_{OWNER_ID}" if IS_CLONE else ""

USER_DATA_FILE = f"user_stats{suffix}.json"
CONFIG_FILE = f"bot_config{suffix}.json"
USERS_LIST_FILE = f"all_users{suffix}.json"
BAN_FILE = f"banned_users{suffix}.json"
CLONE_DB = "permanent_clones.json"
POST_MAP_FILE = "post_mapping.json"

DEFAULT_TEMPLATE = "✨ <b>𝐍𝐄𝐖 𝐌𝐄𝐍𝐅𝐄𝐒𝐒!</b> ✨\n\n<blockquote>{TEXT}</blockquote>\n\n• <b>Sender:</b> {SENDER}\n<b>• Via :</b> {BOT_LINK}"

# --- KEYBOARD ---
MAIN_KEYBOARD = ReplyKeyboardMarkup([['👤 Kirim Anonim', '📝 Tampilkan Nama'], ['💳 Isi Kuota (Bayar)', '📊 Cek Kuota'], ['🤖 CLONE', '🇮🇩 ADMIN MENU']], resize_keyboard=True)
OWNER_KEYBOARD = ReplyKeyboardMarkup([['⚙️ CUSTOM POST', '📢 BROADCAST'], ['🔓 MODE GRATIS', '🔒 MODE BAYAR'], ['🖼️ SET QRIS', '👤 MENU USER'], ['📋 LIST CLONE']], resize_keyboard=True)
CLONE_ADMIN_KEYBOARD = ReplyKeyboardMarkup([
    ['⚙️ CUSTOM POST', '📢 BROADCAST'],
    ['🔓 MODE GRATIS', '🔒 MODE BAYAR'],
    ['🖼️ SET QRIS', '👤 MENU USER'],
    ['📋 TUTORIAL']
], resize_keyboard=True)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- 2. DATABASE HELPER ---
def load_json(file_name):
    if not os.path.exists(file_name):
        default = [] if any(x in file_name for x in ["all_users", "clones", "permanent", "banned"]) else {}
        with open(file_name, "w") as f: json.dump(default, f)
        return default
    with open(file_name, "r") as f:
        try:
            data = json.load(f)
            return data if data is not None else []
        except: return []

def save_json(file_name, data):
    with open(file_name, "w") as f: json.dump(data, f, indent=4)

def is_banned(uid):
    return str(uid) in load_json(BAN_FILE)

# --- 3. CALLBACK HANDLER ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != OWNER_ID: return
    data = query.data

    if data.startswith("ban_"):
        uid = data.split("_")[1]
        banned = load_json(BAN_FILE)
        if uid not in banned: banned.append(uid); save_json(BAN_FILE, banned)
        await query.answer("User Berhasil di Ban!")
        await query.edit_message_caption(caption=query.message.caption + "\n\n🚫 <b>STATUS: BANNED</b>", parse_mode=ParseMode.HTML)

    elif data == "reset_tpl":
        cfg = load_json(CONFIG_FILE)
        cfg["post_template"] = DEFAULT_TEMPLATE
        save_json(CONFIG_FILE, cfg)
        await query.answer("✅ Template berhasil direset!", show_alert=True)
        await query.message.reply_text("✨ <b>RESET BERHASIL!</b>\nTemplate menfess telah dikembalikan ke pengaturan awal.", parse_mode=ParseMode.HTML)

    elif data.startswith("unban_"):
        uid = data.split("_")[1]
        banned = load_json(BAN_FILE)
        if uid in banned: banned.remove(uid); save_json(BAN_FILE, banned)
        await query.answer("Ban User Dicabut!")
        await query.edit_message_caption(caption=query.message.caption + "\n\n✅ <b>STATUS: AKTIF</b>", parse_mode=ParseMode.HTML)

    elif data.startswith("delclone_"):
        try:
            idx = int(data.split("_")[1])
            clones = load_json(CLONE_DB)
            if 0 <= idx < len(clones):
                removed = clones.pop(idx)
                if removed.get('pid'):
                    try: os.kill(removed['pid'], signal.SIGTERM)
                    except: pass
                save_json(CLONE_DB, clones)
                await query.edit_message_text(f"✅ Bot <b>@{removed.get('username')}</b> berhasil dimatikan dan dihapus.", parse_mode=ParseMode.HTML)
        except: await query.answer("Gagal menghapus clone")

    elif data.startswith("count_"):
        _, tid, val = data.split("_")
        val = max(1, int(val))
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("➖", callback_data=f"count_{tid}_{val-1}"), InlineKeyboardButton(f"💎 {val}", callback_data="n"), InlineKeyboardButton("➕", callback_data=f"count_{tid}_{val+1}")], [InlineKeyboardButton("✅ KONFIRMASI", callback_data=f"acc_{tid}_{val}")]])
        await query.edit_message_reply_markup(reply_markup=kb)

    elif data.startswith("acc_"):
        _, tid, val = data.split("_")
        db_user = load_json(USER_DATA_FILE)
        if tid not in db_user: db_user[tid] = {"kuota": 0}
        db_user[tid]["kuota"] += int(val)
        save_json(USER_DATA_FILE, db_user)
        await query.edit_message_caption(caption=query.message.caption + f"\n\n✅ <b>BERHASIL +{val}</b>")
        try: await context.bot.send_message(tid, f"✅ Pembayaran diterima! +{val} kuota ditambahkan.")
        except: pass

    elif data == "cp_tpl":
        context.user_data['edit_mode'] = 'template'
        await query.message.reply_text("📝 Kirim template baru.\nGunakan {TEXT} untuk kolom teks kiriman & {SENDER} untuk menampilkan pengirim.\nbot ini support html format")

    elif data == "cp_ch":
        context.user_data['edit_mode'] = 'channel'
        await query.message.reply_text("📢 Kirim username channel baru (@Channel) atau ID Channel (-100xxx).")

    await query.answer()

# --- 4. NOTIFIKASI KOMENTAR (FIX LINK PRIVAT 2026) ---
async def handle_comments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]: return
    if not update.message or not update.message.reply_to_message: return
    if update.message.text and update.message.text.startswith('/'): return

    msg_reply = update.message.reply_to_message
    original_msg_id = None

    # Deteksi ID Pesan Asli dari Channel (Januari 2026)
    if msg_reply.forward_origin:
        original_msg_id = getattr(msg_reply.forward_origin, 'message_id', None)
    if not original_msg_id: return

    post_map = load_json(POST_MAP_FILE)
    sender_id = post_map.get(str(original_msg_id))

    if sender_id:
        try:
            cfg = load_json(CONFIG_FILE)
            target = cfg.get("target_channel", DEFAULT_CHANNEL)

            # ID Pesan Komentar saat ini di grup
            comment_id = update.message.message_id
            # ID Pesan yang di-reply (Pesan bot di grup)
            thread_id = msg_reply.message_id

            # Mengambil ID Grup Tanpa -100
            chat_id_clean = str(update.effective_chat.id).replace('-100', '')

            # FORMAT LINK YANG ANDA MINTA (UNTUK PRIVAT):
            # https://t.me/2522456972/189174?thread=189173
            link_komentar = f"https://t.me/c/{chat_id_clean}/{comment_id}?thread={thread_id}"

            # Link ke Postingan Asli (Channel Privat)
            target_clean = str(target).replace('-100', '').replace('@', '')
            link_asli = f"https://t.me/c/{target_clean}/{original_msg_id}" if str(target).startswith('-100') else f"https://t.me/c/{target_clean}/{original_msg_id}"

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Lihat Komentar", url=link_komentar)],
                [InlineKeyboardButton("📝 Postingan Asli ↗️", url=link_asli)]
            ])

            await context.bot.send_message(
                chat_id=sender_id,
                text=f"🔔 <b>Notifikasi!</b>\nSeseorang baru saja mengomentari Menfess Anda.",
                reply_markup=kb,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            print(f"Error Notif: {e}")

# --- 5. HANDLING PESAN UTAMA ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message: return
    if update.effective_chat.type != ChatType.PRIVATE: return

    uid_int = update.effective_user.id
    uid = str(uid_int)
    msg = update.message
    text = msg.text or msg.caption or ""
    if is_banned(uid_int): return

    # MENU OWNER
    if uid_int == MAIN_OWNER_ID:
        if text == '🇮🇩 ADMIN MENU': return await msg.reply_text("<i>kembali ke mode owner</i>", reply_markup=OWNER_KEYBOARD)

        if text == '📋 LIST CLONE':
            clones = load_json(CLONE_DB)
            if not clones: return await msg.reply_text("Belum ada bot yang dikloning.")
            txt = "📋 <b>DAFTAR BOT CLONE</b>\n\n"
            kb = [[InlineKeyboardButton(f"❌ Matikan @{c.get('username')}", callback_data=f"delclone_{i}")] for i, c in enumerate(clones)]
            return await msg.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

    if uid_int == OWNER_ID:
        if text == '🇮🇩 ADMIN MENU':
            markup = CLONE_ADMIN_KEYBOARD if IS_CLONE else OWNER_KEYBOARD
            return await msg.reply_text("<i>kembali ke mode owner</i>", reply_markup=markup)
        if text == '📋 TUTORIAL':
            try:
                response = requests.get(URL_GITHUB, timeout=10)
                if response.ok:
                    await update.message.reply_text(text=response.text, parse_mode=ParseMode.HTML, link_preview_options=LinkPreviewOptions(is_disabled=True), reply_markup=CLONE_ADMIN_KEYBOARD)
                    return
            except Exception as e:
                await update.message.reply_text(f"Koneksi Error: {e}")
                return

        if text == '⚙️ CUSTOM POST':
            cfg = load_json(CONFIG_FILE)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("📝 Template", callback_data="cp_tpl"), InlineKeyboardButton("📢 Channel", callback_data="cp_ch")], [InlineKeyboardButton("🔄 Reset Template ke Default", callback_data="reset_tpl")]])
            return await msg.reply_text(f"⚙️ <b>CUSTOM POST</b>\ndi sini kamu bisa mengatur tampilan pesan terkirim sesuai keinginan kamu\n1. klik template untuk mengatur teks kiriman ke channel\n2. klik channel untuk menentukan channel tujuan menfess\n3. channel tujuan saat ini : {cfg.get('target_channel', DEFAULT_CHANNEL)}\n\n<blockquote>ingat untuk menjadikan bot kamu admin di channel kamu agar pesan terkirim</blockquote>", reply_markup=kb, parse_mode=ParseMode.HTML)
        if text == '📢 BROADCAST':
            context.user_data['waiting_bc'] = True; return await msg.reply_text("📢 Silakan kirim pesan broadcast:")
        elif text == '🖼️ SET QRIS':
            context.user_data['step'] = 'SET_QRIS'; return await msg.reply_text("🖼️ <b>Setup Payment</b>\nKirimkan Link Foto QRIS Anda (Contoh: telegra.ph).")
        if text == '🔓 MODE GRATIS':
            cfg = load_json(CONFIG_FILE); cfg["gratis"] = True; save_json(CONFIG_FILE, cfg); return await msg.reply_text("✅ Mode GRATIS aktif!")
        if text == '🔒 MODE BAYAR':
            cfg = load_json(CONFIG_FILE); cfg["gratis"] = False; save_json(CONFIG_FILE, cfg); return await msg.reply_text("✅ Mode BERBAYAR aktif!")
        if text == '👤 MENU USER': return await msg.reply_text("Menu User Aktif.", reply_markup=MAIN_KEYBOARD)

    if context.user_data.get('waiting_bc'):
        context.user_data.pop('waiting_bc'); users = load_json(USERS_LIST_FILE)
        for u in users:
            try: await context.bot.send_message(u, text); await asyncio.sleep(0.05)
            except: continue
        return await msg.reply_text("✅ Broadcast selesai.")

    if context.user_data.get('step') == 'SET_QRIS':
        context.user_data.pop('step'); cfg = load_json(CONFIG_FILE); cfg["qris_link"] = text; save_json(CONFIG_FILE, cfg)
        return await msg.reply_text(f"✅ <b>QRIS Updated!</b>\nLink terpasang: {text}")

    if 'edit_mode' in context.user_data:
        mode = context.user_data.pop('edit_mode'); cfg = load_json(CONFIG_FILE)
        if mode == 'template': cfg["post_template"] = text
        elif mode == 'channel': cfg["target_channel"] = text
        save_json(CONFIG_FILE, cfg); return await msg.reply_text("✨ <b>Update Berhasil!</b>")

    if context.user_data.get('waiting_clone'):
        token_input = text.strip(); context.user_data.pop('waiting_clone')
        try:
            from telegram import Bot
            temp_bot = Bot(token_input); bot_info = await temp_bot.get_me()
            env = os.environ.copy(); env.update({"BOT_TOKEN": token_input, "IS_CLONE": "True", "OWN_ID": str(uid_int)})
            proc = subprocess.Popen([sys.executable, sys.argv[0]], env=env)
            clones = load_json(CLONE_DB); clones.append({"token": token_input, "owner": uid_int, "pid": proc.pid, "username": bot_info.username}); save_json(CLONE_DB, clones)
            return await msg.reply_text(f"✅ <b>Clone Aktif!</b>\n🤖 Bot: {bot_info.first_name}\n🆔 @{bot_info.username}", parse_mode=ParseMode.HTML)
        except: return await msg.reply_text(f"❌ Gagal: Token tidak valid.")
# --- GUNAKAN INI SEBAGAI GANTINYA ---
    if context.user_data.get('step') == 'PAY' and msg.photo:
        context.user_data.pop('step') # Selesaikan mode bayar
        kb_owner = InlineKeyboardMarkup([[InlineKeyboardButton("➖", callback_data=f"count_{uid}_4"), InlineKeyboardButton("💎 5", callback_data="n"), InlineKeyboardButton("➕", callback_data=f"count_{uid}_6")], [InlineKeyboardButton("✅ KONFIRMASI", callback_data=f"acc_{uid}_5")]])
        await context.bot.send_photo(OWNER_ID, photo=msg.photo[-1].file_id, caption=f"💳 <b>BUKTI PEMBAYARAN</b>\n🆔 ID: <code>{uid}</code>", reply_markup=kb_owner, parse_mode=ParseMode.HTML)
        return await msg.reply_text("✅ Bukti pembayaran telah terkirim ke owner. Mohon tunggu konfirmasi.")

    if text == '🤖 CLONE':
        context.user_data['waiting_clone'] = True; return await msg.reply_text("🤖 Kirim <b>Token Bot</b> dari @BotFather:", parse_mode=ParseMode.HTML)
    if text == '📊 Cek Kuota':
        db = load_json(USER_DATA_FILE); return await msg.reply_text(f"📊 Kuota: {db.get(uid, {}).get('kuota', 0)}")
    elif text == '💳 Isi Kuota (Bayar)':
        cfg = load_json(CONFIG_FILE); qris = cfg.get("qris_link", "Belum diset oleh owner.")
        context.user_data['step'] = 'PAY'
        cap = f"💳 <b>Topup Kuota Menfess</b>\n\n1. Silakan scan QRIS di atas atau klik link:\n 🔗 {qris}\n\n2. Selesaikan pembayaran.\n3. <b>Kirim bukti screenshot</b> ke chat ini."
        if "http" in qris: return await context.bot.send_photo(uid_int, qris, caption=cap, parse_mode=ParseMode.HTML)
        else: return await msg.reply_text(cap, parse_mode=ParseMode.HTML)
    if text == '🇮🇩 ADMIN MENU':
        return await msg.reply_text("kamu bukan admin clone\nclone bot kamu terlebih dahulu")
    if text == '👤 Kirim Anonim':
        context.user_data['mode'] = 'anonim'; return await msg.reply_text("yeyyyy kamu pilih mode anonim 👤")
    if text == '📝 Tampilkan Nama':
        context.user_data['mode'] = 'nama'; return await msg.reply_text("yuuhuu kirim menfessmu & namamu akan terpampang di sana 😎")

    list_tombol = ['👤 Kirim Anonim', '📝 Tampilkan Nama', '💳 Isi Kuota (Bayar)', '📊 Cek Kuota', '🤖 CLONE', '⚙️ CUSTOM POST', '📢 BROADCAST', '🔓 MODE GRATIS', '🔒 MODE BAYAR', '👤 MENU USER', '📋 LIST CLONE', '🇮🇩 ADMIN MENU']
    if not text.startswith('/') and text not in list_tombol:
        db_user = load_json(USER_DATA_FILE); cfg = load_json(CONFIG_FILE)
        kuota = db_user.get(uid, {}).get('kuota', 0)
        if uid_int != OWNER_ID and not cfg.get("gratis", False) and kuota <= 0: return await msg.reply_text("❌ Kuota habis!", reply_markup=MAIN_KEYBOARD)
        bot_info = await context.bot.get_me()
        mode = context.user_data.pop('mode', 'anonim')
        full_name = html.escape(update.effective_user.full_name)
        sender = "Anonim 🏴‍☠️" if mode == "anonim" else f"<a href='tg://user?id={uid_int}'>{full_name}</a>"
        bot_link = f"<a href='https://t.me/{bot_info.username}?start=help'>{html.escape(bot_info.first_name)}</a>"
        isi_menfess = text if text else (msg.caption if msg.caption else "(Kirim Foto)")
        template_asli = cfg.get("post_template", DEFAULT_TEMPLATE)
        final_text = template_asli.replace("{TEXT}", isi_menfess).replace("{SENDER}", sender).replace("{BOT_LINK}", bot_link)
        target = cfg.get("target_channel", DEFAULT_CHANNEL)
        try:
            if msg.photo: snt = await context.bot.send_photo(target, msg.photo[-1].file_id, caption=final_text, parse_mode=ParseMode.HTML)
            else: snt = await context.bot.send_message(target, text=final_text, parse_mode=ParseMode.HTML, link_preview_options=LinkPreviewOptions(is_disabled=True))
            p_map = load_json(POST_MAP_FILE); p_map[str(snt.message_id)] = uid_int; save_json(POST_MAP_FILE, p_map)
            if uid_int != OWNER_ID and not cfg.get("gratis", False):
                db_user[uid]['kuota'] -= 1; save_json(USER_DATA_FILE, db_user)
            log_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚫 BAN", callback_data=f"ban_{uid}"), InlineKeyboardButton("✅ UNBAN", callback_data=f"unban_{uid}")]])
            if msg.photo: await context.bot.send_photo(OWNER_ID, msg.photo[-1].file_id, caption=f"📩 LOG: {uid}", reply_markup=log_kb, parse_mode=ParseMode.HTML)
            else: await context.bot.send_message(OWNER_ID, f"📩 LOG: {uid}\n{text[:100]}", reply_markup=log_kb, parse_mode=ParseMode.HTML)
            target_link = str(target).replace('@', '').replace('-100', '')
            link = f"https://t.me/{'c/' if str(target).startswith('-100') else ''}{target_link}/{snt.message_id}"
            await msg.reply_text(f"✅ Terkirim!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Lihat Postingan ↗️", url=link)]]))
        except Exception as e:
            await msg.reply_text(f"<i>channel menfess tidak terkonek dengan bot\nhubungi owner... jangan lupa dijadiin admin channel yah botnya 🤣</i>")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE: return
    uid_int = update.effective_user.id; users = load_json(USERS_LIST_FILE)
    full_name = html.escape(update.effective_user.full_name)
    if str(uid_int) not in users: users.append(str(uid_int)); save_json(USERS_LIST_FILE, users)
    db = load_json(USER_DATA_FILE);
    if str(uid_int) not in db: db[str(uid_int)] = {"kuota": 0}; save_json(USER_DATA_FILE, db)
    kb = OWNER_KEYBOARD if (uid_int == MAIN_OWNER_ID and not IS_CLONE) else (CLONE_ADMIN_KEYBOARD if uid_int == OWNER_ID else MAIN_KEYBOARD)
    await update.message.reply_text(f"👋 Halo! {full_name}\nID: {uid_int}\nselamat datang di bot menfess canggih 😎\n\n<blockquote>created by Ano</blockquote>", reply_markup=kb)

def main():
    app = Application.builder().token(TOKEN).defaults(Defaults(parse_mode=ParseMode.HTML)).build()
    if not IS_CLONE:
        clones = load_json(CLONE_DB)
        for c in clones:
            try:
                env = os.environ.copy(); env.update({"BOT_TOKEN": c['token'], "OWN_ID": str(c.get('owner', OWNER_ID)), "IS_CLONE": "True"})
                subprocess.Popen([sys.executable, sys.argv[0]], env=env)
            except: continue
    app.add_handler(CommandHandler("start", start, filters=filters.ChatType.PRIVATE))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & (~filters.COMMAND), handle_comments))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (~filters.COMMAND), handle_message))
    logging.info("Bot Berjalan..."); app.run_polling()

if __name__ == '__main__':
    main()
