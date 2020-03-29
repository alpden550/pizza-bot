import json
import os
from textwrap import dedent

import aioredis
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, LabeledPrice, ParseMode, ReplyKeyboardMarkup, ReplyKeyboardRemove
from aiogram.utils.emoji import emojize
from more_itertools import chunked

import moltin
import utils
from aiogram.types.message import ContentType

storage = RedisStorage2(db=5)
bot = Bot(token=os.getenv('TG_TOKEN'))
dp = Dispatcher(bot=bot, storage=storage)


class BotState(StatesGroup):
    start = State()
    menu = State()
    description = State()
    basket = State()
    geo = State()
    handle_geo = State()
    delivery = State()
    pay = State()


async def get_from_redis(search):
    redis = await aioredis.create_redis_pool('redis://localhost')
    return await redis.get(search)


async def edit_menu(callback: types.CallbackQuery, state: FSMContext, chunk: int):
    keyboard = await create_menu_buttons(chunk=chunk)
    await state.update_data(chunk=chunk)

    return await bot.edit_message_text(
        text=emojize('_Пожалуйста, выберите пиццу или много пицц :pizza:_'),
        chat_id=callback.from_user.id,
        message_id=callback.message.message_id,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )


async def send_detail_message(callback: types.CallbackQuery, state: FSMContext):
    product = await get_from_redis(callback.data)

    if product is None:
        pizza_data = moltin.get_by_id(callback.data)
    else:
        pizza_data = json.loads(product)

    pizza_name = pizza_data['name']
    pizza_text = pizza_data['description']
    pizza_price = pizza_data['meta']['display_price']['with_tax']['formatted']
    image_id = pizza_data['relationships']['main_image']['data']['id']
    image_url = await get_from_redis(image_id)

    if image_url is None:
        image = moltin.get_picture(image_id)
    else:
        image = image_url

    basket_message = moltin.check_product_in_cart(
        callback.from_user.id, callback.data) or ''
    message = f'*{pizza_name}*\n\n{pizza_text}\n\n_Цена {pizza_price}_\n\n{basket_message}'
    keyboard = create_description_buttons()
    await state.update_data(last_product=callback.data)

    return await bot.send_photo(
        chat_id=callback.from_user.id,
        photo=image.decode('utf-8'),
        caption=message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )


async def send_basket_message(callback: types.CallbackQuery, state: FSMContext):
    keyboard = create_basket_buttons(user_id=callback.from_user.id)
    message = moltin.format_basket_for_sending(
        user_id=callback.from_user.id)
    return await bot.send_message(
        chat_id=callback.from_user.id,
        text=message,
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN,
    )


async def create_menu_buttons(chunk=0):
    products = await get_from_redis('products')
    chunks = list(chunked(json.loads(products), 7))

    keyboard = InlineKeyboardMarkup(row_width=1)
    buttons = (InlineKeyboardButton(pr_name, callback_data=pr_id)
               for pr_id, pr_name in chunks[chunk])
    next_button = InlineKeyboardButton('Следующие ➡️', callback_data='next')
    prev_button = InlineKeyboardButton('⬅️ Предыдущие', callback_data='prev')
    keyboard.add(*buttons)

    if chunk == 0:
        keyboard.add(next_button)
    elif chunk == len(chunks) - 1:
        keyboard.add(prev_button)
    else:
        keyboard.row(*(prev_button, next_button))

    keyboard.row(InlineKeyboardButton('Корзина 🛒', callback_data='basket'))
    return keyboard


def create_description_buttons():
    keyboard = InlineKeyboardMarkup(row_width=1)
    buttons_list = [['1 шт', 'cart 1'], ['3 шт', 'cart 3'], ['5 шт', 'cart 5']]
    buttons = (InlineKeyboardButton(name, callback_data=button_id)
               for name, button_id in buttons_list)
    keyboard.row(*buttons)
    keyboard.add(
        InlineKeyboardButton(
            'Назад ↩️',
            callback_data='back_to_menu'))
    keyboard.add(InlineKeyboardButton('Корзина 🛒', callback_data='basket'))
    return keyboard


