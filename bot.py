# -*- coding: utf-8 -*-
"""
============================================================
ربات فروش کانفیگ - نسخه حرفه‌ای (Full Rewrite - v3)
============================================================

تغییرات نسبت به نسخه قبلی (v2) طبق درخواست جدید:

الف) دکمه انصراف در پنل ادمین:
   - در تمام مراحل چندمرحله‌ای پنل ادمین (افزودن/ویرایش محصول،
     افزودن موجودی متنی/عکسی، مدیریت کانفیگ تست، کد تخفیف، کارت‌ها،
     مدیریت ادمین‌ها، تنظیمات) یک دکمه اینلاین «❌ انصراف» اضافه شده
     که با /cancel قبلی هم‌زمان کار می‌کند (admin_cancel).

ب) آیدی پشتیبانی و مقدار جایزه دعوت:
   - هیچ‌کدام دیگر در کد ثابت نیستند. هر دو در جدول settings در
     دیتابیس نگه داشته می‌شوند و فقط از طریق «پنل رئیس -> ⚙️ تنظیمات
     ربات» قابل تغییر هستند.

ج) دسترسی‌های جزئی ادمین‌ها:
   - جدول admin_permissions اضافه شد. هر ادمین برای هر بخش
     (محصولات، کانفیگ تست، کد تخفیف، مشتری‌ها، سفارش‌ها، نمایندگی،
     کارت‌ها، مدیریت ادمین‌ها) یک دسترسی جدا دارد.
   - رئیس از «👨‍💼 مدیریت ادمین‌ها -> لیست و دسترسی‌ها -> 🔧 تنظیم
     دسترسی‌ها» می‌تواند هر بخش را برای هر ادمین روشن/خاموش کند؛
     یعنی هم می‌تواند دسترسی یک ادمین را کم کند، هم می‌تواند
     دسترسی‌های مخصوص رئیس (مثل مدیریت کارت‌ها یا مدیریت ادمین‌ها)
     را به یک ادمین خاص بدهد.
   - دسترسی‌های پیش‌فرض برای ادمین تازه اضافه‌شده: محصولات، کانفیگ
     تست، کد تخفیف، مشتری‌ها، سفارش‌ها، نمایندگی (بدون کارت‌ها و
     مدیریت ادمین‌ها، مگر رئیس صریحاً اضافه کند).
   - توجه: اگر دسترسی «مدیریت ادمین‌ها» به یک ادمین داده شود، آن
     ادمین می‌تواند ادمین جدید بسازد و دسترسی‌ها را تغییر دهد. این
     یک ابزار قدرتمند است و باید با احتیاط داده شود.

============================================================
"""

import asyncio
import logging
import os
import random
from html import escape
from datetime import datetime

import aiosqlite

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)


# ============================================================
# تنظیمات اصلی
# توضیح: دیگر هیچ شماره کارت، آیدی پشتیبانی، مقدار جایزه دعوت یا
# لیست ادمینی در این بخش وجود ندارد. همه این‌ها از طریق ربات و
# توسط رئیس (SUPER_ADMIN_ID) مدیریت می‌شوند.
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "8620450006:AAEhhZ68ZN5ebE4mCnd0mxRRFv_litzjifk").strip()

REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@spayder_man_vpn").strip()
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/spayder_man_vpn").strip()

# فقط رئیس اصلی - دسترسی کامل و بدون قید و شرط به همه بخش‌ها.
# این تنها آیدی است که همچنان به‌صورت ثابت در کد باقی می‌ماند،
# چون رئیس اصلی نمی‌تواند از طریق پنل خودش را حذف کند.
SUPER_ADMIN_ID = 7237811387

# دیتابیس
DATABASE = "config_shop.db"

# پروکسی (در صورت نیاز)
PROXY_URL = os.getenv("PROXY_URL", "").strip()

# حداقل موجودی کیف پول برای درخواست نمایندگی (تومان)
RESELLER_MIN_WALLET = 500000

# حداکثر تعداد کارت بانکی قابل ثبت
MAX_CARDS = 20

# نام کاربری ربات - بعد از اجرا خودکار پر می‌شود (برای ساخت لینک دعوت)
BOT_USERNAME = ""

# کش درون‌حافظه‌ای ادمین‌ها - در استارت ربات از دیتابیس پر می‌شود
# و با افزودن/حذف ادمین توسط رئیس به‌روز می‌ماند.
ADMIN_IDS_CACHE: set[int] = set()

# کش درون‌حافظه‌ای دسترسی‌های جزئی هر ادمین: {user_id: {perm1, perm2, ...}}
ADMIN_PERMISSIONS_CACHE: dict[int, set[str]] = {}

# کش درون‌حافظه‌ای تنظیمات قابل ویرایش رئیس (آیدی پشتیبانی، جایزه دعوت و ...)
SETTINGS_CACHE: dict[str, str] = {}

# مقادیر پیش‌فرض تنظیمات، فقط برای زمانی که هنوز در دیتابیس ثبت نشده باشند
DEFAULT_SETTINGS = {
    "support_username": "",
    "referral_reward": "25000",
}

# لیست کامل بخش‌های قابل واگذاری به ادمین‌ها (کلید -> برچسب فارسی)
PERMISSIONS: dict[str, str] = {
    "products": "📦 محصولات و موجودی",
    "test_configs": "🧪 کانفیگ تست",
    "discounts": "🏷 کدهای تخفیف",
    "customers": "👥 لیست مشتری‌ها",
    "orders": "🧾 سفارش‌ها (تایید/رد)",
    "resellers": "🤝 درخواست‌های نمایندگی",
    "cards": "💳 مدیریت کارت‌ها",
    "admins": "👨‍💼 مدیریت ادمین‌ها",
}
# دسترسی‌های پیش‌فرض برای ادمینی که تازه توسط رئیس اضافه می‌شود.
# کارت‌ها و مدیریت ادمین‌ها عمداً پیش‌فرض نیستند چون حساس‌ترند.
DEFAULT_ADMIN_PERMISSIONS: set[str] = {
    "products", "test_configs", "discounts", "customers", "orders", "resellers",
}


# ============================================================
# LOG
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================
# Dispatcher
# ============================================================

dp = Dispatcher()


# ============================================================
# STATES
# ============================================================

class PaymentFlow(StatesGroup):
    """
    جریان مشترک پرداخت برای سه حالت:
      flow_type = purchase   -> خرید محصول
      flow_type = renewal    -> تمدید سرویس
      flow_type = wallet_charge -> شارژ کیف پول
    """
    waiting_discount_code = State()
    waiting_receipt = State()


class ProductStates(StatesGroup):
    waiting_code = State()
    waiting_name = State()
    waiting_price = State()
    waiting_description = State()
    waiting_photo = State()


class StockStates(StatesGroup):
    waiting_product_code = State()
    waiting_config = State()


class BulkPhotoStockStates(StatesGroup):
    waiting_product_code = State()
    waiting_photos = State()


class EditProductStates(StatesGroup):
    waiting_code = State()
    waiting_field = State()
    waiting_value = State()


class TestConfigStates(StatesGroup):
    waiting_config = State()


class TestConfigBulkPhotoStates(StatesGroup):
    waiting_photos = State()


class DiscountStates(StatesGroup):
    waiting_code = State()
    waiting_type = State()
    waiting_value = State()
    waiting_max_uses = State()


class RedeemCodeStates(StatesGroup):
    waiting_code = State()


class CardStates(StatesGroup):
    waiting_number = State()
    waiting_owner = State()


class WalletChargeAmountStates(StatesGroup):
    waiting_amount = State()


class AdminManageStates(StatesGroup):
    waiting_id = State()


class SettingsStates(StatesGroup):
    waiting_support_username = State()
    waiting_referral_reward = State()


# ============================================================
# مدیریت دسترسی
# توضیح: is_admin/has_permission به‌صورت سینک (غیر async) روی کش
# درون‌حافظه‌ای کار می‌کنند تا نیازی نباشد همه‌جای کد async شود.
# این کش‌ها در ابتدای اجرای ربات از دیتابیس پر می‌شوند و با هر
# تغییر توسط رئیس، بلادرنگ به‌روزرسانی می‌شوند.
# ============================================================

def is_admin(user_id: int) -> bool:
    if SUPER_ADMIN_ID != 0 and user_id == SUPER_ADMIN_ID:
        return True
    return user_id in ADMIN_IDS_CACHE


def is_super_admin(user_id: int) -> bool:
    return SUPER_ADMIN_ID != 0 and user_id == SUPER_ADMIN_ID


def has_permission(user_id: int, permission: str) -> bool:
    """رئیس همیشه به همه‌چیز دسترسی دارد؛ ادمین‌های عادی فقط طبق کش."""
    if is_super_admin(user_id):
        return True
    return permission in ADMIN_PERMISSIONS_CACHE.get(user_id, set())


def all_admin_ids() -> set:
    ids = set(ADMIN_IDS_CACHE)
    if SUPER_ADMIN_ID != 0:
        ids.add(SUPER_ADMIN_ID)
    return ids


async def load_admins():
    """در استارت ربات، لیست ادمین‌ها از دیتابیس در کش لود می‌شود."""
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT user_id FROM admins")
        rows = await cursor.fetchall()
    ADMIN_IDS_CACHE.clear()
    for (user_id,) in rows:
        ADMIN_IDS_CACHE.add(user_id)
    logger.info(f"تعداد ادمین‌های لود شده از دیتابیس: {len(ADMIN_IDS_CACHE)}")


async def load_admin_permissions():
    """
    دسترسی‌های جزئی هر ادمین از دیتابیس لود می‌شود. برای ادمین‌های
    قدیمی که از قبل (قبل از این آپدیت) در جدول admins بودند و هیچ
    ردیف دسترسی ندارند، یک‌بار دسترسی‌های پیش‌فرض برایشان ساخته
    می‌شود تا بعد از آپدیت ناگهان دسترسی خود را از دست ندهند.
    """
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT user_id, permission FROM admin_permissions")
        rows = await cursor.fetchall()

        grouped: dict[int, set[str]] = {}
        for user_id, permission in rows:
            grouped.setdefault(user_id, set()).add(permission)

        for admin_id in ADMIN_IDS_CACHE:
            if admin_id not in grouped:
                for perm in DEFAULT_ADMIN_PERMISSIONS:
                    await db.execute(
                        "INSERT OR IGNORE INTO admin_permissions (user_id, permission) VALUES (?, ?)",
                        (admin_id, perm),
                    )
                grouped[admin_id] = set(DEFAULT_ADMIN_PERMISSIONS)

        await db.commit()

    ADMIN_PERMISSIONS_CACHE.clear()
    ADMIN_PERMISSIONS_CACHE.update(grouped)


async def load_settings():
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT key, value FROM settings")
        rows = await cursor.fetchall()
    SETTINGS_CACHE.clear()
    for key, value in rows:
        SETTINGS_CACHE[key] = value


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        await db.commit()
    SETTINGS_CACHE[key] = value


def get_setting(key: str) -> str:
    return SETTINGS_CACHE.get(key, DEFAULT_SETTINGS.get(key, ""))


def get_support_username() -> str:
    return get_setting("support_username")


def get_referral_reward() -> int:
    try:
        return int(get_setting("referral_reward"))
    except (TypeError, ValueError):
        return int(DEFAULT_SETTINGS["referral_reward"])


# ============================================================
# کیبوردها
# ============================================================

def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🛒 خرید کانفیگ"),
                KeyboardButton(text="🔄 تمدید سرویس"),
            ],
            [
                KeyboardButton(text="🧪 تست کانفیگ"),
                KeyboardButton(text="📦 سرویس‌های من"),
            ],
            [
                KeyboardButton(text="💰 کیف پول"),
                KeyboardButton(text="👤 حساب کاربری"),
            ],
            [
                KeyboardButton(text="🏷 کد تخفیف"),
                KeyboardButton(text="🧑‍🤝‍🧑 دعوت دوستان"),
            ],
            [
                KeyboardButton(text="🤝 درخواست نمایندگی"),
                KeyboardButton(text="📢 کانال ما"),
            ],
            [
                KeyboardButton(text="📞 پشتیبانی"),
            ],
        ],
        resize_keyboard=True,
    )


