"""
Main keyboards for the bot
"""

from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)


def get_main_keyboard() -> InlineKeyboardMarkup:
    """Get main menu keyboard"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📖 Довідка",
                    callback_data="help"
                ),
                InlineKeyboardButton(
                    text="📊 Статистика",
                    callback_data="stats"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Налаштування",
                    callback_data="settings"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔍 Inline режим",
                    switch_inline_query=""
                ),
            ],
        ]
    )


def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Get settings menu keyboard"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Якість за замовчуванням",
                    callback_data="settings:quality"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔔 Сповіщення",
                    callback_data="settings:notifications"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data="back_to_main"
                ),
            ],
        ]
    )


def get_reply_keyboard() -> ReplyKeyboardMarkup:
    """Get persistent reply keyboard"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📊 Статистика"),
                KeyboardButton(text="⚙️ Налаштування"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=False
    )
