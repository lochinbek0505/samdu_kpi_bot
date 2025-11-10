import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler
import requests
import json
import asyncio
from datetime import datetime

# Logging sozlamalari
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# API sozlamalari
BASE_URL = "http://185.217.131.207:8001/api"
LOGIN_URL = f"{BASE_URL}/users/loginme/"
CHATLIST_URL = f"{BASE_URL}/chats/chatlist/"
WEBAPP_URL = "https://samdu-kpi.web.app/"

# Conversation holatlar
USERNAME, PASSWORD = range(2)

# Foydalanuvchilar ma'lumotlari (xotirada saqlash)
user_data_storage = {}

class TelegramBot:
    def __init__(self, token):
        self.token = token
        self.application = Application.builder().token(token).build()
        self.checking_tasks = {}
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Bot boshlanishi"""
        user_id = update.effective_user.id
        
        # Agar foydalanuvchi allaqachon login qilgan bo'lsa
        if user_id in user_data_storage and 'access_token' in user_data_storage[user_id]:
            keyboard = [[InlineKeyboardButton("📱 Web App ni ochish", web_app=WebAppInfo(url=WEBAPP_URL))]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"Xush kelibsiz, {user_data_storage[user_id]['user']['first_name']}!\n"
                "Siz allaqachon tizimga kirgansiz.",
                reply_markup=reply_markup
            )
            # Xabarlarni tekshirishni boshlash
            if user_id not in self.checking_tasks:
                asyncio.create_task(self.check_messages_periodically(user_id, context))
            return ConversationHandler.END
        
        await update.message.reply_text(
            "🔐 Xush kelibsiz! Tizimga kirish uchun telefon raqamingizni kiriting.\n\n"
            "Masalan: +998901234567"
        )
        return USERNAME
    
    async def get_username(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Username/telefon olish"""
        username = update.message.text.strip()
        context.user_data['username'] = username
        
        await update.message.reply_text(
            "🔑 Endi parolingizni kiriting:"
        )
        return PASSWORD
    
    async def get_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Parol olish va login qilish"""
        password = update.message.text.strip()
        username = context.user_data.get('username')
        user_id = update.effective_user.id
        
        # Login qilish
        await update.message.reply_text("⏳ Tekshirilmoqda...")
        
        try:
            response = requests.post(
                LOGIN_URL,
                json={"username": username, "password": password},
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Ma'lumotlarni saqlash
                user_data_storage[user_id] = {
                    'access_token': data['access'],
                    'refresh_token': data['refresh'],
                    'user': data['user'],
                    'username': username
                }
                
                # Web App tugmasi
                keyboard = [[InlineKeyboardButton("📱 Web App ni ochish", web_app=WebAppInfo(url=WEBAPP_URL))]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"✅ Muvaffaqiyatli tizimga kirdingiz!\n\n"
                    f"👤 Ism: {data['user']['first_name']} {data['user']['last_name']}\n"
                    f"📞 Telefon: {data['user']['phone']}\n"
                    f"💼 Lavozim: {data['user']['position']}\n"
                    f"⭐ Reyting: {data['user']['rating']}\n\n"
                    f"Xabarlar avtomatik ravishda tekshiriladi.",
                    reply_markup=reply_markup
                )
                
                # Xabarlarni tekshirishni boshlash
                asyncio.create_task(self.check_messages_periodically(user_id, context))
                
                return ConversationHandler.END
            else:
                await update.message.reply_text(
                    "❌ Login yoki parol noto'g'ri. Qaytadan urinib ko'ring.\n"
                    "Telefon raqamingizni kiriting:"
                )
                return USERNAME
                
        except Exception as e:
            logger.error(f"Login xatosi: {e}")
            await update.message.reply_text(
                "❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.\n"
                "/start - Boshlash"
            )
            return ConversationHandler.END
    
    async def check_messages_periodically(self, user_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Xabarlarni davriy ravishda tekshirish"""
        if user_id in self.checking_tasks:
            return
        
        self.checking_tasks[user_id] = True
        previous_unread = {}
        
        while user_id in user_data_storage and user_id in self.checking_tasks:
            try:
                # Token olish
                access_token = user_data_storage[user_id]['access_token']
                
                # Chatlist API dan ma'lumot olish
                response = requests.get(
                    CHATLIST_URL,
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                
                if response.status_code == 200:
                    chats = response.json()
                    
                    # Har bir chat uchun tekshirish
                    for chat in chats:
                        chat_user_id = chat['user']['id']
                        unread_count = chat['unread_count']
                        
                        # Agar yangi xabar bo'lsa
                        if unread_count > 0:
                            prev_count = previous_unread.get(chat_user_id, 0)
                            
                            if unread_count > prev_count:
                                # Yangi xabar haqida xabar yuborish
                                keyboard = [[
                                    InlineKeyboardButton(
                                        "📬 Xabarni o'qish",
                                        web_app=WebAppInfo(url=WEBAPP_URL)
                                    )
                                ]]
                                reply_markup = InlineKeyboardMarkup(keyboard)
                                
                                department_text = chat['user']['department'] if chat['user']['department'] else "Ko'rsatilmagan"
                                
                                await context.bot.send_message(
                                    chat_id=user_id,
                                    text=f"📨 Sizda yangi xabar bor!\n\n"
                                         f"👤 Kimdan: {chat['user']['firstname']} {chat['user']['lastname']}\n"
                                         f"💼 Lavozim: {chat['user']['role']}\n"
                                         f"📊 Bo'lim: {department_text}\n"
                                         f"📮 O'qilmagan xabarlar: {unread_count}\n"
                                         f"🕐 Oxirgi xabar: {chat['last_time'][:19].replace('T', ' ')}",
                                    reply_markup=reply_markup
                                )
                        
                        previous_unread[chat_user_id] = unread_count
                
                elif response.status_code == 401:
                    # Token muddati tugagan
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="⚠️ Sessiya muddati tugadi. Iltimos, qaytadan login qiling.\n/start"
                    )
                    if user_id in user_data_storage:
                        del user_data_storage[user_id]
                    break
                    
            except Exception as e:
                logger.error(f"Xabarlarni tekshirishda xatolik: {e}")
            
            # 5 soniya kutish
            await asyncio.sleep(5)
        
        # Taskni o'chirish
        if user_id in self.checking_tasks:
            del self.checking_tasks[user_id]
    
    async def logout(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Tizimdan chiqish"""
        user_id = update.effective_user.id
        
        if user_id in user_data_storage:
            del user_data_storage[user_id]
        
        if user_id in self.checking_tasks:
            del self.checking_tasks[user_id]
        
        await update.message.reply_text(
            "👋 Tizimdan chiqdingiz. Qaytadan kirish uchun /start buyrug'ini ishlating."
        )
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Foydalanuvchi holati"""
        user_id = update.effective_user.id
        
        if user_id not in user_data_storage:
            await update.message.reply_text(
                "❌ Siz tizimga kirmagansiz. /start buyrug'ini ishlating."
            )
            return
        
        user = user_data_storage[user_id]['user']
        keyboard = [[InlineKeyboardButton("📱 Web App ni ochish", web_app=WebAppInfo(url=WEBAPP_URL))]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📊 Sizning ma'lumotlaringiz:\n\n"
            f"👤 Ism: {user['first_name']} {user['last_name']}\n"
            f"📞 Telefon: {user['phone']}\n"
            f"💼 Lavozim: {user['position']}\n"
            f"🏢 Bo'lim ID: {user['department']}\n"
            f"⭐ Reyting: {user['rating']}\n"
            f"⭐ Qo'shimcha reyting: {user['rating_extra']}\n"
            f"🎯 Maksimal ball: {user['max_ball']}",
            reply_markup=reply_markup
        )
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Bekor qilish"""
        await update.message.reply_text(
            "❌ Bekor qilindi. /start - Qaytadan boshlash"
        )
        return ConversationHandler.END
    
    def run(self):
        """Botni ishga tushirish"""
        # Conversation handler
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start)],
            states={
                USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_username)],
                PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_password)],
            },
            fallbacks=[CommandHandler('cancel', self.cancel)],
        )
        
        # Handlerlarni qo'shish
        self.application.add_handler(conv_handler)
        self.application.add_handler(CommandHandler('logout', self.logout))
        self.application.add_handler(CommandHandler('status', self.status))
        
        # Botni ishga tushirish
        logger.info("Bot ishga tushdi...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

# Asosiy qism
if __name__ == '__main__':
    # Bot tokeni
    BOT_TOKEN = "8526641202:AAHiYyApHnbnTwj2koBZAw0HjuLbtcDI1Sw"
    
    bot = TelegramBot(BOT_TOKEN)
    bot.run()