def admin_keyboard(user_id: int):
    """
    کیبورد پنل ادمین حالا بر اساس دسترسی‌های واقعی همان کاربر ساخته
    می‌شود؛ یعنی هر ادمین فقط دکمه‌های بخش‌هایی را می‌بیند که به آن‌ها
    دسترسی دارد. رئیس همیشه همه دکمه‌ها را می‌بیند.
    """
    rows = []

    if has_permission(user_id, "products"):
        rows.append([
            KeyboardButton(text="➕ افزودن محصول"),
            KeyboardButton(text="📦 افزودن موجودی (متنی)"),
        ])
        rows.append([
            KeyboardButton(text="📸 افزودن موجودی (عکسی)"),
            KeyboardButton(text="✏️ ویرایش محصول"),
        ])
        rows.append([KeyboardButton(text="📋 لیست محصولات")])

    if has_permission(user_id, "customers"):
        rows.append([KeyboardButton(text="👥 لیست مشتری‌ها")])

    if has_permission(user_id, "test_configs"):
        rows.append([KeyboardButton(text="🧪 مدیریت کانفیگ تست")])

    if has_permission(user_id, "discounts"):
        rows.append([KeyboardButton(text="🏷 مدیریت کد تخفیف")])

    if has_permission(user_id, "orders"):
        rows.append([
            KeyboardButton(text="⏳ سفارش‌های در انتظار"),
            KeyboardButton(text="💰 شارژهای در انتظار"),
        ])

    if has_permission(user_id, "resellers"):
        rows.append([KeyboardButton(text="🤝 درخواست‌های نمایندگی")])

    if has_permission(user_id, "cards"):
        rows.append([KeyboardButton(text="💳 مدیریت کارت‌ها")])

    if has_permission(user_id, "admins"):
        rows.append([KeyboardButton(text="👨‍💼 مدیریت ادمین‌ها")])

    if is_super_admin(user_id):
        rows.append([KeyboardButton(text="⚙️ تنظیمات ربات")])

    rows.append([KeyboardButton(text="🏠 منوی اصلی")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def cancel_inline_keyboard(callback_data: str = "cancel_flow"):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ انصراف از سفارش", callback_data=callback_data)]
        ]
    )


def admin_cancel_keyboard():
    """دکمه انصراف مشترک برای همه مراحل چندمرحله‌ای پنل ادمین."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ انصراف", callback_data="admin_cancel")]]
    )


def bulk_photo_keyboard(finish_callback: str):
    """کیبورد مشترک برای مراحل افزودن چند عکس پشت‌سرهم + دکمه انصراف."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ پایان افزودن", callback_data=finish_callback)],
            [InlineKeyboardButton(text="❌ انصراف", callback_data="admin_cancel")],
        ]
    )


def skip_discount_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏷 وارد کردن کد تخفیف", callback_data="enter_discount")],
            [InlineKeyboardButton(text="⏭ رد شدن از تخفیف", callback_data="skip_discount")],
            [InlineKeyboardButton(text="❌ انصراف", callback_data="cancel_flow")],
        ]
    )


# ============================================================
# انصراف مشترک پنل ادمین
# ============================================================

@dp.callback_query(F.data == "admin_cancel")
async def admin_cancel_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(
        "❌ عملیات لغو شد.",
        reply_markup=admin_keyboard(callback.from_user.id),
    )
    await callback.answer("لغو شد.")


# ============================================================
# دیتابیس - ساخت جدول‌ها
# توضیح: نسبت به نسخه قبلی دو جدول جدید اضافه شده:
#  - admin_permissions: دسترسی جزئی هر ادمین به هر بخش
#  - settings: تنظیمات قابل تغییر رئیس (آیدی پشتیبانی، جایزه دعوت)
# ============================================================

async def init_db():
    async with aiosqlite.connect(DATABASE) as db:

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                wallet_balance INTEGER DEFAULT 0,
                is_reseller INTEGER DEFAULT 0,
                invited_by INTEGER,
                created_at TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                added_at TEXT
            )
        """)

        # دسترسی جزئی هر ادمین به هر بخش از پنل مدیریت
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_permissions (
                user_id INTEGER,
                permission TEXT,
                PRIMARY KEY (user_id, permission)
            )
        """)

        # تنظیمات قابل ویرایش رئیس (آیدی پشتیبانی، مقدار جایزه دعوت و ...)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                name TEXT,
                price INTEGER,
                description TEXT,
                photo_file_id TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT
            )
        """)

        # کانفیگ تست: مستقل از محصولات، هر ردیف یک آیتم یک‌بارمصرف
        # است. claimed_by مشخص می‌کند کدام کاربر آن را گرفته است.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS test_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config TEXT,
                config_type TEXT DEFAULT 'text',
                claimed INTEGER DEFAULT 0,
                claimed_by INTEGER,
                created_at TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS stock (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                config TEXT,
                config_type TEXT DEFAULT 'text',
                sold INTEGER DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY(product_id) REFERENCES products(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                product_id INTEGER,
                order_type TEXT DEFAULT 'purchase',
                amount INTEGER,
                wallet_used INTEGER DEFAULT 0,
                card_amount INTEGER DEFAULT 0,
                discount_code_id INTEGER,
                receipt_photo TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                product_id INTEGER,
                stock_id INTEGER,
                config TEXT,
                config_type TEXT DEFAULT 'text',
                order_id INTEGER,
                created_at TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS discount_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                discount_type TEXT,   -- percent / fixed / wallet
                value INTEGER,
                max_uses INTEGER,
                used_count INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                created_at TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS discount_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code_id INTEGER,
                user_id INTEGER,
                created_at TEXT,
                UNIQUE(code_id, user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS reseller_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER UNIQUE,
                reward_given INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)

        # شماره کارت‌ها فقط اینجا، در دیتابیس نگه داشته می‌شوند و
        # فقط از طریق پنل رئیس (یا ادمینی با دسترسی «cards») مدیریت می‌شوند.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_number TEXT,
                card_owner TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT
            )
        """)

        await db.commit()

    logger.info("دیتابیس آماده است.")


# ============================================================
# توابع کمکی دیتابیس - کاربر و کیف پول
# ============================================================

async def save_user(message: Message, invited_by: int | None = None):
    if not message.from_user:
        return
    user = message.from_user

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT user_id FROM users WHERE user_id = ?", (user.id,)
        )
        existing = await cursor.fetchone()

        if existing:
            await db.execute("""
                UPDATE users SET username = ?, first_name = ?
                WHERE user_id = ?
            """, (user.username, user.first_name, user.id))
        else:
            await db.execute("""
                INSERT INTO users (user_id, username, first_name, wallet_balance,
                                    invited_by, created_at)
                VALUES (?, ?, ?, 0, ?, ?)
            """, (user.id, user.username, user.first_name, invited_by,
                  datetime.now().isoformat()))

        await db.commit()

    return existing is not None


async def get_wallet(user_id: int) -> int:
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT wallet_balance FROM users WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def change_wallet(user_id: int, delta: int):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            UPDATE users SET wallet_balance = wallet_balance + ?
            WHERE user_id = ?
        """, (delta, user_id))
        await db.commit()


async def has_successful_purchase(user_id: int) -> bool:
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM purchases WHERE user_id = ?", (user_id,)
        )
        return (await cursor.fetchone())[0] > 0


# ============================================================
# توابع کمکی دیتابیس - کارت‌های بانکی
# توضیح: اگر کارت فعالی در دیتابیس نباشد، pick_card مقدار None
# برمی‌گرداند و بخش‌های مصرف‌کننده باید این حالت را مدیریت کنند
# (پرداخت کارتی غیرفعال).
# ============================================================

async def get_active_cards():
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id, card_number, card_owner FROM cards WHERE active = 1"
        )
        return await cursor.fetchall()


async def pick_card():
    cards = await get_active_cards()
    if not cards:
        return None, None, None
    card = random.choice(cards)
    return card[0], card[1], card[2]


# ============================================================
# توابع کمکی دیتابیس - کد تخفیف
# ============================================================

async def get_discount_code(code: str):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT id, code, discount_type, value, max_uses, used_count, active
            FROM discount_codes WHERE code = ?
        """, (code,))
        return await cursor.fetchone()


async def user_used_discount(code_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT id FROM discount_usage WHERE code_id = ? AND user_id = ?
        """, (code_id, user_id))
        return (await cursor.fetchone()) is not None


async def mark_discount_used(code_id: int, user_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            INSERT INTO discount_usage (code_id, user_id, created_at)
            VALUES (?, ?, ?)
        """, (code_id, user_id, datetime.now().isoformat()))
        await db.execute("""
            UPDATE discount_codes SET used_count = used_count + 1 WHERE id = ?
        """, (code_id,))
        await db.commit()


async def validate_discount_for_purchase(code_text: str, user_id: int):
    row = await get_discount_code(code_text.strip())
    if not row:
        return False, "❌ کد تخفیف پیدا نشد.", None

    code_id, code, dtype, value, max_uses, used_count, active = row

    if not active:
        return False, "❌ این کد تخفیف غیرفعال شده است.", None

    if dtype not in ("percent", "fixed"):
        return False, "❌ این کد فقط برای شارژ کیف پول قابل استفاده است (از منوی «کد تخفیف»).", None

    if max_uses and used_count >= max_uses:
        return False, "❌ ظرفیت استفاده از این کد تخفیف تمام شده است.", None

    if await user_used_discount(code_id, user_id):
        return False, "❌ شما قبلاً از این کد تخفیف استفاده کرده‌اید.", None

    return True, "✅ کد تخفیف اعمال شد.", row


def apply_discount_value(base_price: int, code_row) -> int:
    code_id, code, dtype, value, max_uses, used_count, active = code_row
    if dtype == "percent":
        discount = int(base_price * value / 100)
    else:
        discount = value
    return max(0, base_price - discount)


# ============================================================
# بررسی عضویت اجباری در کانال
# ============================================================

async def check_membership(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
        ]
    except Exception as e:
        logger.warning(f"خطا در بررسی عضویت {user_id}: {e}")
        return False


async def check_access(message: Message) -> bool:
    if not message.from_user:
        return False

    if is_admin(message.from_user.id):
        return True

    joined = await check_membership(message.bot, message.from_user.id)

    if not joined:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📢 عضویت در کانال", url=CHANNEL_LINK)],
                [InlineKeyboardButton(text="✅ بررسی عضویت", callback_data="check_membership")],
            ]
        )
        await message.answer(
            "برای استفاده از ربات ابتدا باید در کانال ما عضو شوید.",
            reply_markup=keyboard,
        )
        return False

    return True


# ============================================================
# START + سیستم دعوت دوستان
# ============================================================

@dp.message(CommandStart())
async def start_handler(message: Message, command: CommandObject):
    global BOT_USERNAME

    if not BOT_USERNAME:
        me = await message.bot.get_me()
        BOT_USERNAME = me.username

    invited_by = None
    args = command.args

    if args and args.startswith("ref_"):
        try:
            ref_id = int(args.replace("ref_", ""))
            if ref_id != message.from_user.id:
                invited_by = ref_id
        except ValueError:
            invited_by = None

    already_existed = await save_user(message, invited_by=invited_by)

    if not already_existed and invited_by:
        async with aiosqlite.connect(DATABASE) as db:
            cursor = await db.execute(
                "SELECT user_id FROM users WHERE user_id = ?", (invited_by,)
            )
            referrer_exists = await cursor.fetchone()

            if referrer_exists:
                try:
                    await db.execute("""
                        INSERT INTO referrals (referrer_id, referred_id, reward_given, created_at)
                        VALUES (?, ?, 1, ?)
                    """, (invited_by, message.from_user.id, datetime.now().isoformat()))
                    await db.commit()

                    reward = get_referral_reward()
                    await change_wallet(invited_by, reward)

                    try:
                        await message.bot.send_message(
                            invited_by,
                            f"🎉 یک نفر با لینک دعوت شما عضو ربات شد!\n"
                            f"💰 مبلغ {reward:,} تومان به کیف پول شما اضافه شد."
                        )
                    except Exception:
                        pass

                except aiosqlite.IntegrityError:
                    pass

    if not await check_access(message):
        return

    if is_admin(message.from_user.id):
        await message.answer(
            "👑 به پنل مدیریت خوش آمدید.",
            reply_markup=admin_keyboard(message.from_user.id),
        )
        return

    await message.answer(
        f"سلام {escape(message.from_user.first_name or '')} 👋\n\n"
        "به ربات فروش کانفیگ خوش آمدید.",
        reply_markup=main_keyboard(),
    )


