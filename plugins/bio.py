import re
import os
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatMemberStatus
from pyrogram.raw import functions
from motor.motor_asyncio import AsyncIOMotorClient
from antigcast import db, auto_delete_reply  # Integrasi Database & Worker Utama

# --- CONFIGURATION ---
# Pattern untuk mendeteksi link di Bio profil
LINK_PATTERN = r"(@\S+|http?://\S+|https?://\S+|t\.me/\S+|bit\.ly/\S+|linktr\.ee/\S+)"
config_db = db["status"]

# --- COMMAND: SETTING ON/OFF ---
@Client.on_message(filters.command("biocheck") & filters.group)
async def toggle_bio_check(client: Client, message: Message):
    # Cek Admin/Owner
    try:
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return
    except:
        return

    if len(message.command) < 2:
        res = await message.reply_text("❌ **Format Salah!**\nGunakan: `/biocheck on` atau `/biocheck off`")
        return await auto_delete_reply([res, message], delay=5)

    input_cmd = message.command[1].lower()

    if input_cmd == "on":
        await config_db.update_one(
            {"chat_id": message.chat.id},
            {"$set": {"bio_check": True}},
            upsert=True
        )
        res = await message.reply_text("✅ **Bio Link Detector DIAKTIFKAN.**\nSetiap member baru/lama yang chat akan diperiksa link di bionya.")
    elif input_cmd == "off":
        await config_db.update_one(
            {"chat_id": message.chat.id},
            {"$set": {"bio_check": False}},
            upsert=True
        )
        res = await message.reply_text("❌ **Bio Link Detector DINONAKTIFKAN.**")
    else:
        res = await message.reply_text("❓ Gunakan argumen `on` atau `off`.")

    # Hapus pesan perintah & balasan dalam 5 detik
    await auto_delete_reply([res, message], delay=5)


# --- CORE FILTER: BIO SCANNER ---
@Client.on_message(filters.group & ~filters.service, group=1)
async def main_bio_filter(client: Client, message: Message):
    # Abaikan jika tidak ada user, user bot, atau pesan dari admin
    if not message.from_user or message.from_user.is_bot:
        return

    cid = message.chat.id
    uid = message.from_user.id

    # 1. Cek apakah fitur aktif di grup ini via Database
    cfg = await config_db.find_one({"chat_id": cid})
    if not cfg or not cfg.get("bio_check", False):
        return

    # 2. Pengecualian Admin (Admin bebas pasang link apa saja di bio)
    try:
        member = await client.get_chat_member(cid, uid)
        if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return
    except:
        pass

    # 3. PENGECEKAN REAL-TIME KE SERVER TELEGRAM
    try:
        # Memanggil fungsi FullUser untuk melihat kolom 'About/Bio'
        full_user = await client.invoke(
            functions.users.GetFullUser(
                id=await client.resolve_peer(uid)
            )
        )

        u_bio = full_user.full_user.about

        if u_bio:
            # Jika ditemukan link di Bio profil user
            if re.search(LINK_PATTERN, u_bio, re.IGNORECASE):
                # Hapus pesan yang dikirim user tersebut
                await message.delete()

                # Kirim peringatan (opsional, akan hilang dalam 5 detik)
                # alert = await message.reply_text(f"⚠️ {message.from_user.mention}, pesan Anda dihapus karena terdapat link iklan di Bio profil Anda.")
                # await auto_delete_reply([alert], delay=5)

                print(f"🛡️ Bio-Hit: User {uid} dihapus pesannya di {cid}")
                return

    except Exception as e:
        # Jika bio disembunyikan (Privacy) dan grup mengaktifkan strict_mode
        if cfg.get("strict_mode", False):
            try:
                await message.delete()
            except:
                pass
        print(f"❌ Bio-Error [{cid}]: {e}")
