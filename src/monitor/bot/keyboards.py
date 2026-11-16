from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def dashboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 Targets", callback_data="targets:list"),
                InlineKeyboardButton(text="➕ Add target", callback_data="targets:add"),
            ],
            [
                InlineKeyboardButton(text="⚙️ Settings", callback_data="settings:show"),
                InlineKeyboardButton(text="🩺 Status", callback_data="status:show"),
            ],
        ]
    )