@dp.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext):
    await state.clear()
    if is_admin(message.from_user.id):
        await message.answer("عملیات لغو شد.", reply_markup=admin_keyboard(message.from_user.id))
    else:
        await message.answer("عملیات لغو شد.", reply_markup=main_keyboard())


@dp.message(Command("id"))
async def id_handler(message: Message):
    if not message.from_user:
        return
    await message.answer(
        f"🆔 آیدی عددی شما:\n\n<code>{message.from_user.id}</code>",
        parse_mode="HTML",
    )


@dp.message(Command("admin"))
async def admin_handler(message: Message):
    if not message.from_user:
        return
    if not is_admin(message.from_user.id):
        await message.answer("⛔ شما دسترسی مدیریت ندارید.")
        return
    await message.answer(
        "👑 <b>پنل مدیریت</b>\n\nاز گزینه‌های زیر استفاده کنید.",
        reply_markup=admin_keyboard(message.from_user.id),
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "check_membership")
async def check_membership_callback(callback: CallbackQuery):
    joined = await check_membership(callback.bot, callback.from_user.id)
    if joined:
        await callback.message.edit_text("✅ عضویت شما تأیید شد.\n\nحالا می‌توانید از ربات استفاده کنید.")
        await callback.answer("عضویت تأیید شد.")
    else:
        await callback.answer("❌ هنوز عضو کانال نشده‌اید.", show_alert=True)


# ============================================================
# دکمه «کانال ما»
# ============================================================

@dp.message(F.text == "📢 کانال ما")
async def channel_button(message: Message):
    if not await check_access(message):
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📢 عضویت در کانال", url=CHANNEL_LINK)]]
    )
    await message.answer(
        "📢 <b>کانال رسمی ما</b>\n\nبرای اطلاع از اخبار و آپدیت‌ها عضو کانال شوید.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


# ============================================================
# پشتیبانی
# توضیح: آیدی پشتیبانی دیگر در کد نیست؛ از تنظیمات رئیس خوانده می‌شود.
# ============================================================

@dp.message(F.text == "📞 پشتیبانی")
async def support_handler(message: Message):
    if not await check_access(message):
        return

    username = get_support_username().strip()
    if not username:
        await message.answer("📞 <b>پشتیبانی</b>\n\nدر حال حاضر پشتیبانی در دسترس نیست.", parse_mode="HTML")
        return

    clean_username = username.lstrip("@").strip()
    if not clean_username:
        await message.answer("📞 <b>پشتیبانی</b>\n\nدر حال حاضر پشتیبانی در دسترس نیست.", parse_mode="HTML")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=f"👤 {username}", url=f"https://t.me/{clean_username}")]]
    )
    await message.answer(
        "📞 <b>پشتیبانی</b>\n\nبرای ارتباط با پشتیبانی روی دکمه زیر بزنید:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


# ============================================================
# حساب کاربری / کیف پول
# ============================================================

@dp.message(F.text == "👤 حساب کاربری")
async def account(message: Message):
    if not await check_access(message):
        return

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM purchases WHERE user_id = ?", (message.from_user.id,)
        )
        purchases = (await cursor.fetchone())[0]

    wallet = await get_wallet(message.from_user.id)
    username = f"@{message.from_user.username}" if message.from_user.username else "ندارد"

    await message.answer(
        "👤 <b>حساب کاربری</b>\n\n"
        f"🆔 آیدی: <code>{message.from_user.id}</code>\n"
        f"📱 یوزرنیم: {escape(username)}\n"
        f"💰 موجودی کیف پول: <b>{wallet:,}</b> تومان\n"
        f"📦 تعداد خریدها: <b>{purchases}</b>",
        parse_mode="HTML",
    )


@dp.message(F.text == "💰 کیف پول")
async def wallet_menu(message: Message):
    if not await check_access(message):
        return

    wallet = await get_wallet(message.from_user.id)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="➕ شارژ کیف پول", callback_data="charge_wallet")]]
    )
    await message.answer(
        f"💰 <b>کیف پول شما</b>\n\nموجودی فعلی: <b>{wallet:,}</b> تومان",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "charge_wallet")
async def charge_wallet_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(WalletChargeAmountStates.waiting_amount)
    await callback.message.answer(
        "💰 مبلغی که می‌خواهید به کیف پول شارژ کنید را فقط به عدد (تومان) وارد کنید.\n\n"
        "برای انصراف /cancel را ارسال کنید."
    )
    await callback.answer()


@dp.message(WalletChargeAmountStates.waiting_amount)
async def charge_wallet_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text.replace(",", "").strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ لطفاً یک عدد مثبت وارد کنید.")
        return

    await state.clear()
    await start_payment_flow(
        message, state,
        flow_type="wallet_charge",
        product_id=None,
        base_price=amount,
    )


# ============================================================
# کد تخفیف - شارژ مستقیم کیف پول
# ============================================================

@dp.message(F.text == "🏷 کد تخفیف")
async def redeem_code_start(message: Message, state: FSMContext):
    if not await check_access(message):
        return
    await state.set_state(RedeemCodeStates.waiting_code)
    await message.answer("🏷 کد تخفیف خود را ارسال کنید.\n\nبرای انصراف /cancel را بفرستید.")


@dp.message(RedeemCodeStates.waiting_code)
async def redeem_code_process(message: Message, state: FSMContext):
    await state.clear()
    code_text = message.text.strip()
    row = await get_discount_code(code_text)

    if not row:
        await message.answer("❌ کد تخفیف پیدا نشد.")
        return

    code_id, code, dtype, value, max_uses, used_count, active = row

    if not active:
        await message.answer("❌ این کد تخفیف غیرفعال شده است.")
        return

    if dtype != "wallet":
        await message.answer("❌ این کد فقط هنگام خرید قابل استفاده است (در مرحله انتخاب محصول).")
        return

    if max_uses and used_count >= max_uses:
        await message.answer("❌ ظرفیت استفاده از این کد تخفیف تمام شده است.")
        return

    if await user_used_discount(code_id, message.from_user.id):
        await message.answer("❌ شما قبلاً از این کد تخفیف استفاده کرده‌اید.")
        return

    await mark_discount_used(code_id, message.from_user.id)
    await change_wallet(message.from_user.id, value)

    await message.answer(
        f"✅ کد تخفیف با موفقیت اعمال شد.\n💰 مبلغ {value:,} تومان به کیف پول شما اضافه شد."
    )


# ============================================================
# دعوت دوستان
# ============================================================

@dp.message(F.text == "🧑‍🤝‍🧑 دعوت دوستان")
async def invite_friends(message: Message):
    if not await check_access(message):
        return

    global BOT_USERNAME
    if not BOT_USERNAME:
        me = await message.bot.get_me()
        BOT_USERNAME = me.username

    link = f"https://t.me/{BOT_USERNAME}?start=ref_{message.from_user.id}"
    reward = get_referral_reward()

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (message.from_user.id,)
        )
        invited_count = (await cursor.fetchone())[0]

    await message.answer(
        "🧑‍🤝‍🧑 <b>دعوت از دوستان</b>\n\n"
        f"با لینک زیر دوستان خود را دعوت کنید و به ازای هر عضو جدید "
        f"<b>{reward:,} تومان</b> به کیف پول شما اضافه می‌شود:\n\n"
        f"<code>{escape(link)}</code>\n\n"
        f"👥 تعداد افرادی که تا الان با لینک شما عضو شده‌اند: <b>{invited_count}</b>",
        parse_mode="HTML",
    )


# ============================================================
# درخواست نمایندگی
# ============================================================

@dp.message(F.text == "🤝 درخواست نمایندگی")
async def reseller_request_start(message: Message):
    if not await check_access(message):
        return

    user_id = message.from_user.id
    wallet = await get_wallet(user_id)
    has_purchase = await has_successful_purchase(user_id)

    if wallet < RESELLER_MIN_WALLET and not has_purchase:
        await message.answer(
            "❌ برای درخواست نمایندگی باید یکی از شرایط زیر را داشته باشید:\n\n"
            f"• موجودی کیف پول حداقل {RESELLER_MIN_WALLET:,} تومان\n"
            "• حداقل یک خرید موفق از ربات"
        )
        return

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id FROM reseller_requests WHERE user_id = ? AND status = 'pending'",
            (user_id,),
        )
        pending = await cursor.fetchone()

        if pending:
            await message.answer("⏳ درخواست نمایندگی قبلی شما هنوز در حال بررسی است.")
            return

        await db.execute("""
            INSERT INTO reseller_requests (user_id, status, created_at)
            VALUES (?, 'pending', ?)
        """, (user_id, datetime.now().isoformat()))
        request_id = (await db.execute("SELECT last_insert_rowid()")).lastrowid
        await db.commit()

    await message.answer("✅ درخواست نمایندگی شما ثبت شد و برای بررسی به ادمین ارسال شد.")

    username = f"@{message.from_user.username}" if message.from_user.username else "بدون یوزرنیم"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ تایید نمایندگی", callback_data=f"reseller_approve:{request_id}"),
            InlineKeyboardButton(text="❌ رد درخواست", callback_data=f"reseller_reject:{request_id}"),
        ]]
    )

    for admin_id in all_admin_ids():
        if not has_permission(admin_id, "resellers"):
            continue
        try:
            await message.bot.send_message(
                admin_id,
                "🤝 <b>درخواست نمایندگی جدید</b>\n\n"
                f"👤 کاربر: {escape(username)}\n"
                f"🔢 آیدی: <code>{user_id}</code>\n"
                f"💰 موجودی کیف پول: {wallet:,} تومان\n"
                f"🛒 خرید موفق: {'دارد' if has_purchase else 'ندارد'}",
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"خطا در ارسال درخواست نمایندگی به ادمین {admin_id}: {e}")


@dp.callback_query(F.data.startswith("reseller_approve:"))
async def reseller_approve(callback: CallbackQuery):
    if not has_permission(callback.from_user.id, "resellers"):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    request_id = int(callback.data.split(":")[1])

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT user_id, status FROM reseller_requests WHERE id = ?", (request_id,)
        )
        row = await cursor.fetchone()
        if not row:
            await callback.answer("❌ درخواست پیدا نشد.", show_alert=True)
            return
        user_id, status = row
        if status != "pending":
            await callback.answer("⚠️ این درخواست قبلاً بررسی شده.", show_alert=True)
            return

        await db.execute("UPDATE reseller_requests SET status = 'approved' WHERE id = ?", (request_id,))
        await db.execute("UPDATE users SET is_reseller = 1 WHERE user_id = ?", (user_id,))
        await db.commit()

    try:
        await callback.bot.send_message(user_id, " 🎉 تبریک! درخواست نمایندگی شما تایید شد. از پشتیبانی با شما ارتباط گرفته میشود ")
    except Exception:
        pass

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.answer("✅ نمایندگی تایید شد.")


@dp.callback_query(F.data.startswith("reseller_reject:"))
async def reseller_reject(callback: CallbackQuery):
    if not has_permission(callback.from_user.id, "resellers"):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    request_id = int(callback.data.split(":")[1])

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT user_id, status FROM reseller_requests WHERE id = ?", (request_id,)
        )
        row = await cursor.fetchone()
        if not row:
            await callback.answer("❌ درخواست پیدا نشد.", show_alert=True)
            return
        user_id, status = row
        if status != "pending":
            await callback.answer("⚠️ این درخواست قبلاً بررسی شده.", show_alert=True)
            return

        await db.execute("UPDATE reseller_requests SET status = 'rejected' WHERE id = ?", (request_id,))
        await db.commit()

    try:
        await callback.bot.send_message(user_id, "❌ درخواست نمایندگی شما رد شد.")
    except Exception:
        pass

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.answer("❌ درخواست رد شد.")