def create_basket_buttons(user_id):
    basket = moltin.get_cart(user_id)
    total = moltin.get_total(user_id)
    keyboard = InlineKeyboardMarkup(row_width=1)
    buttons = (
        InlineKeyboardButton(
            f'Удалить {product["name"]}',
            callback_data=product['cart_id']) for product in basket)
    keyboard.add(*buttons)
    keyboard.row(
        InlineKeyboardButton(
            'Назад в меню',
            callback_data='back_to_menu'))
    if total != '0':
        keyboard.row(
            InlineKeyboardButton(
                'Оформить заказ',
                callback_data='sell'))
    return keyboard


def create_delivery_buttons(distance):
    keyboard = InlineKeyboardMarkup(row_width=1)
    if distance < 20:
        buttons = (
            InlineKeyboardButton('Доставка', callback_data='delivery'),
            InlineKeyboardButton('Самовывоз', callback_data='pickup'),
        )
        keyboard.add(*buttons)
    else:
        buttons = InlineKeyboardButton('Самовывоз', callback_data='pickup')
        keyboard.add(buttons)
    return keyboard


def create_payment_buttons():
    keyboard = InlineKeyboardMarkup(row_width=1)
    buttons = (
        InlineKeyboardButton('Картой через Telegram 💳', callback_data='telegram'),
        InlineKeyboardButton('Наличными 💵', callback_data='cash'),
    )
    keyboard.add(*buttons)
    return keyboard


@dp.message_handler(commands='start', state='*')
async def handle_start(message: types.Message, state: FSMContext):
    keyboard = await create_menu_buttons(chunk=0)
    await message.answer(
        text=emojize('_Пожалуйста, выберите пиццу или много пицц :pizza:_'),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )
    await state.update_data(chunk=0)
    await BotState.menu.set()


@dp.message_handler(Text(contains='start', ignore_case=True), state='*')
async def handle_start_text(message: types.Message, state: FSMContext):
    await handle_start(message, state)


