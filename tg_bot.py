import json
import logging
import os
from operator import itemgetter

import redis
from dotenv import load_dotenv
from geopy import Point, distance
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    LabeledPrice,
    ParseMode,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    Filters,
    MessageHandler,
    PreCheckoutQueryHandler,
    Updater,
)
from yandex_geocoder import Client
from yandex_geocoder.exceptions import YandexGeocoderAddressNotFound

import moltin
import utils


def get_database():
    db_url = os.getenv('REDIS_URL')
    db_port = os.getenv('REDIS_PORT')
    db_password = os.getenv('REDIS_PASSWORD')
    database = redis.Redis(
        host=db_url,
        port=db_port,
        password=db_password,
        charset='utf-8',
        decode_responses=True,
    )
    return database


def create_chunks(products, size=7):
    for i in range(0, len(products), size):
        yield products[i: i + size]


def send_order_to_deliverer(context, order_id, deliverer, longitude, latitude):
    order_text = 'Офомлен заказ на:\n\n'
    order_text += moltin.format_basket_for_sending(order_id)
    order_text += '\n\nКоординаты клиента:'
    context.bot.send_message(
        chat_id=deliverer, text=order_text, parse_mode=ParseMode.MARKDOWN
    )
    context.bot.send_location(chat_id=deliverer, longitude=longitude, latitude=latitude)


def create_menu_buttons(chunk):
    products = moltin.get_products()
    chunks = list(create_chunks(products))
    last_chunk = len(chunks) - 1

    keyboard = [
        [InlineKeyboardButton(pr_name, callback_data=pr_id)]
        for pr_id, pr_name in chunks[chunk]
    ]
    if chunk == 0:
        keyboard.append([InlineKeyboardButton("Следующие", callback_data='next')])
    elif chunk == last_chunk:
        keyboard.append([InlineKeyboardButton("Предыдущие", callback_data='prev')])
    else:
        keyboard.append(
            [
                InlineKeyboardButton("Предыдущие", callback_data='prev'),
                InlineKeyboardButton("Следующие", callback_data='next'),
            ]
        )

    keyboard.append([InlineKeyboardButton("Корзина", callback_data='basket')])
    return InlineKeyboardMarkup(keyboard)


def create_description_buttons():
    buttons_list = [['1 шт', 'cart 1'], ['3 шт', 'cart 3'], ['5 шт', 'cart 5']]
    keyboard = [
        [
            InlineKeyboardButton(button_name, callback_data=button_id)
            for button_name, button_id in buttons_list
        ]
    ]
    keyboard.append([InlineKeyboardButton('Назад', callback_data='back_to_menu')])
    keyboard.append([InlineKeyboardButton("Корзина", callback_data='basket')])

    return InlineKeyboardMarkup(keyboard)


def create_basket_buttons(user_id=None):
    user_basket = moltin.get_cart(user_id)
    keyboard = []
    for product in user_basket:
        pr_name = product['name']
        pr_id = product['cart_id']
        keyboard.append(
            [InlineKeyboardButton(f'Удалить {pr_name}', callback_data=pr_id)]
        )
    keyboard.append(
        [InlineKeyboardButton("Назад в меню", callback_data='back_to_menu')]
    )
    keyboard.append([InlineKeyboardButton("Оформить заказ", callback_data='sell')])
    return InlineKeyboardMarkup(keyboard)


def create_delivery_buttons(distance):
    if distance <= 20:
        keyboard = [
            [
                InlineKeyboardButton('Доставка', callback_data='delivery'),
                InlineKeyboardButton('Самовывоз', callback_data='pickup'),
            ]
        ]
    else:
        keyboard = [[InlineKeyboardButton('Самовывоз', callback_data='pickup')]]
    return InlineKeyboardMarkup(keyboard)


def start(update, context):
    chat_id = update.message.chat_id
    keyboard = create_menu_buttons(chunk=0)

    user_data = json.loads(db.get(chat_id))
    user_data['last_chunk'] = 0
    db.set(chat_id, json.dumps(user_data))

    context.bot.send_message(
        chat_id=chat_id,
        text='_Пожалуйста, выберите пиццу или много пицц :):_',
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN,
    )
    return 'HANDLE_MENU'