@dp.message(F.text == "🤝 درخواست‌های نمایندگی")
async def list_reseller_requests(message: Message):
    if not has_permission(message.from_user.id, "resellers"):
        return

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT id, user_id, status, created_at FROM reseller_requests
            WHERE status = 'pending' ORDER BY id DESC
        """)
        rows = await cursor.fetchall()

    if not rows:
        await message.answer("✅ هیچ درخواست نمایندگی در انتظاری وجود ندارد.")
        return

    for req_id, user_id, status, created_at in rows:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="✅ تایید", callback_data=f"reseller_approve:{req_id}"),
                InlineKeyboardButton(text="❌ رد", callback_data=f"reseller_reject:{req_id}"),
            ]]
        )
        await message.answer(
            f"🆔 درخواست: {req_id}\n👤 کاربر: <code>{user_id}</code>\n📅 تاریخ: {created_at}",
            reply_markup=keyboard,
            parse_mode="HTML",
        )


# ============================================================
# موتور مشترک پرداخت (خرید / تمدید / شارژ کیف پول)
# ============================================================

async def start_payment_flow(target, state: FSMContext, flow_type: str,
                              product_id: int | None, base_price: int,
                              product_name: str = ""):
    message = target if isinstance(target, Message) else target

    await state.update_data(
        flow_type=flow_type,
        product_id=product_id,
        base_price=base_price,
        product_name=product_name,
    )

    if flow_type in ("purchase", "renewal"):
        await state.set_state(PaymentFlow.waiting_discount_code)
        await message.answer(
            f"📦 <b>{escape(product_name)}</b>\n💰 قیمت: <b>{base_price:,}</b> تومان\n\n"
            "آیا کد تخفیف دارید؟",
            reply_markup=skip_discount_keyboard(),
            parse_mode="HTML",
        )
    else:
        await proceed_to_payment_split(message, state, discount_code_id=None)


@dp.callback_query(F.data == "enter_discount", PaymentFlow.waiting_discount_code)
async def ask_discount_code(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("🏷 کد تخفیف خود را ارسال کنید.")
    await callback.answer()


@dp.callback_query(F.data == "skip_discount", PaymentFlow.waiting_discount_code)
async def skip_discount(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await proceed_to_payment_split(callback.message, state, discount_code_id=None)


@dp.message(PaymentFlow.waiting_discount_code)
async def process_discount_code_text(message: Message, state: FSMContext):
    data = await state.get_data()
    base_price = data["base_price"]

    ok, msg, row = await validate_discount_for_purchase(message.text, message.from_user.id)
    await message.answer(msg)

    if not ok:
        return

    code_id = row[0]
    final_price = apply_discount_value(base_price, row)
    await state.update_data(final_price=final_price)
    await proceed_to_payment_split(message, state, discount_code_id=code_id)


async def proceed_to_payment_split(message: Message, state: FSMContext, discount_code_id):
    data = await state.get_data()
    base_price = data["base_price"]
    final_price = data.get("final_price", base_price)
    user_id = message.chat.id

    wallet = await get_wallet(user_id)
    wallet_used = min(wallet, final_price)
    card_amount = final_price - wallet_used

    if card_amount <= 0:
        await state.update_data(
            final_price=final_price,
            wallet_used=wallet_used,
            card_amount=card_amount,
            discount_code_id=discount_code_id,
        )
        await finalize_wallet_only_payment(message, state)
        return

    # قبل از هر برداشتی از کیف پول، وجود کارت فعال را بررسی می‌کنیم
    card_id, card_number, card_owner = await pick_card()

    if not card_number:
        await state.clear()
        await message.answer(
            "❌ در حال حاضر هیچ کارت بانکی فعالی برای پرداخت کارت‌به‌کارت ثبت نشده است.\n"
            "لطفاً با پشتیبانی در ارتباط باشید یا بعداً دوباره تلاش کنید.",
            reply_markup=main_keyboard(),
        )
        return

    await state.update_data(
        final_price=final_price,
        wallet_used=wallet_used,
        card_amount=card_amount,
        discount_code_id=discount_code_id,
        card_id=card_id,
    )
    await state.set_state(PaymentFlow.waiting_receipt)

    wallet_line = (
        f"💰 مبلغ {wallet_used:,} تومان از کیف پول شما کسر شد.\n"
        if wallet_used > 0 else ""
    )

    await message.answer(
        f"{wallet_line}"
        f"💳 مبلغ باقی‌مانده جهت پرداخت: <b>{card_amount:,}</b> تومان\n\n"
        f"شماره کارت:\n<code>{escape(card_number)}</code>\n"
        f"👤 به نام: <b>{escape(card_owner)}</b>\n\n"
        "بعد از پرداخت، تصویر رسید را همینجا ارسال کنید.",
        reply_markup=cancel_inline_keyboard(),
        parse_mode="HTML",
    )

    if wallet_used > 0:
        await change_wallet(user_id, -wallet_used)


async def finalize_wallet_only_payment(message: Message, state: FSMContext):
    data = await state.get_data()
    flow_type = data["flow_type"]
    user_id = message.chat.id
    final_price = data["final_price"]
    wallet_used = data["wallet_used"]
    discount_code_id = data.get("discount_code_id")

    await change_wallet(user_id, -wallet_used)

    if discount_code_id:
        await mark_discount_used(discount_code_id, user_id)

    if flow_type == "wallet_charge":
        await state.clear()
        await message.answer("✅ عملیات با موفقیت انجام شد.", reply_markup=main_keyboard())
        return

    product_id = data["product_id"]
    stock_row = await take_stock_item(product_id)

    if not stock_row:
        await change_wallet(user_id, wallet_used)
        await state.clear()
        await message.answer("❌ متاسفانه موجودی این محصول تمام شد. مبلغ به کیف پول شما بازگشت.",
                              reply_markup=main_keyboard())
        return

    await record_purchase_and_deliver(message.bot, user_id, product_id, stock_row, order_id=None)

    await state.clear()
    await message.answer("✅ خرید شما با موفقیت از کیف پول انجام و کانفیگ ارسال شد.",
                          reply_markup=main_keyboard())


# ============================================================
# انصراف از سفارش در مرحله رسید
# ============================================================

@dp.callback_query(F.data == "cancel_flow")
async def cancel_flow_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    wallet_used = data.get("wallet_used", 0)
    user_id = callback.from_user.id

    if wallet_used:
        await change_wallet(user_id, wallet_used)

    await state.clear()
    await callback.message.answer("❌ سفارش لغو شد.", reply_markup=main_keyboard())
    await callback.answer("لغو شد.")


# ============================================================
# دریافت رسید کارت‌به‌کارت
# ============================================================

@dp.message(PaymentFlow.waiting_receipt, F.photo)
async def receive_receipt(message: Message, state: FSMContext):
    data = await state.get_data()
    flow_type = data["flow_type"]
    product_id = data.get("product_id")
    final_price = data["final_price"]
    wallet_used = data["wallet_used"]
    card_amount = data["card_amount"]
    discount_code_id = data.get("discount_code_id")
    product_name = data.get("product_name", "")

    photo = message.photo[-1]
    user_id = message.from_user.id

    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            INSERT INTO orders (user_id, product_id, order_type, amount, wallet_used,
                                 card_amount, discount_code_id, receipt_photo, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """, (user_id, product_id, flow_type, final_price, wallet_used, card_amount,
              discount_code_id, photo.file_id, datetime.now().isoformat()))
        order_id = (await db.execute("SELECT last_insert_rowid()")).lastrowid
        await db.commit()

    await state.clear()

    await message.answer(
        "✅ رسید شما دریافت شد.\n\n⏳ سفارش برای بررسی ادمین ارسال شد.",
        reply_markup=main_keyboard(),
    )

    username = f"@{message.from_user.username}" if message.from_user.username else "بدون یوزرنیم"

    if flow_type == "wallet_charge":
        title = "💰 <b>درخواست شارژ کیف پول</b>"
        product_line = ""
    elif flow_type == "renewal":
        title = "🔄 <b>سفارش تمدید سرویس</b>"
        product_line = f"📦 محصول: <b>{escape(product_name)}</b>\n"
    else:
        title = "🛒 <b>سفارش جدید</b>"
        product_line = f"📦 محصول: <b>{escape(product_name)}</b>\n"

    caption = (
        f"{title}\n\n"
        f"🆔 سفارش: <code>{order_id}</code>\n"
        f"👤 کاربر: {escape(username)}\n"
        f"🔢 آیدی: <code>{user_id}</code>\n"
        f"{product_line}"
        f"💰 مبلغ کل: <b>{final_price:,}</b> تومان\n"
        f"👛 از کیف پول: {wallet_used:,} تومان\n"
        f"💳 پرداخت کارتی: {card_amount:,} تومان"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ تأیید سفارش", callback_data=f"approve:{order_id}"),
            InlineKeyboardButton(text="❌ رد سفارش", callback_data=f"reject:{order_id}"),
        ]]
    )

    for admin_id in all_admin_ids():
        if not has_permission(admin_id, "orders"):
            continue
        try:
            await message.bot.send_photo(
                chat_id=admin_id, photo=photo.file_id, caption=caption,
                reply_markup=keyboard, parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"خطا در ارسال سفارش به ادمین {admin_id}: {e}")


@dp.message(PaymentFlow.waiting_receipt)
async def invalid_receipt(message: Message):
    await message.answer("⚠️ لطفاً تصویر رسید پرداخت را ارسال کنید یا برای انصراف /cancel را بزنید.")


# ============================================================
# توابع کمکی موجودی و تحویل کانفیگ
# ============================================================

async def take_stock_item(product_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute("""
            SELECT id, config, config_type FROM stock
            WHERE product_id = ? AND sold = 0 ORDER BY id ASC LIMIT 1
        """, (product_id,))
        stock_item = await cursor.fetchone()

        if not stock_item:
            await db.rollback()
            return None

        stock_id = stock_item[0]
        await db.execute("UPDATE stock SET sold = 1 WHERE id = ?", (stock_id,))
        await db.commit()
        return stock_item


async def record_purchase_and_deliver(bot: Bot, user_id: int, product_id: int, stock_row, order_id):
    stock_id, config, config_type = stock_row

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT name FROM products WHERE id = ?", (product_id,))
        product_name = (await cursor.fetchone())[0]

        await db.execute("""
            INSERT INTO purchases (user_id, product_id, stock_id, config, config_type, order_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, product_id, stock_id, config, config_type, order_id, datetime.now().isoformat()))
        await db.commit()

    try:
        if config_type == "photo":
            await bot.send_photo(
                chat_id=user_id, photo=config,
                caption=f"✅ <b>خرید شما تایید شد.</b>\n📦 محصول: <b>{escape(product_name)}</b>\n\nممنون از خرید شما ❤️",
                parse_mode="HTML",
            )
        else:
            await bot.send_message(
                chat_id=user_id,
                text=(
                    "✅ <b>خرید شما تایید شد.</b>\n\n"
                    f"📦 محصول: <b>{escape(product_name)}</b>\n\n"
                    "🔐 <b>کانفیگ شما:</b>\n"
                    f"<pre>{escape(config)}</pre>\n\n"
                    "ممنون از خرید شما ❤️"
                ),
                parse_mode="HTML",
            )
    except Exception as e:
        logger.error(f"خطا در ارسال کانفیگ: {e}")


# ============================================================
# تأیید / رد سفارش توسط ادمین
# ============================================================

@dp.callback_query(F.data.startswith("approve:"))
async def approve_order(callback: CallbackQuery):
    if not has_permission(callback.from_user.id, "orders"):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    order_id = int(callback.data.split(":")[1])

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT id, user_id, product_id, order_type, amount, wallet_used,
                   card_amount, discount_code_id, status
            FROM orders WHERE id = ?
        """, (order_id,))
        order = await cursor.fetchone()

        if not order:
            await callback.answer("❌ سفارش پیدا نشد.", show_alert=True)
            return

        (order_id_db, user_id, product_id, order_type, amount, wallet_used,
         card_amount, discount_code_id, status) = order

        if status != "pending":
            await callback.answer("⚠️ این سفارش قبلاً بررسی شده است.", show_alert=True)
            return

        await db.execute("UPDATE orders SET status = 'approved' WHERE id = ?", (order_id_db,))
        await db.commit()

    if discount_code_id:
        await mark_discount_used(discount_code_id, user_id)

    if order_type == "wallet_charge":
        await change_wallet(user_id, amount)
        try:
            await callback.bot.send_message(
                user_id,
                f"✅ کیف پول شما به مبلغ <b>{amount:,}</b> تومان شارژ شد.",
                parse_mode="HTML",
            )
        except Exception:
            pass

    else:
        stock_row = await take_stock_item(product_id)

        if not stock_row:
            if wallet_used:
                await change_wallet(user_id, wallet_used)
            async with aiosqlite.connect(DATABASE) as db:
                await db.execute("UPDATE orders SET status = 'rejected' WHERE id = ?", (order_id_db,))
                await db.commit()
            try:
                await callback.bot.send_message(
                    user_id,
                    "❌ متاسفانه موجودی این محصول تمام شده است. مبلغ کیف پولی شما بازگشت داده شد.\n"
                    "برای بخش کارتی با پشتیبانی در ارتباط باشید.",
                )
            except Exception:
                pass
            await callback.answer("❌ موجودی تمام شده - سفارش رد شد.", show_alert=True)
            return

        await record_purchase_and_deliver(callback.bot, user_id, product_id, stock_row, order_id_db)

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.answer("✅ سفارش تأیید شد.")


@dp.callback_query(F.data.startswith("reject:"))
async def reject_order(callback: CallbackQuery):
    if not has_permission(callback.from_user.id, "orders"):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    order_id = int(callback.data.split(":")[1])

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT user_id, status, wallet_used FROM orders WHERE id = ?", (order_id,)
        )
        order = await cursor.fetchone()

        if not order:
            await callback.answer("❌ سفارش پیدا نشد.", show_alert=True)
            return

        user_id, status, wallet_used = order

        if status != "pending":
            await callback.answer("⚠️ این سفارش قبلاً بررسی شده.", show_alert=True)
            return

        await db.execute("UPDATE orders SET status = 'rejected' WHERE id = ?", (order_id,))
        await db.commit()

    if wallet_used:
        await change_wallet(user_id, wallet_used)

    try:
        await callback.bot.send_message(
            user_id,
            "❌ <b>سفارش شما رد شد.</b>\n\n"
            + (f"💰 مبلغ {wallet_used:,} تومان به کیف پول شما بازگشت داده شد.\n\n" if wallet_used else "")
            + "در صورت وجود مشکل در پرداخت، با پشتیبانی تماس بگیرید.",
            parse_mode="HTML",
        )
    except Exception:
        pass

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.answer("❌ سفارش رد شد.")