@dp.callback_query_handler(state=BotState.menu)
async def handle_menu(callback: types.CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    chunk = state_data['chunk']

    if callback.data == 'next':
        await edit_menu(callback, state, chunk + 1)
        await BotState.menu.set()
    elif callback.data == 'prev':
        await edit_menu(callback, state, chunk - 1)
        await BotState.menu.set()
    elif callback.data == 'basket':
        await send_basket_message(callback, state)
        await BotState.basket.set()
        await bot.delete_message(chat_id=callback.from_user.id, message_id=callback.message.message_id)
    else:
        await send_detail_message(callback, state)
        await BotState.description.set()
        await bot.delete_message(chat_id=callback.from_user.id, message_id=callback.message.message_id)


@dp.callback_query_handler(state=BotState.description)
async def handle_desciption(callback: types.CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    product = state_data['last_product']
    chunk = state_data['chunk']

    if callback.data == 'back_to_menu':
        keyboard = await create_menu_buttons(chunk=chunk)
        await bot.send_message(
            chat_id=callback.from_user.id,
            text=emojize('_Пожалуйста, выберите пиццу или много пицц :pizza:_'),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )
        await bot.delete_message(chat_id=callback.from_user.id, message_id=callback.message.message_id)
        await BotState.menu.set()
    elif callback.data == 'basket':
        await send_basket_message(callback, state)
        await BotState.basket.set()
        await bot.delete_message(chat_id=callback.from_user.id, message_id=callback.message.message_id)
    elif 'cart' in callback.data:
        quantity = int(callback.data.split()[1])
        moltin.put_in_cart(callback.from_user.id, product, quantity)
        await callback.answer(emojize('Добавили :pizza: в 🛒 !'))
        await BotState.description.set()


@dp.callback_query_handler(state=BotState.basket)
async def handle_basket(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == 'back_to_menu':
        await edit_menu(callback, state, chunk=0)
        await BotState.menu.set()
    elif callback.data == 'sell':
        keyboard = ReplyKeyboardMarkup()
        keyboard.add(KeyboardButton('Отправить локацию', request_location=True))
        await bot.send_message(
            text=emojize('Где вы находитесь :house: ?\n\nВведите адрес или отправьте геоллокацию с телефона.'),
            chat_id=callback.from_user.id,
            reply_markup=keyboard,
        )
        await bot.delete_message(chat_id=callback.from_user.id, message_id=callback.message.message_id)
        await BotState.geo.set()
    else:
        moltin.delete_item_in_cart(callback.from_user.id, callback.data)
        await callback.answer('Удалили :pizza: из 🛒!')
        await send_basket_message(callback, state)
        await bot.delete_message(chat_id=callback.from_user.id, message_id=callback.message.message_id)
        await BotState.basket.set()


@dp.message_handler(state=BotState.geo)
@dp.message_handler(state=BotState.geo, content_types=ContentType.LOCATION)
async def handle_geo(message: types.Message, state: FSMContext):

    if message.location:
        user_location = message.location
        location = (user_location['longitude'], user_location['latitude'])
    else:
        try:
            location = utils.fetch_coordinates(message.text)
        except IndexError:
            location = None

        if location is None:
            await message.answer(emojize('Не смогли определить адрес :house:, попробуйте еще.'))
            await BotState.geo.set()

    all_pizzerias = await get_from_redis('pizzerias')
    closest_pizzeria = utils.get_closest_pizzeria(
        location, all_pizzerias=json.loads(all_pizzerias))
    reply_message, distance = utils.calculate_distance_for_message(
        closest_pizzeria)
    await message.answer('Данные приняты, спасибо.', reply_markup=ReplyKeyboardRemove())
    await state.update_data(
        closest_pizzeria=closest_pizzeria,
        customer_geo=location,
    )

    keyboard = create_delivery_buttons(distance)
    await message.answer(
        text=reply_message,
        reply_markup=keyboard,
    )
    await BotState.handle_geo.set()


@dp.callback_query_handler(state=BotState.handle_geo)
async def handle_delivery(callback: types.CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    pizzeria = state_data['closest_pizzeria']
    pizza_address = pizzeria['address']
    pizza_name = pizzeria['alias']
    pizza_image = utils.get_yandex_map(
        (pizzeria['longitude'], pizzeria['latitude']))
    customer_geo = state_data['customer_geo']
    customer_image = utils.get_yandex_map(customer_geo)
    keyboard = create_payment_buttons()

    if callback.data == 'pickup':
        message = f"""
            Отлично!

            Вы можете забрать ваш заказ в ресторане {pizza_name} по адресу: {pizza_address}.
        """
        await bot.send_photo(
            caption=dedent(message),
            chat_id=callback.from_user.id,
            photo=pizza_image,
        )
        await bot.delete_message(chat_id=callback.from_user.id, message_id=callback.message.message_id)
        await bot.send_message(
            chat_id=callback.from_user.id,
            text='Как хотите оплатить?',
            reply_markup=keyboard,
        )
        await BotState.pay.set()
    elif callback.data == 'delivery':
        await bot.send_photo(
            chat_id=callback.from_user.id,
            caption='Отлично!\n\nВезем ваш заказ к вам.',
            photo=customer_image,
        )
        await bot.delete_message(chat_id=callback.from_user.id, message_id=callback.message.message_id)
        await bot.send_message(
            chat_id=callback.from_user.id,
            text='Как хотите оплатить?',
            reply_markup=keyboard,
        )
        await BotState.pay.set()


@dp.callback_query_handler(state=BotState.pay)
async def handle_pay(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == 'cash':
        await bot.edit_message_text(
            text='Спасибо за заказ, ждем вас.',
            chat_id=callback.from_user.id,
            message_id=callback.message.message_id,
        )
    elif callback.data == 'telegram':
        total = moltin.get_total(callback.from_user.id)
        amount = total.split()[0].split('.')[0].replace(',', '')
        payload = os.getenv('PAYMENT_PAYLOAD')
        provider_token = os.getenv('TG_TRANZZO_TOKEN')
        start_parameter = 'payment'
        currency = "RUB"
        prices = [LabeledPrice(label="Оплатить заказ", amount=int(amount) * 100)]

        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title="Оплата заказа",
            description="Пожалуйста, нажмите, чтобы оплатить заказ.",
            payload=payload,
            provider_token=provider_token,
            start_parameter=start_parameter,
            currency=currency,
            prices=prices,
        )
        await bot.delete_message(chat_id=callback.from_user.id, message_id=callback.message.message_id)


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
