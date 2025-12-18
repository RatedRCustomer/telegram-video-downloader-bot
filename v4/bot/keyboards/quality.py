"""
Quality selection keyboards
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_quality_keyboard(
    url: str,
    platform: str,
    msg_id: int,
    show_audio: bool = False
) -> InlineKeyboardMarkup:
    """Get quality selection keyboard"""
    keyboard = [
        [
            InlineKeyboardButton(
                text="✨ Авто (найкраща до 50MB)",
                callback_data=f"quality:auto:{msg_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                text="1080p",
                callback_data=f"quality:1080p:{msg_id}"
            ),
            InlineKeyboardButton(
                text="720p",
                callback_data=f"quality:720p:{msg_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                text="480p",
                callback_data=f"quality:480p:{msg_id}"
            ),
            InlineKeyboardButton(
                text="360p",
                callback_data=f"quality:360p:{msg_id}"
            ),
        ],
    ]

    # Add audio button for YouTube
    if show_audio:
        keyboard.append([
            InlineKeyboardButton(
                text="🎵 Тільки аудіо (MP3)",
                callback_data=f"audio:{msg_id}"
            ),
        ])

    # Cancel button
    keyboard.append([
        InlineKeyboardButton(
            text="❌ Скасувати",
            callback_data="cancel"
        ),
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_default_quality_keyboard() -> InlineKeyboardMarkup:
    """Get default quality settings keyboard"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✨ Авто",
                    callback_data="set_quality:auto"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="1080p",
                    callback_data="set_quality:1080p"
                ),
                InlineKeyboardButton(
                    text="720p",
                    callback_data="set_quality:720p"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="480p",
                    callback_data="set_quality:480p"
                ),
                InlineKeyboardButton(
                    text="360p",
                    callback_data="set_quality:360p"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data="settings"
                ),
            ],
        ]
    )