@dp.message(F.text == "⏳ سفارش‌های در انتظار")
async def pending_orders_list(message: Message):
    if not has_permission(message.from_user.id, "orders"):
        return

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT id, user_id, order_type, amount, card_amount FROM orders
            WHERE status = 'pending' AND order_type != 'wallet_charge'
            ORDER BY id DESC
        """)
        rows = await cursor.fetchall()

    if not rows:
        await message.answer("✅ سفارش در انتظاری وجود ندارد.")
        return

    text = "⏳ <b>سفارش‌های در انتظار تایید</b>\n\n"
    for order_id, user_id, order_type, amount, card_amount in rows:
        text += (
            f"🆔 {order_id} | 👤 <code>{user_id}</code> | "
            f"نوع: {order_type} | مبلغ کارتی: {card_amount:,}\n"
        )
    await message.answer(text, parse_mode="HTML")


@dp.message(F.text == "💰 شارژهای در انتظار")
async def pending_wallet_charges(message: Message):
    if not has_permission(message.from_user.id, "orders"):
        return

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT id, user_id, amount FROM orders
            WHERE status = 'pending' AND order_type = 'wallet_charge'
            ORDER BY id DESC
        """)
        rows = await cursor.fetchall()

    if not rows:
        await message.answer("✅ درخواست شارژ در انتظاری وجود ندارد.")
        return

    text = "💰 <b>درخواست‌های شارژ کیف پول در انتظار</b>\n\n"
    for order_id, user_id, amount in rows:
        text += f"🆔 {order_id} | 👤 <code>{user_id}</code> | مبلغ: {amount:,}\n"
    await message.answer(text, parse_mode="HTML")


# ============================================================
# خرید محصول
# ============================================================

@dp.message(F.text == "🛒 خرید کانفیگ")
async def buy_config(message: Message):
    if not await check_access(message):
        return

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT p.id, p.name, p.price, COUNT(s.id)
            FROM products p
            LEFT JOIN stock s ON p.id = s.product_id AND s.sold = 0
            WHERE p.active = 1
            GROUP BY p.id ORDER BY p.id DESC
        """)
        products = await cursor.fetchall()

    if not products:
        await message.answer("❌ در حال حاضر محصولی موجود نیست.")
        return

    buttons = []
    for product_id, name, price, stock_count in products:
        buttons.append([InlineKeyboardButton(
            text=f"{name} | {price:,} تومان | موجودی: {stock_count}",
            callback_data=f"buy:{product_id}",
        )])

    await message.answer(
        "🛒 <b>محصول موردنظر را انتخاب کنید:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("buy:"))
async def buy_product_callback(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split(":")[1])

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id, name, price FROM products WHERE id = ? AND active = 1", (product_id,)
        )
        product = await cursor.fetchone()

        if not product:
            await callback.answer("❌ محصول پیدا نشد.", show_alert=True)
            return

        stock_cursor = await db.execute(
            "SELECT COUNT(*) FROM stock WHERE product_id = ? AND sold = 0", (product_id,)
        )
        stock_count = (await stock_cursor.fetchone())[0]

    if stock_count <= 0:
        await callback.answer("❌ این محصول موجود نیست.", show_alert=True)
        return

    _, name, price = product
    await callback.answer()
    await start_payment_flow(
        callback.message, state, flow_type="purchase",
        product_id=product_id, base_price=price, product_name=name,
    )


# ============================================================
# تمدید سرویس
# ============================================================

@dp.message(F.text == "🔄 تمدید سرویس")
async def renewal_start(message: Message):
    if not await check_access(message):
        return

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT DISTINCT p.id, p.name, p.price
            FROM purchases pu
            JOIN products p ON pu.product_id = p.id
            WHERE pu.user_id = ? AND p.active = 1
        """, (message.from_user.id,))
        rows = await cursor.fetchall()

    if not rows:
        await message.answer("📦 شما هنوز هیچ سرویسی خریداری نکرده‌اید که قابل تمدید باشد.")
        return

    buttons = []
    for product_id, name, price in rows:
        buttons.append([InlineKeyboardButton(
            text=f"{name} | {price:,} تومان", callback_data=f"renew:{product_id}"
        )])

    await message.answer(
        "🔄 <b>کدام سرویس را می‌خواهید تمدید کنید؟</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("renew:"))
async def renewal_callback(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split(":")[1])

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id, name, price FROM products WHERE id = ? AND active = 1", (product_id,)
        )
        product = await cursor.fetchone()

        if not product:
            await callback.answer("❌ محصول پیدا نشد.", show_alert=True)
            return

        stock_cursor = await db.execute(
            "SELECT COUNT(*) FROM stock WHERE product_id = ? AND sold = 0", (product_id,)
        )
        stock_count = (await stock_cursor.fetchone())[0]

    if stock_count <= 0:
        await callback.answer("❌ در حال حاضر موجودی برای تمدید این محصول وجود ندارد.", show_alert=True)
        return

    _, name, price = product
    await callback.answer()
    await start_payment_flow(
        callback.message, state, flow_type="renewal",
        product_id=product_id, base_price=price, product_name=name,
    )


# ============================================================
# سرویس‌های من
# ============================================================

@dp.message(F.text == "📦 سرویس‌های من")
async def my_services(message: Message):
    if not await check_access(message):
        return

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT purchases.id, products.name, purchases.config, purchases.config_type
            FROM purchases
            JOIN products ON purchases.product_id = products.id
            WHERE purchases.user_id = ?
            ORDER BY purchases.id DESC
        """, (message.from_user.id,))
        services = await cursor.fetchall()

    if not services:
        await message.answer("📦 هنوز سرویسی خریداری نکرده‌اید.")
        return

    for purchase_id, name, config, config_type in services:
        if config_type == "photo":
            await message.bot.send_photo(
                chat_id=message.from_user.id, photo=config,
                caption=f"🔹 <b>{escape(name)}</b>\n🆔 خرید: <code>{purchase_id}</code>",
                parse_mode="HTML",
            )
        else:
            await message.answer(
                f"🔹 <b>{escape(name)}</b>\n🆔 خرید: <code>{purchase_id}</code>\n"
                f"🔐 کانفیگ:\n<pre>{escape(config)}</pre>",
                parse_mode="HTML",
            )


# ============================================================
# تست کانفیگ - بخش مشتری
# ============================================================

async def user_already_claimed_test(user_id: int) -> bool:
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id FROM test_configs WHERE claimed_by = ?", (user_id,)
        )
        return (await cursor.fetchone()) is not None


async def claim_test_config(user_id: int):
    """یک آیتم تست آزاد را به کاربر تخصیص می‌دهد و برمی‌گرداند."""
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute("""
            SELECT id, config, config_type FROM test_configs
            WHERE claimed = 0 ORDER BY id ASC LIMIT 1
        """)
        row = await cursor.fetchone()

        if not row:
            await db.rollback()
            return None

        tc_id, config, config_type = row
        await db.execute("""
            UPDATE test_configs SET claimed = 1, claimed_by = ? WHERE id = ?
        """, (user_id, tc_id))
        await db.commit()
        return config, config_type


@dp.message(F.text == "🧪 تست کانفیگ")
async def test_config_menu(message: Message):
    if not await check_access(message):
        return

    user_id = message.from_user.id

    if await user_already_claimed_test(user_id):
        await message.answer("⚠️ شما قبلاً کانفیگ تست خود را دریافت کرده‌اید. هر کاربر فقط یک بار می‌تواند تست بگیرد.")
        return

    result = await claim_test_config(user_id)

    if not result:
        await message.answer("❌ در حال حاضر کانفیگ تستی موجود نیست.")
        return

    config, config_type = result

    if config_type == "photo":
        await message.bot.send_photo(
            chat_id=user_id, photo=config,
            caption="🧪 <b>کانفیگ تست شما</b>\n\nاین کانفیگ فقط یک‌بار قابل دریافت بود.",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "🧪 <b>کانفیگ تست شما:</b>\n\n"
            f"<pre>{escape(config)}</pre>\n\n"
            "این کانفیگ فقط یک‌بار قابل دریافت بود.",
            parse_mode="HTML",
        )


# ============================================================
# مدیریت کانفیگ تست - پنل ادمین
# ============================================================

@dp.message(F.text == "🧪 مدیریت کانفیگ تست")
async def test_config_admin_menu(message: Message):
    if not has_permission(message.from_user.id, "test_configs"):
        return

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM test_configs WHERE claimed = 0")
        remaining = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM test_configs WHERE claimed = 1")
        used = (await cursor.fetchone())[0]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ افزودن کانفیگ تست (متنی)", callback_data="tc_add_text")],
            [InlineKeyboardButton(text="📸 شارژ کانفیگ تست (عکسی)", callback_data="tc_add_photo")],
        ]
    )
    await message.answer(
        f"🧪 <b>مدیریت کانفیگ تست</b>\n\n"
        f"📦 باقی‌مانده (آزاد): <b>{remaining}</b>\n"
        f"✅ استفاده‌شده: <b>{used}</b>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "tc_add_text")
async def tc_add_text_start(callback: CallbackQuery, state: FSMContext):
    if not has_permission(callback.from_user.id, "test_configs"):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return
    await state.set_state(TestConfigStates.waiting_config)
    await callback.message.answer(
        "متن کانفیگ تست را ارسال کنید.",
        reply_markup=admin_cancel_keyboard(),
    )
    await callback.answer()


@dp.message(TestConfigStates.waiting_config)
async def tc_add_text_save(message: Message, state: FSMContext):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            INSERT INTO test_configs (config, config_type, claimed, created_at)
            VALUES (?, 'text', 0, ?)
        """, (message.text.strip(), datetime.now().isoformat()))
        await db.commit()

    await state.clear()
    await message.answer(
        "✅ کانفیگ تست اضافه شد.",
        reply_markup=admin_keyboard(message.from_user.id),
    )


