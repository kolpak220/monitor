from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message


class AdminFilter(BaseFilter):
    def __init__(self, admin_ids: tuple[int, ...]) -> None:
        self.admin_ids = set(admin_ids)

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return bool(user and user.id in self.admin_ids)
