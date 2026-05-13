from aiogram.fsm.state import State, StatesGroup


class ProfileEditState(StatesGroup):
    waiting_for_first_name = State()
    waiting_for_last_name = State()