@dp.callback_query(F.data == "tc_add_photo")
async def tc_add_photo_start(callback: CallbackQuery, state: FSMContext):
    if not has_permission(callback.from_user.id, "test_configs"):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    await state.update_data(count=0)
    await state.set_state(TestConfigBulkPhotoStates.waiting_photos)

    await callback.message.answer(
        "📸 عکس‌های کانفیگ تست را یکی‌یکی ارسال کن.\n"
        "هر عکس = یک کانفیگ تست یک‌بارمصرف.\n\n"
        "وقتی تمام شد روی دکمه پایین بزن یا بنویس «پایان».",
        reply_markup=bulk_photo_keyboard("finish_tc_photo"),
    )
    await callback.answer()


@dp.message(TestConfigBulkPhotoStates.waiting_photos, F.photo)
async def tc_photo_receive(message: Message, state: FSMContext):
    data = await state.get_data()
    photo = message.photo[-1]

    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            INSERT INTO test_configs (config, config_type, claimed, created_at)
            VALUES (?, 'photo', 0, ?)
        """, (photo.file_id, datetime.now().isoformat()))
        await db.commit()

    new_count = data.get("count", 0) + 1
    await state.update_data(count=new_count)
    await message.answer(f"✅ اضافه شد. (تعداد این دور: {new_count})")


@dp.message(TestConfigBulkPhotoStates.waiting_photos, F.text.lower() == "پایان")
async def tc_photo_finish_text(message: Message, state: FSMContext):
    await finish_tc_photo_common(message, state)


@dp.callback_query(F.data == "finish_tc_photo", TestConfigBulkPhotoStates.waiting_photos)
async def tc_photo_finish_button(callback: CallbackQuery, state: FSMContext):
    await finish_tc_photo_common(callback.message, state)
    await callback.answer()


async def finish_tc_photo_common(message: Message, state: FSMContext):
    data = await state.get_data()
    count = data.get("count", 0)

    await state.clear()
    await message.answer(
        f"✅ شارژ کانفیگ تست تمام شد.\n\n📊 تعداد اضافه شده: <b>{count}</b>",
        reply_markup=admin_keyboard(message.from_user.id),
        parse_mode="HTML",
    )


@dp.message(TestConfigBulkPhotoStates.waiting_photos)
async def tc_photo_invalid(message: Message):
    await message.answer("⚠️ لطفاً عکس ارسال کن یا برای پایان بنویس «پایان».")


# ============================================================
# مدیریت کد تخفیف - پنل ادمین
# ============================================================

@dp.message(F.text == "🏷 مدیریت کد تخفیف")
async def discount_admin_menu(message: Message):
    if not has_permission(message.from_user.id, "discounts"):
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ افزودن کد تخفیف", callback_data="dc_add")],
            [InlineKeyboardButton(text="📋 لیست کدهای تخفیف", callback_data="dc_list")],
        ]
    )
    await message.answer("🏷 مدیریت کد تخفیف", reply_markup=keyboard)


@dp.callback_query(F.data == "dc_add")
async def dc_add_start(callback: CallbackQuery, state: FSMContext):
    if not has_permission(callback.from_user.id, "discounts"):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return
    await state.set_state(DiscountStates.waiting_code)
    await callback.message.answer(
        "کد تخفیف را وارد کنید (مثال: OFF20):",
        reply_markup=admin_cancel_keyboard(),
    )
    await callback.answer()


@dp.message(DiscountStates.waiting_code)
async def dc_add_code(message: Message, state: FSMContext):
    code = message.text.strip().upper()

    existing = await get_discount_code(code)
    if existing:
        await message.answer("❌ این کد تخفیف قبلاً ثبت شده است.")
        return

    await state.update_data(code=code)
    await state.set_state(DiscountStates.waiting_type)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="درصدی از قیمت خرید", callback_data="dctype:percent")],
            [InlineKeyboardButton(text="مقدار ثابت از قیمت خرید", callback_data="dctype:fixed")],
            [InlineKeyboardButton(text="شارژ مستقیم کیف پول", callback_data="dctype:wallet")],
            [InlineKeyboardButton(text="❌ انصراف", callback_data="admin_cancel")],
        ]
    )
    await message.answer("نوع کد تخفیف را انتخاب کنید:", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("dctype:"), DiscountStates.waiting_type)
async def dc_add_type(callback: CallbackQuery, state: FSMContext):
    dtype = callback.data.split(":")[1]
    await state.update_data(discount_type=dtype)
    await state.set_state(DiscountStates.waiting_value)

    if dtype == "percent":
        prompt = "مقدار درصد تخفیف را وارد کنید (مثال: 20 برای ۲۰٪)"
    elif dtype == "fixed":
        prompt = "مقدار ثابت تخفیف را به تومان وارد کنید."
    else:
        prompt = "مقداری که باید به کیف پول کاربر اضافه شود را به تومان وارد کنید."

    await callback.message.answer(prompt, reply_markup=admin_cancel_keyboard())
    await callback.answer()


@dp.message(DiscountStates.waiting_value)
async def dc_add_value(message: Message, state: FSMContext):
    try:
        value = int(message.text.replace(",", "").strip())
        if value <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ لطفاً یک عدد مثبت وارد کنید.")
        return

    await state.update_data(value=value)
    await state.set_state(DiscountStates.waiting_max_uses)
    await message.answer(
        "حداکثر تعداد کل استفاده از این کد چند بار باشد؟ (عدد وارد کنید، یا 0 برای نامحدود)",
        reply_markup=admin_cancel_keyboard(),
    )


@dp.message(DiscountStates.waiting_max_uses)
async def dc_add_max_uses(message: Message, state: FSMContext):
    try:
        max_uses = int(message.text.strip())
        if max_uses < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر وارد کنید.")
        return

    data = await state.get_data()

    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            INSERT INTO discount_codes (code, discount_type, value, max_uses, used_count, active, created_at)
            VALUES (?, ?, ?, ?, 0, 1, ?)
        """, (data["code"], data["discount_type"], data["value"],
              max_uses if max_uses > 0 else None, datetime.now().isoformat()))
        await db.commit()

    await state.clear()
    await message.answer(
        f"✅ کد تخفیف <code>{escape(data['code'])}</code> ثبت شد.",
        reply_markup=admin_keyboard(message.from_user.id),
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "dc_list")
async def dc_list(callback: CallbackQuery):
    if not has_permission(callback.from_user.id, "discounts"):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT code, discount_type, value, max_uses, used_count, active
            FROM discount_codes ORDER BY id DESC
        """)
        rows = await cursor.fetchall()

    if not rows:
        await callback.message.answer("لیست خالی است.")
        await callback.answer()
        return

    text = "🏷 <b>کدهای تخفیف</b>\n\n"
    for code, dtype, value, max_uses, used_count, active in rows:
        status = "فعال" if active else "غیرفعال"
        limit = max_uses if max_uses else "نامحدود"
        text += (
            f"🔑 <code>{escape(code)}</code> | نوع: {dtype} | مقدار: {value:,}\n"
            f"   استفاده: {used_count}/{limit} | {status}\n"
        )

    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


# ============================================================
# لیست مشتری‌ها - پنل ادمین
# ============================================================

@dp.message(F.text == "👥 لیست مشتری‌ها")
async def customers_list(message: Message):
    if not has_permission(message.from_user.id, "customers"):
        return

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT user_id, username, first_name, wallet_balance, is_reseller
            FROM users ORDER BY user_id DESC
        """)
        rows = await cursor.fetchall()

    if not rows:
        await message.answer("هیچ کاربری ثبت نشده است.")
        return

    chunk = ""
    for user_id, username, first_name, wallet, is_reseller in rows:
        uname = f"@{username}" if username else "-"
        rep = " 🤝" if is_reseller else ""
        line = f"🆔 <code>{user_id}</code> | {escape(first_name or '')} | {escape(uname)} | 💰{wallet:,}{rep}\n"
        if len(chunk) + len(line) > 3500:
            await message.answer(chunk, parse_mode="HTML")
            chunk = ""
        chunk += line

    if chunk:
        await message.answer(chunk, parse_mode="HTML")

    await message.answer(f"👥 تعداد کل کاربران: <b>{len(rows)}</b>", parse_mode="HTML")


# ============================================================
# مدیریت کارت‌های بانکی
# توضیح: پیش‌فرض فقط رئیس دسترسی دارد، اما با دادن دسترسی «cards»
# به یک ادمین، آن ادمین هم می‌تواند این بخش را مدیریت کند.
# ============================================================

@dp.message(F.text == "💳 مدیریت کارت‌ها")
async def cards_admin_menu(message: Message):
    if not has_permission(message.from_user.id, "cards"):
        await message.answer("⛔ شما به این بخش دسترسی ندارید.")
        return

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM cards WHERE active = 1")
        count = (await cursor.fetchone())[0]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ افزودن کارت", callback_data="card_add")],
            [InlineKeyboardButton(text="📋 لیست کارت‌ها", callback_data="card_list")],
        ]
    )
    await message.answer(
        f"💳 مدیریت کارت‌های بانکی\n\nتعداد کارت فعال: {count}/{MAX_CARDS}",
        reply_markup=keyboard,
    )


@dp.callback_query(F.data == "card_add")
async def card_add_start(callback: CallbackQuery, state: FSMContext):
    if not has_permission(callback.from_user.id, "cards"):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM cards WHERE active = 1")
        count = (await cursor.fetchone())[0]

    if count >= MAX_CARDS:
        await callback.answer(f"❌ حداکثر {MAX_CARDS} کارت قابل ثبت است.", show_alert=True)
        return

    await state.set_state(CardStates.waiting_number)
    await callback.message.answer("شماره کارت جدید را وارد کنید.", reply_markup=admin_cancel_keyboard())
    await callback.answer()


@dp.message(CardStates.waiting_number)
async def card_add_number(message: Message, state: FSMContext):
    await state.update_data(card_number=message.text.strip())
    await state.set_state(CardStates.waiting_owner)
    await message.answer("نام صاحب کارت را وارد کنید.", reply_markup=admin_cancel_keyboard())