def handle_button(update, context):
    query = update.callback_query
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    user_data = json.loads(db.get(chat_id))
    chunk = user_data['last_chunk']

    if query.data == 'basket':
        keyboard = create_basket_buttons(user_id=chat_id)
        message = moltin.format_basket_for_sending(chat_id)
        context.bot.send_message(
            chat_id=chat_id,
            text=message,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )
        context.bot.deleteMessage(chat_id=chat_id, message_id=message_id)
        return 'HANDLE_BASKET'
    elif query.data == 'prev':
        keyboard = create_menu_buttons(chunk=chunk - 1)
        context.bot.send_message(
            chat_id=chat_id,
            text='_Пожалуйста, выберите пиццу или много пицц :):_',
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )
        context.bot.deleteMessage(chat_id=chat_id, message_id=message_id)
        user_data['last_chunk'] -= 1
        db.set(chat_id, json.dumps(user_data))
        return 'HANDLE_MENU'
    elif query.data == 'next':
        keyboard = create_menu_buttons(chunk=chunk + 1)
        context.bot.send_message(
            chat_id=chat_id,
            text='_Пожалуйста, выберите пиццу или много пицц :):_',
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )
        context.bot.deleteMessage(chat_id=chat_id, message_id=message_id)
        user_data['last_chunk'] += 1
        db.set(chat_id, json.dumps(user_data))
        return 'HANDLE_MENU'
    else:
        pizza_data = json.loads(db.get(query.data)) or moltin.get_by_id(query.data)
        pizza_name = pizza_data['name']
        pizza_text = pizza_data['description']
        pizza_price = pizza_data['meta']['display_price']['with_tax']['formatted']
        image_id = pizza_data['relationships']['main_image']['data']['id']
        image_url = db.get(image_id) or moltin.get_picture(image_id)
        basket_message = moltin.check_product_in_cart(chat_id, query.data) or ''

        keyboard = create_description_buttons()

        user_data = json.loads(db.get(chat_id))
        user_data['last_product'] = query.data
        db.set(chat_id, json.dumps(user_data))

        message = f'*{pizza_name}*\n\n{pizza_text}\n\n_Цена {pizza_price}_\n\n{basket_message}'
        context.bot.send_photo(
            chat_id=chat_id,
            photo=image_url,
            caption=message,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )
        context.bot.deleteMessage(chat_id=chat_id, message_id=message_id)

    return 'HANDLE_DESCRIPTION'


def handle_description(update, context):
    query = update.callback_query
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    user_data = json.loads(db.get(chat_id))
    product_id = user_data['last_product']

    if query.data == 'back_to_menu':
        user_data = json.loads(db.get(chat_id))
        chunk = user_data['last_chunk']
        keyboard = create_menu_buttons(chunk=chunk)
        context.bot.send_message(
            chat_id=chat_id,
            text='_Пожалуйста, выберите пиццу или много пицц :):_',
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )
        context.bot.deleteMessage(chat_id=chat_id, message_id=message_id)
        return 'HANDLE_MENU'
    elif query.data == 'basket':
        keyboard = create_basket_buttons(user_id=chat_id)
        message = moltin.format_basket_for_sending(chat_id)
        context.bot.send_message(
            chat_id=chat_id,
            text=message,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )
        context.bot.deleteMessage(chat_id=chat_id, message_id=message_id)
        return 'HANDLE_BASKET'
    elif query.data.split()[0] == 'cart':
        quantity = int(query.data.split()[1])
        moltin.put_in_cart(chat_id, product_id, quantity)
        context.bot.answer_callback_query(
            callback_query_id=query.id, text='Добавили в корзину!'
        )
        return 'HANDLE_DESCRIPTION'


def handle_basket(update, context):
    query = update.callback_query
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    if query.data == 'back_to_menu':
        keyboard = create_menu_buttons(chunk=0)
        context.bot.send_message(
            chat_id=chat_id,
            text='_Пожалуйста, выберите пиццу или много пицц :):_',
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )
        context.bot.deleteMessage(chat_id=chat_id, message_id=message_id)
        return 'HANDLE_MENU'
    elif query.data == 'sell':
        location_keyboard = KeyboardButton(
            text='Отправить свою геолокацию', request_location=True
        )
        custom_keyboard = [[location_keyboard]]
        reply_markup = ReplyKeyboardMarkup(custom_keyboard)
        context.bot.send_message(
            chat_id=chat_id,
            text='Отправить геолокацию можно только с телефона',
            reply_markup=reply_markup,
        )
        context.bot.deleteMessage(chat_id=chat_id, message_id=message_id)
        return 'WAITING_GEO'
    else:
        moltin.delete_item_in_cart(chat_id, query.data)
        message = moltin.format_basket_for_sending(chat_id)
        keyboard = create_basket_buttons(user_id=chat_id)
        context.bot.answer_callback_query(
            callback_query_id=query.id, text='Удалили из корзины!'
        )
        context.bot.send_message(
            chat_id=chat_id,
            text=message,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )
        context.bot.deleteMessage(chat_id=chat_id, message_id=message_id)
        return 'HANDLE_BASKET'


def handle_waiting(update, context):
    message = update.message
    chat_id = message.chat_id
    if message.text:
        try:
            current_pos = Client.coordinates(message.text)
        except YandexGeocoderAddressNotFound as error:
            logging.error(error)
            update.message.reply_text(
                text='Не смогли определить адрес, попробуйте еще.'
            )
            current_pos = None
    else:
        current_pos = (message.location.longitude, message.location.latitude)

    if current_pos is None:
        return 'WAITING_GEO'

    closest_pizzeria = utils.get_closest_pizzeria(db, current_pos)
    message, distance = utils.calculate_distance_for_message(closest_pizzeria)
    update.message.reply_text(
        text='Данные приняты, спасибо.', reply_markup=ReplyKeyboardRemove()
    )
    keyboard = create_delivery_buttons(distance)
    context.bot.send_message(chat_id=chat_id, text=message, reply_markup=keyboard)
    user_data = json.loads(db.get(chat_id))
    user_data['closest_pizzeria'] = closest_pizzeria
    user_data['customer_geo'] = current_pos
    db.set(chat_id, json.dumps(user_data))
    return 'WAITING_CHOOSING'


