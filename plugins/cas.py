import httpx
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatMemberStatus
from antigcast import db, auto_delete_reply  # Pastikan auto_delete_reply diimpor dari config utama

# Konfigurasi
DELAY_NOTIF = 10
whitelist_col = db["whitelist_per_group"]

# --- FUNGSI HELPER CAS (ASYNCHRONOUS) ---
async def is_cas_banned(user_id: int) -> bool:
    """Mengecek status ban user di API CAS Chat."""
    url = f"https://api.cas.chat/check?user_id={user_id}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=5.0)
            if response.status_code == 200:
                return response.json().get("ok", False)
            return False
        except (httpx.RequestError, Exception):
            return False

# --- COMMAND: WHITELIST (WL) ---
@Client.on_message(filters.command("wl") & filters.group)
async def add_whitelist(client: Client, message: Message):
    # Cek apakah pengirim adalah Admin/Owner
    try:
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return
    except:
        return

    target_id = None
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
    elif len(message.command) > 1:
        try:
            target_id = int(message.command[1])
        except ValueError:
            msg = await message.reply_text("❌ **Error:** ID harus berupa angka.")
            return await auto_delete_reply([msg, message], delay=5)

    if target_id:
        await whitelist_col.update_one(
            {"user_id": target_id, "chat_id": message.chat.id},
            {"$set": {"status": "whitelisted"}},
            upsert=True
        )
        res = await message.reply_text(f"✅ **Whitelisted:** `{target_id}` aman dari CAS di grup ini.")
        await auto_delete_reply([res, message], delay=DELAY_NOTIF)

# --- COMMAND: UNWHITELIST (UNWL) ---
@Client.on_message(filters.command("unwl") & filters.group)
async def remove_whitelist(client: Client, message: Message):
    try:
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return
    except:
        return

    target_id = None
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
    elif len(message.command) > 1:
        try:
            target_id = int(message.command[1])
        except ValueError:
            msg = await message.reply_text("❌ **Error:** ID harus berupa angka.")
            return await auto_delete_reply([msg, message], delay=5)

    if target_id:
        result = await whitelist_col.delete_one({"user_id": target_id, "chat_id": message.chat.id})
        if result.deleted_count > 0:
            res = await message.reply_text(f"🗑️ **Unwhitelisted:** ID `{target_id}` dihapus.")
        else:
            res = await message.reply_text("❌ ID tidak ditemukan di daftar whitelist grup ini.")
        await auto_delete_reply([res, message], delay=DELAY_NOTIF)

# --- HANDLER OTOMATIS (CORE CAS) ---
@Client.on_message(filters.group & ~filters.service, group=-1)
async def cas_auto_mod(client: Client, message: Message):
    # Abaikan jika pesan dari bot itu sendiri atau tidak ada user_id (channel post)
    if not message.from_user or message.from_user.is_bot:
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    # 1. CEK DATABASE WHITELIST
    is_whitelisted = await whitelist_col.find_one({"user_id": user_id, "chat_id": chat_id})
    if is_whitelisted:
        return

    # 2. CEK STATUS ADMIN (Admin kebal CAS)
    try:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return
    except:
        # Jika bot bukan admin, dia tidak bisa ambil chat_member, abaikan
        pass

    # 3. CEK API CAS
    if await is_cas_banned(user_id):
        try:
            # Eksekusi Banned
            await client.ban_chat_member(chat_id, user_id)

            # Hapus pesan spam
            await message.delete()

            # Notifikasi ke grup
            alert = await client.send_message(
                chat_id,
                f"🛡️ **CAS Anti-Spam System**\n"
                f"**User:** {message.from_user.mention} (`{user_id}`)\n"
                f"**Action:** Banned\n"
                f"**Reason:** Terdaftar di database global CAS (Scammer/Spammer)."
            )

            # Gunakan worker untuk hapus notifikasi agar grup tetap bersih
            await auto_delete_reply([alert], delay=DELAY_NOTIF)

        except Exception as e:
            print(f"DEBUG: Gagal ban {user_id} karena {e}")