@dp.message(CardStates.waiting_owner)
async def card_add_owner(message: Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            INSERT INTO cards (card_number, card_owner, active, created_at)
            VALUES (?, ?, 1, ?)
        """, (data["card_number"], message.text.strip(), datetime.now().isoformat()))
        await db.commit()
    await state.clear()
    await message.answer("✅ کارت با موفقیت اضافه شد.", reply_markup=admin_keyboard(message.from_user.id))


@dp.callback_query(F.data == "card_list")
async def card_list(callback: CallbackQuery):
    if not has_permission(callback.from_user.id, "cards"):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT id, card_number, card_owner, active FROM cards ORDER BY id DESC")
        rows = await cursor.fetchall()

    if not rows:
        await callback.message.answer("هیچ کارتی ثبت نشده است.")
        await callback.answer()
        return

    for card_id, number, owner, active in rows:
        status = "فعال" if active else "غیرفعال"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text=("🔴 غیرفعال کردن" if active else "🟢 فعال کردن"),
                    callback_data=f"card_toggle:{card_id}",
                )
            ]]
        )
        await callback.message.answer(
            f"🆔 {card_id} | <code>{escape(number)}</code> | {escape(owner)} | {status}",
            reply_markup=keyboard, parse_mode="HTML",
        )

    await callback.answer()


@dp.callback_query(F.data.startswith("card_toggle:"))
async def card_toggle(callback: CallbackQuery):
    if not has_permission(callback.from_user.id, "cards"):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    card_id = int(callback.data.split(":")[1])

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT active FROM cards WHERE id = ?", (card_id,))
        row = await cursor.fetchone()
        if not row:
            await callback.answer("❌ کارت پیدا نشد.", show_alert=True)
            return
        new_state = 0 if row[0] else 1
        await db.execute("UPDATE cards SET active = ? WHERE id = ?", (new_state, card_id))
        await db.commit()

    await callback.answer("✅ وضعیت کارت تغییر کرد.")
    try:
        await callback.message.delete()
    except Exception:
        pass


# ============================================================
# مدیریت ادمین‌ها + دسترسی‌های جزئی
# توضیح: این بخش پیش‌فرض فقط برای رئیس است، اما با دادن دسترسی
# «admins» به یک ادمین خاص، آن ادمین هم می‌تواند از این بخش
# استفاده کند (افزودن/حذف ادمین و تغییر دسترسی‌ها).
# ============================================================

@dp.message(F.text == "👨‍💼 مدیریت ادمین‌ها")
async def admins_menu(message: Message):
    if not has_permission(message.from_user.id, "admins"):
        await message.answer("⛔ شما به این بخش دسترسی ندارید.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ افزودن ادمین", callback_data="admin_add")],
            [InlineKeyboardButton(text="📋 لیست و دسترسی‌های ادمین‌ها", callback_data="admin_list")],
        ]
    )
    await message.answer(
        f"👨‍💼 مدیریت ادمین‌ها\n\nتعداد ادمین‌های فعلی: {len(ADMIN_IDS_CACHE)}",
        reply_markup=keyboard,
    )


@dp.callback_query(F.data == "admin_add")
async def admin_add_start(callback: CallbackQuery, state: FSMContext):
    if not has_permission(callback.from_user.id, "admins"):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return
    await state.set_state(AdminManageStates.waiting_id)
    await callback.message.answer(
        "🆔 آیدی عددی کاربری که می‌خواهی ادمین شود را ارسال کن.\n\n"
        "(کاربر باید حداقل یک بار /start ربات را زده باشد یا خودت آیدی عددی او را از قبل داشته باشی.)\n\n"
        "دسترسی‌های پیش‌فرض او: محصولات، کانفیگ تست، کد تخفیف، مشتری‌ها، "
        "سفارش‌ها، نمایندگی. (کارت‌ها و مدیریت ادمین‌ها را بعداً می‌توانی جدا اضافه کنی.)",
        reply_markup=admin_cancel_keyboard(),
    )
    await callback.answer()


@dp.message(AdminManageStates.waiting_id)
async def admin_add_process(message: Message, state: FSMContext):
    try:
        new_admin_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ لطفاً یک آیدی عددی معتبر ارسال کن.")
        return

    if new_admin_id == SUPER_ADMIN_ID:
        await message.answer("❌ این کاربر همان رئیس اصلی است.")
        await state.clear()
        return

    if new_admin_id in ADMIN_IDS_CACHE:
        await message.answer("⚠️ این کاربر از قبل ادمین است.")
        await state.clear()
        return

    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)
        """, (new_admin_id, datetime.now().isoformat()))
        for perm in DEFAULT_ADMIN_PERMISSIONS:
            await db.execute("""
                INSERT OR IGNORE INTO admin_permissions (user_id, permission) VALUES (?, ?)
            """, (new_admin_id, perm))
        await db.commit()

    ADMIN_IDS_CACHE.add(new_admin_id)
    ADMIN_PERMISSIONS_CACHE[new_admin_id] = set(DEFAULT_ADMIN_PERMISSIONS)
    await state.clear()

    await message.answer(
        f"✅ کاربر <code>{new_admin_id}</code> با موفقیت ادمین شد.",
        reply_markup=admin_keyboard(message.from_user.id),
        parse_mode="HTML",
    )

    try:
        await message.bot.send_message(new_admin_id, "👑 شما توسط رئیس به عنوان ادمین ربات انتخاب شدید.")
    except Exception:
        pass


@dp.callback_query(F.data == "admin_list")
async def admin_list(callback: CallbackQuery):
    if not has_permission(callback.from_user.id, "admins"):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    if not ADMIN_IDS_CACHE:
        await callback.message.answer("هیچ ادمین عادی‌ای ثبت نشده است.")
        await callback.answer()
        return

    for admin_id in sorted(ADMIN_IDS_CACHE):
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔧 تنظیم دسترسی‌ها", callback_data=f"admin_perms:{admin_id}")],
                [InlineKeyboardButton(text="❌ حذف ادمین", callback_data=f"admin_remove:{admin_id}")],
            ]
        )
        await callback.message.answer(
            f"🆔 <code>{admin_id}</code>", reply_markup=keyboard, parse_mode="HTML",
        )

    await callback.answer()


def permission_toggle_keyboard(admin_id: int) -> InlineKeyboardMarkup:
    perms = ADMIN_PERMISSIONS_CACHE.get(admin_id, set())
    rows = []
    for key, label in PERMISSIONS.items():
        mark = "✅" if key in perms else "◻️"
        rows.append([InlineKeyboardButton(
            text=f"{mark} {label}",
            callback_data=f"admin_perm_toggle:{admin_id}:{key}",
        )])
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت به لیست", callback_data="admin_list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.callback_query(F.data.startswith("admin_perms:"))
async def admin_perms_menu(callback: CallbackQuery):
    if not has_permission(callback.from_user.id, "admins"):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    admin_id = int(callback.data.split(":")[1])
    if admin_id not in ADMIN_IDS_CACHE:
        await callback.answer("❌ این ادمین دیگر وجود ندارد.", show_alert=True)
        return

    try:
        await callback.message.edit_text(
            f"🔧 <b>دسترسی‌های ادمین</b> <code>{admin_id}</code>\n\n"
            "روی هر گزینه بزنید تا فعال/غیرفعال شود.\n"
            "⚠️ توجه: دادن دسترسی «مدیریت ادمین‌ها» یا «مدیریت کارت‌ها» به یک ادمین بسیار حساس است.",
            reply_markup=permission_toggle_keyboard(admin_id),
            parse_mode="HTML",
        )
    except Exception:
        await callback.message.answer(
            f"🔧 <b>دسترسی‌های ادمین</b> <code>{admin_id}</code>\n\n"
            "روی هر گزینه بزنید تا فعال/غیرفعال شود.",
            reply_markup=permission_toggle_keyboard(admin_id),
            parse_mode="HTML",
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("admin_perm_toggle:"))
async def admin_perm_toggle(callback: CallbackQuery):
    if not has_permission(callback.from_user.id, "admins"):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    _, admin_id_str, perm = callback.data.split(":", 2)
    admin_id = int(admin_id_str)

    if admin_id not in ADMIN_IDS_CACHE or perm not in PERMISSIONS:
        await callback.answer("❌ نامعتبر.", show_alert=True)
        return

    current = set(ADMIN_PERMISSIONS_CACHE.get(admin_id, set()))

    async with aiosqlite.connect(DATABASE) as db:
        if perm in current:
            await db.execute(
                "DELETE FROM admin_permissions WHERE user_id = ? AND permission = ?",
                (admin_id, perm),
            )
            current.discard(perm)
        else:
            await db.execute(
                "INSERT OR IGNORE INTO admin_permissions (user_id, permission) VALUES (?, ?)",
                (admin_id, perm),
            )
            current.add(perm)
        await db.commit()

    ADMIN_PERMISSIONS_CACHE[admin_id] = current

    try:
        await callback.message.edit_reply_markup(reply_markup=permission_toggle_keyboard(admin_id))
    except Exception:
        pass
    await callback.answer("✅ به‌روزرسانی شد.")


@dp.callback_query(F.data.startswith("admin_remove:"))
async def admin_remove(callback: CallbackQuery):
    if not has_permission(callback.from_user.id, "admins"):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    target_id = int(callback.data.split(":")[1])

    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("DELETE FROM admins WHERE user_id = ?", (target_id,))
        await db.execute("DELETE FROM admin_permissions WHERE user_id = ?", (target_id,))
        await db.commit()

    ADMIN_IDS_CACHE.discard(target_id)
    ADMIN_PERMISSIONS_CACHE.pop(target_id, None)

    await callback.answer("✅ ادمین حذف شد.")
    try:
        await callback.message.delete()
    except Exception:
        pass

    try:
        await callback.bot.send_message(target_id, "⚠️ دسترسی ادمینی شما توسط رئیس لغو شد.")
    except Exception:
        pass


# ============================================================
# تنظیمات ربات (فقط رئیس) - آیدی پشتیبانی و مقدار جایزه دعوت
# ============================================================

@dp.message(F.text == "⚙️ تنظیمات ربات")
async def settings_menu(message: Message):
    if not is_super_admin(message.from_user.id):
        await message.answer("⛔ فقط رئیس اصلی به این بخش دسترسی دارد.")
        return

    support = get_support_username() or "تنظیم نشده"
    reward = get_referral_reward()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📞 تغییر آیدی پشتیبانی", callback_data="settings_support")],
            [InlineKeyboardButton(text="🎁 تغییر مقدار جایزه دعوت دوستان", callback_data="settings_referral")],
        ]
    )
    await message.answer(
        "⚙️ <b>تنظیمات ربات</b>\n\n"
        f"📞 آیدی پشتیبانی فعلی: {escape(support)}\n"
        f"🎁 جایزه دعوت دوستان فعلی: {reward:,} تومان",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "settings_support")
async def settings_support_start(callback: CallbackQuery, state: FSMContext):
    if not is_super_admin(callback.from_user.id):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return
    await state.set_state(SettingsStates.waiting_support_username)
    await callback.message.answer(
        "📞 آیدی یوزرنیم پشتیبانی جدید را وارد کنید (مثال: @spayder_support).\n"
        "برای غیرفعال کردن پشتیبانی، عدد 0 را ارسال کنید.",
        reply_markup=admin_cancel_keyboard(),
    )
    await callback.answer()


@dp.message(SettingsStates.waiting_support_username)
async def settings_support_save(message: Message, state: FSMContext):
    text = message.text.strip()
    value = "" if text == "0" else text

    await set_setting("support_username", value)
    await state.clear()
    await message.answer(
        "✅ آیدی پشتیبانی به‌روزرسانی شد.",
        reply_markup=admin_keyboard(message.from_user.id),
    )


@dp.callback_query(F.data == "settings_referral")
async def settings_referral_start(callback: CallbackQuery, state: FSMContext):
    if not is_super_admin(callback.from_user.id):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return
    await state.set_state(SettingsStates.waiting_referral_reward)
    await callback.message.answer(
        "🎁 مقدار جدید جایزه دعوت دوستان را به تومان و فقط به عدد وارد کنید.\n\nمثال:\n25000",
        reply_markup=admin_cancel_keyboard(),
    )
    await callback.answer()


@dp.message(SettingsStates.waiting_referral_reward)
async def settings_referral_save(message: Message, state: FSMContext):
    try:
        value = int(message.text.replace(",", "").strip())
        if value < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر (صفر یا بیشتر) وارد کنید.")
        return

    await set_setting("referral_reward", str(value))
    await state.clear()
    await message.answer(
        f"✅ مقدار جایزه دعوت دوستان به {value:,} تومان تغییر کرد.",
        reply_markup=admin_keyboard(message.from_user.id),
    )


# ============================================================
# منوی اصلی (بازگشت)
# ============================================================

@dp.message(F.text == "🏠 منوی اصلی")
async def back_main(message: Message):
    if not message.from_user:
        return
    if is_admin(message.from_user.id):
        await message.answer("🏠 منوی اصلی پنل مدیریت", reply_markup=admin_keyboard(message.from_user.id))
    else:
        await message.answer("🏠 منوی اصلی", reply_markup=main_keyboard())


# ============================================================
# افزودن محصول
# ============================================================

@dp.message(F.text == "➕ افزودن محصول")
async def add_product_start(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "products"):
        return
    await state.set_state(ProductStates.waiting_code)
    await message.answer(
        "➕ <b>افزودن محصول</b>\n\nکد محصول را وارد کنید.\n\nمثال:\n<code>v2ray-1m</code>",
        reply_markup=admin_cancel_keyboard(),
        parse_mode="HTML",
    )


@dp.message(ProductStates.waiting_code)
async def add_product_code(message: Message, state: FSMContext):
    code = message.text.strip()

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT id FROM products WHERE code = ?", (code,))
        exists = await cursor.fetchone()

    if exists:
        await message.answer("❌ این کد محصول قبلاً استفاده شده است.")
        return

    await state.update_data(code=code)
    await state.set_state(ProductStates.waiting_name)
    await message.answer("نام محصول را وارد کنید.", reply_markup=admin_cancel_keyboard())


@dp.message(ProductStates.waiting_name)
async def add_product_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(ProductStates.waiting_price)
    await message.answer(
        "قیمت محصول را فقط به عدد وارد کنید.\n\nمثال:\n150000",
        reply_markup=admin_cancel_keyboard(),
    )


@dp.message(ProductStates.waiting_price)
async def add_product_price(message: Message, state: FSMContext):
    try:
        price = int(message.text.replace(",", "").strip())
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ قیمت باید یک عدد مثبت باشد.")
        return

    await state.update_data(price=price)
    await state.set_state(ProductStates.waiting_description)
    await message.answer("توضیحات محصول را وارد کنید.", reply_markup=admin_cancel_keyboard())


