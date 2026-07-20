from aiogram.fsm.state import State, StatesGroup

class EditLinkStates(StatesGroup):
    choosing_link = State()
    entering_value = State()

class EditOperatorsStates(StatesGroup):
    entering_operator = State()