def handle_delivery_choosing(update, context):
    query = update.callback_query
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    user_name = query.message.chat.first_name

    user_data = json.loads(db.get(chat_id))
    closest_pizzeria = user_data['closest_pizzeria']
    customer_geo = user_data['customer_geo']
    pizzeria_name = closest_pizzeria['alias']
    pizzeria_address = closest_pizzeria['address']
    pizzeria_id = closest_pizzeria['id']
    customer_longitude, customer_latitude = customer_geo

    if query.data == 'pickup':
        context.bot.send_message(
            chat_id=chat_id,
            text=f'Отлично! Вы можете забрать ваш заказ в ресторане {pizzeria_name} по адресу: {pizzeria_address}\n\nУдачного дня и заходите еще!',
        )
        context.bot.deleteMessage(chat_id=chat_id, message_id=message_id)
        moltin.create_customer_entry(
            chat_id, pizzeria_name, customer_longitude, customer_latitude
        )

    elif query.data == 'delivery':
        context.bot.send_message(
            chat_id=chat_id, text=f'Ваш заказ принят, ожидаем оплату.'
        )
        context.bot.deleteMessage(chat_id=chat_id, message_id=message_id)
        user = moltin.create_customer_entry(
            chat_id, user_name, customer_longitude, customer_latitude
        )
        deliverer = moltin.get_deliverer(pizzeria_id)
        send_order_to_deliverer(
            context, chat_id, deliverer, customer_longitude, customer_latitude
        )

        create_invoice(context, chat_id=chat_id)
        job_queue.run_once(remind_about_order, 3600, context=chat_id)


def remind_about_order(context):
    message = 'Приятного аппетита!\n\n'
    message += (
        'Но если заказ не пришел в течении этого часа, следующий заказ за наш счет:('
    )
    context.bot.send_message(chat_id=context.job.context, text=message)


def create_invoice(context, chat_id):
    user_total = moltin.get_total(chat_id)
    amount = int(user_total.split()[0].split('.')[0])
    title = "Оплата заказа"
    description = "Пожалуйста, нажмите, чтобы оплатить заказ."
    payload = os.getenv('PAYMENT_PAYLOAD')
    provider_token = os.getenv('TG_TRANZZO_TOKEN')
    start_parameter = 'payment'
    currency = "RUB"
    prices = [LabeledPrice("Оплатить заказ", amount * 100)]
    context.bot.sendInvoice(
        chat_id,
        title,
        description,
        payload,
        provider_token,
        start_parameter,
        currency,
        prices,
    )


def handle_invoice(update, context):
    payload = os.getenv('PAYMENT_PAYLOAD')
    query = update.pre_checkout_query
    if query.invoice_payload != payload:
        context.bot.answer_pre_checkout_query(
            pre_checkout_query_id=query.id,
            ok=False,
            error_message='Что-то пошло не так...',
        )
    else:
        context.bot.answer_pre_checkout_query(pre_checkout_query_id=query.id, ok=True)


def handle_successful_payment(update, context):
    update.message.reply_text("Спасибо, мы получили ваш платеж!")


def handle_users_reply(update, context):
    if update.message:
        user_reply = update.message.text
        chat_id = update.message.chat_id
    elif update.callback_query:
        user_reply = update.callback_query.data
        chat_id = update.callback_query.message.chat_id
    else:
        return

    if user_reply == '/start':
        user_state = 'START'
    else:
        user = db.get(chat_id)
        user_state = json.loads(user)['state']

    states_functions = {
        'START': start,
        'HANDLE_MENU': handle_button,
        'HANDLE_DESCRIPTION': handle_description,
        'HANDLE_BASKET': handle_basket,
        'WAITING_GEO': handle_waiting,
        'WAITING_CHOOSING': handle_delivery_choosing,
    }

    state_handler = states_functions[user_state]
    try:
        next_state = state_handler(update, context)
    except Exception as error:
        logging.error(error)
        next_state = None

    if next_state is not None:
        user = db.get(chat_id)
        if user:
            user_data = json.loads(user)
            user_data['state'] = next_state
        else:
            user_data = {'state': next_state}
        db.set(chat_id, json.dumps(user_data))


if __name__ == "__main__":
    load_dotenv()
    tg_token = os.getenv('TG_TOKEN')

    global db
    db = get_database()

    updater = Updater(tg_token, use_context=True)
    dispatcher = updater.dispatcher
    job_queue = updater.job_queue

    dispatcher.add_handler(CommandHandler('start', handle_users_reply))
    dispatcher.add_handler(CallbackQueryHandler(handle_users_reply))
    dispatcher.add_handler(
        MessageHandler(Filters.text | Filters.location, handle_users_reply)
    )

    dispatcher.add_handler(PreCheckoutQueryHandler(handle_invoice))
    dispatcher.add_handler(
        MessageHandler(Filters.successful_payment, handle_successful_payment)
    )

    updater.start_polling()
    updater.idle()