@dp.message(ProductStates.waiting_description)
async def add_product_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(ProductStates.waiting_photo)
    await message.answer("🖼 تصویر محصول را ارسال کنید.", reply_markup=admin_cancel_keyboard())


@dp.message(ProductStates.waiting_photo, F.photo)
async def add_product_photo(message: Message, state: FSMContext):
    photo = message.photo[-1]
    data = await state.get_data()

    async with aiosqlite.connect(DATABASE) as db:
        try:
            await db.execute("""
                INSERT INTO products (code, name, price, description, photo_file_id, active, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
            """, (data["code"], data["name"], data["price"], data["description"],
                  photo.file_id, datetime.now().isoformat()))
            await db.commit()
        except Exception as e:
            await state.clear()
            await message.answer(f"❌ خطا در ثبت محصول:\n{escape(str(e))}", parse_mode="HTML")
            return

    await state.clear()
    await message.answer("✅ محصول با موفقیت اضافه شد.", reply_markup=admin_keyboard(message.from_user.id))


# ============================================================
# افزودن موجودی متنی
# ============================================================

@dp.message(F.text == "📦 افزودن موجودی (متنی)")
async def add_stock_start(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "products"):
        return
    await state.set_state(StockStates.waiting_product_code)
    await message.answer(
        "کد محصولی که می‌خواهی موجودی به آن اضافه کنی را وارد کن.",
        reply_markup=admin_cancel_keyboard(),
    )


@dp.message(StockStates.waiting_product_code)
async def stock_product_code(message: Message, state: FSMContext):
    code = message.text.strip()

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT id, name FROM products WHERE code = ?", (code,))
        product = await cursor.fetchone()

    if not product:
        await message.answer("❌ محصولی با این کد پیدا نشد.")
        return

    await state.update_data(product_id=product[0], product_name=product[1])
    await state.set_state(StockStates.waiting_config)
    await message.answer(
        f"📦 محصول: <b>{escape(product[1])}</b>\n\nحالا کانفیگ را ارسال کن.\n\nهر کانفیگ = یک موجودی",
        reply_markup=admin_cancel_keyboard(),
        parse_mode="HTML",
    )


@dp.message(StockStates.waiting_config)
async def stock_config(message: Message, state: FSMContext):
    data = await state.get_data()
    config = message.text.strip()

    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            INSERT INTO stock (product_id, config, config_type, sold, created_at)
            VALUES (?, ?, 'text', 0, ?)
        """, (data["product_id"], config, datetime.now().isoformat()))
        await db.commit()

        cursor = await db.execute(
            "SELECT COUNT(*) FROM stock WHERE product_id = ? AND sold = 0", (data["product_id"],)
        )
        count = (await cursor.fetchone())[0]

    await state.clear()
    await message.answer(
        f"✅ موجودی با موفقیت اضافه شد.\n\n📦 محصول: <b>{escape(data['product_name'])}</b>\n"
        f"📊 موجودی فعلی: <b>{count}</b>",
        reply_markup=admin_keyboard(message.from_user.id),
        parse_mode="HTML",
    )


# ============================================================
# افزودن موجودی عکسی (محصولات)
# ============================================================

@dp.message(F.text == "📸 افزودن موجودی (عکسی)")
async def add_photo_stock_start(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "products"):
        return
    await state.set_state(BulkPhotoStockStates.waiting_product_code)
    await message.answer(
        "کد محصولی که می‌خواهی موجودی عکسی به آن اضافه کنی را وارد کن.",
        reply_markup=admin_cancel_keyboard(),
    )


@dp.message(BulkPhotoStockStates.waiting_product_code)
async def photo_stock_product_code(message: Message, state: FSMContext):
    code = message.text.strip()

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT id, name FROM products WHERE code = ?", (code,))
        product = await cursor.fetchone()

    if not product:
        await message.answer("❌ محصولی با این کد پیدا نشد.")
        return

    await state.update_data(product_id=product[0], product_name=product[1], count=0)
    await state.set_state(BulkPhotoStockStates.waiting_photos)

    await message.answer(
        f"📦 محصول: <b>{escape(product[1])}</b>\n\n"
        "حالا عکس‌ها را یکی‌یکی ارسال کن. هر عکس = یک موجودی.\n"
        "وقتی تمام شد روی دکمه پایین بزن یا بنویس «پایان».",
        reply_markup=bulk_photo_keyboard("finish_photo_stock"),
        parse_mode="HTML",
    )


@dp.message(BulkPhotoStockStates.waiting_photos, F.photo)
async def photo_stock_receive(message: Message, state: FSMContext):
    data = await state.get_data()
    photo = message.photo[-1]

    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            INSERT INTO stock (product_id, config, config_type, sold, created_at)
            VALUES (?, ?, 'photo', 0, ?)
        """, (data["product_id"], photo.file_id, datetime.now().isoformat()))
        await db.commit()

    new_count = data.get("count", 0) + 1
    await state.update_data(count=new_count)
    await message.answer(f"✅ اضافه شد. (تعداد این دور: {new_count})")


@dp.message(BulkPhotoStockStates.waiting_photos, F.text.lower() == "پایان")
async def photo_stock_finish_text(message: Message, state: FSMContext):
    await finish_photo_stock_common(message, state)


@dp.callback_query(F.data == "finish_photo_stock", BulkPhotoStockStates.waiting_photos)
async def photo_stock_finish_button(callback: CallbackQuery, state: FSMContext):
    await finish_photo_stock_common(callback.message, state)
    await callback.answer()


async def finish_photo_stock_common(message: Message, state: FSMContext):
    data = await state.get_data()
    count = data.get("count", 0)
    product_name = data.get("product_name", "")

    await state.clear()
    await message.answer(
        f"✅ افزودن موجودی عکسی تمام شد.\n\n📦 محصول: <b>{escape(product_name)}</b>\n"
        f"📊 تعداد اضافه شده: <b>{count}</b>",
        reply_markup=admin_keyboard(message.from_user.id),
        parse_mode="HTML",
    )


@dp.message(BulkPhotoStockStates.waiting_photos)
async def photo_stock_invalid(message: Message):
    await message.answer("⚠️ لطفاً عکس ارسال کن یا برای پایان بنویس «پایان».")


# ============================================================
# لیست محصولات
# ============================================================

@dp.message(F.text == "📋 لیست محصولات")
async def products_list(message: Message):
    if not has_permission(message.from_user.id, "products"):
        return

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT p.id, p.code, p.name, p.price, p.active, COUNT(s.id)
            FROM products p
            LEFT JOIN stock s ON p.id = s.product_id AND s.sold = 0
            GROUP BY p.id ORDER BY p.id DESC
        """)
        products = await cursor.fetchall()

    if not products:
        await message.answer("📋 هنوز محصولی ثبت نشده است.")
        return

    text = "📋 <b>لیست محصولات</b>\n\n"
    for product_id, code, name, price, active, stock_count in products:
        status = "فعال" if active else "غیرفعال"
        text += (
            f"🆔 ID: <code>{product_id}</code>\n"
            f"🔑 کد: <code>{escape(code)}</code>\n"
            f"📦 نام: <b>{escape(name)}</b>\n"
            f"💰 قیمت: {price:,} تومان\n"
            f"📊 موجودی: {stock_count}\n"
            f"🔘 وضعیت: {status}\n"
            "━━━━━━━━━━━━━━\n"
        )

    await message.answer(text, parse_mode="HTML")


# ============================================================
# ویرایش محصول
# ============================================================

@dp.message(F.text == "✏️ ویرایش محصول")
async def edit_product_start(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "products"):
        return
    await state.set_state(EditProductStates.waiting_code)
    await message.answer(
        "کد محصولی که می‌خواهی ویرایش کنی را وارد کن.",
        reply_markup=admin_cancel_keyboard(),
    )


@dp.message(EditProductStates.waiting_code)
async def edit_product_code(message: Message, state: FSMContext):
    code = message.text.strip()

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT id, name FROM products WHERE code = ?", (code,))
        product = await cursor.fetchone()

    if not product:
        await message.answer("❌ محصول پیدا نشد.")
        return

    await state.update_data(product_id=product[0])

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 نام", callback_data="editfield:name"),
                InlineKeyboardButton(text="💰 قیمت", callback_data="editfield:price"),
            ],
            [InlineKeyboardButton(text="📄 توضیحات", callback_data="editfield:description")],
            [InlineKeyboardButton(text="🔘 فعال/غیرفعال", callback_data="editfield:active")],
            [InlineKeyboardButton(text="❌ انصراف", callback_data="admin_cancel")],
        ]
    )

    await state.set_state(EditProductStates.waiting_field)
    await message.answer(
        f"محصول: <b>{escape(product[1])}</b>\n\nچه چیزی را می‌خواهی ویرایش کنی؟",
        reply_markup=keyboard, parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("editfield:"))
async def edit_field_callback(callback: CallbackQuery, state: FSMContext):
    if not has_permission(callback.from_user.id, "products"):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    field = callback.data.split(":")[1]
    allowed_fields = {"name", "price", "description", "active"}

    if field not in allowed_fields:
        await callback.answer("❌ گزینه نامعتبر است.", show_alert=True)
        return

    if field == "active":
        data = await state.get_data()
        async with aiosqlite.connect(DATABASE) as db:
            cursor = await db.execute("SELECT active FROM products WHERE id = ?", (data["product_id"],))
            current = (await cursor.fetchone())[0]
            new_val = 0 if current else 1
            await db.execute("UPDATE products SET active = ? WHERE id = ?", (new_val, data["product_id"]))
            await db.commit()
        await state.clear()
        await callback.message.answer(
            "✅ وضعیت محصول تغییر کرد.",
            reply_markup=admin_keyboard(callback.from_user.id),
        )
        await callback.answer()
        return

    await state.update_data(field=field)
    await state.set_state(EditProductStates.waiting_value)

    field_names = {"name": "نام محصول", "price": "قیمت", "description": "توضیحات"}
    await callback.message.answer(
        f"مقدار جدید <b>{field_names[field]}</b> را ارسال کنید.",
        reply_markup=admin_cancel_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.message(EditProductStates.waiting_value)
async def edit_product_value(message: Message, state: FSMContext):
    data = await state.get_data()
    product_id = data["product_id"]
    field = data["field"]
    value = message.text.strip()

    allowed_fields = {"name", "price", "description"}
    if field not in allowed_fields:
        await state.clear()
        await message.answer("❌ خطای امنیتی در ویرایش محصول.")
        return

    if field == "price":
        try:
            value = int(value.replace(",", ""))
            if value <= 0:
                raise ValueError
        except ValueError:
            await message.answer("❌ قیمت باید عدد مثبت باشد.")
            return

    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(f"UPDATE products SET {field} = ? WHERE id = ?", (value, product_id))
        await db.commit()

    await state.clear()
    await message.answer("✅ محصول با موفقیت ویرایش شد.", reply_markup=admin_keyboard(message.from_user.id))


# ============================================================
# پیام ناشناخته
# ============================================================

@dp.message()
async def unknown_message(message: Message):
    if not message.from_user:
        return

    if is_admin(message.from_user.id):
        await message.answer("از گزینه‌های پنل مدیریت استفاده کنید.", reply_markup=admin_keyboard(message.from_user.id))
    else:
        await message.answer("لطفاً از منوی ربات استفاده کنید.", reply_markup=main_keyboard())


# ============================================================
# اجرای ربات
# ============================================================

async def main():
    global BOT_USERNAME

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN خالی است.")

    await init_db()
    await load_admins()
    await load_admin_permissions()
    await load_settings()

    if PROXY_URL:
        session = AiohttpSession(proxy=PROXY_URL)
        bot = Bot(token=BOT_TOKEN, session=session)
        logger.info(f"پراکسی فعال شد: {PROXY_URL}")
    else:
        bot = Bot(token=BOT_TOKEN)
        logger.info("ربات بدون پراکسی اجرا می‌شود.")

    try:
        logger.info("ربات در حال اتصال به Telegram API است...")
        me = await bot.get_me()
        BOT_USERNAME = me.username
        logger.info(f"اتصال موفق! ربات: @{me.username}")
        logger.info("ربات با موفقیت اجرا شد.")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("ربات متوقف شد.")
    except Exception as e:
        logger.exception(f"خطای اصلی ربات: {e}")
