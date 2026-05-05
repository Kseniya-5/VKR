from aiogram.fsm.state import State, StatesGroup


class ProfileEditState(StatesGroup):
    waiting_for_first_name = State()
    waiting_for_last_name = State()


class LinkWebState(StatesGroup):
    waiting_for_link_code = State()


class UploadPhotosState(StatesGroup):
    waiting_for_photos = State()

class DeletePhotosState(StatesGroup):
    waiting_for_replies = State()