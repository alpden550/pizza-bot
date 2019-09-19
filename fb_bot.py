import json
import logging
import os
from functools import wraps

import redis
import requests
from dotenv import load_dotenv
from flask import Flask, request
from yandex_geocoder import Client
from yandex_geocoder.exceptions import YandexGeocoderAddressNotFound

import moltin
import utils

app = Flask(__name__)
FB_TOKEN = os.getenv('FB_PAGE_TOKEN')
FB_API = 'https://graph.facebook.com/v2.6/me/messages'
LOGO_URL = 'https://image.freepik.com/free-vector/pizza-logo-design-vector_22159-4.jpg'
CATEGORY_LOGO_URL = 'https://primepizza.ru/uploads/position/large_0c07c6fd5c4dcadddaf4a2f1a2c218760b20c396.jpg'
BASKET_IMG_URL = 'https://internet-marketings.ru/wp-content/uploads/2018/08/idealnaya-korzina-internet-magazina-1068x713.jpg'


def headers_wrapper(func):
    @wraps(func)
    def inner(*args, **kwargs):
        params = {'access_token': FB_TOKEN}
        headers = {'Content-Type': 'application/json'}
        return func(headers, params, *args, **kwargs)

    return inner


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


@app.route('/', methods=['GET'])
def verify():
    '''
    При верификации вебхука у Facebook он отправит запрос на этот адрес. На него нужно ответить VERIFY_TOKEN.
    '''
    if request.args.get('hub.mode') == 'subscribe' and request.args.get(
        'hub.challenge'
    ):
        if not request.args.get('hub.verify_token') == os.getenv('FB_VERIFY_TOKEN'):
            return 'Verification token mismatch', 403
        return request.args['hub.challenge'], 200

    return 'Hello!', 200


def create_category_menu(categories):
    buttons = []
    for category in categories:
        category_data = json.loads(db.get(category)) or moltin.get_category_by_slug(
            category
        )
        name, slug = category_data['name'], category_data['slug']
        buttons.append({'type': 'postback', 'title': name, 'payload': slug})
    categories = {
        'title': 'Не нашли нужную пиццу?',
        'subtitle': 'Остальные пиццы можно посмотреть в наших категориях:',
        'image_url': CATEGORY_LOGO_URL,
        'buttons': buttons,
    }
    return categories


def create_all_menu(category_slug='main'):
    categories = json.loads(db.get('categories')) or moltin.get_all_categories()
    categories.remove(category_slug)

    menu_elements = [
        {
            'title': 'Меню',
            'subtitle': 'Вы можете выбрать одну, или много пицц',
            'image_url': LOGO_URL,
            'buttons': [{'type': 'postback', 'title': 'Корзина', 'payload': 'basket'}],
        }
    ]

    category = json.loads(db.get(category_slug)) or moltin.get_category_by_slug(
        category_slug
    )
    category_products = category['products']
    for product in category_products:
        pizza_data = json.loads(db.get(product)) or moltin.get_by_id(product)
        pizza_name = pizza_data['name']
        pizza_desc = pizza_data['description']
        pizza_price = pizza_data['meta']['display_price']['with_tax']['formatted']
        image_id = pizza_data['relationships']['main_image']['data']['id']
        image_url = db.get(image_id) or moltin.get_picture(image_id)
        data = {
            'title': f'{pizza_name}, {pizza_price}',
            'subtitle': pizza_desc,
            'image_url': image_url,
            'buttons': [
                {'type': 'postback', 'title': 'Добавить в корзину!', 'payload': product}
            ],
        }
        menu_elements.append(data)
    rest_categories = create_category_menu(categories)
    menu_elements.append(rest_categories)
    return menu_elements


@headers_wrapper
def send_message(headers, params, recipient_id, message):
    request_content = {"recipient": {"id": recipient_id}, "message": {"text": message}}
    response = requests.post(
        url=FB_API, params=params, headers=headers, json=request_content
    )
    response.raise_for_status()


@headers_wrapper
def send_main_menu(headers, params, recipient_id, message):
    menu_elements = create_all_menu(category_slug='main')

    request_content = {
        'recipient': {'id': recipient_id},
        'message': {
            'attachment': {
                'type': 'template',
                'payload': {
                    'template_type': 'generic',
                    'image_aspect_ratio': 'square',
                    'elements': menu_elements,
                },
            }
        },
    }
    response = requests.post(
        url=FB_API, params=params, headers=headers, json=request_content
    )
    response.raise_for_status()
    return 'HANDLE_MENU'


@headers_wrapper
def create_basket_menu(headers, params, recipient_id):
    total = moltin.get_total(recipient_id)
    user_cart = moltin.get_cart(recipient_id)

    menu_elements = [
        {
            'title': f'Ваш заказ на сумму: {total}',
            'image_url': BASKET_IMG_URL,
            'buttons': [
                {'type': 'postback', 'title': 'Оформить заказ', 'payload': 'order'},
                {
                    'type': 'postback',
                    'title': 'Назад в меню',
                    'payload': 'back_to_menu',
                },
            ],
        }
    ]
    for product in user_cart:
        product_id = product['product_id']
        pizza_data = json.loads(db.get(product_id)) or moltin.get_by_id(product)
        pizza_name = pizza_data['name']
        pizza_desc = pizza_data['description']
        pizza_price = pizza_data['meta']['display_price']['with_tax']['formatted']
        image_id = pizza_data['relationships']['main_image']['data']['id']
        image_url = db.get(image_id) or moltin.get_picture(image_id)
        data = {
            'title': f'{pizza_name}, {pizza_price}',
            'subtitle': pizza_desc,
            'image_url': image_url,
            'buttons': [
                {
                    'type': 'postback',
                    'title': 'Добавить еще одну',
                    'payload': f'add {product_id}',
                },
                {
                    'type': 'postback',
                    'title': 'Удалить',
                    'payload': f'remove {product_id}',
                },
            ],
        }
        menu_elements.append(data)
    request_content = {
        'recipient': {'id': recipient_id},
        'message': {
            'attachment': {
                'type': 'template',
                'payload': {
                    'template_type': 'generic',
                    'image_aspect_ratio': 'square',
                    'elements': menu_elements,
                },
            }
        },
    }
    response = requests.post(
        url=FB_API, params=params, headers=headers, json=request_content
    )
    response.raise_for_status()


@headers_wrapper
def create_delivery_buttons(headers, params, recipient_id, distance):
    if distance <= 20:
        menu_elements = [
            {
                'title': 'Как получите заказ?',
                'buttons': [
                    {'type': 'postback', 'title': 'Доставка', 'payload': 'delivery'},
                    {'type': 'postback', 'title': 'Самовывоз', 'payload': 'pickup'},
                ],
            }
        ]
    else:
        menu_elements = [
            {
                'title': 'Как получите заказ?',
                'buttons': [
                    {'type': 'postback', 'title': 'Самовывоз', 'payload': 'pickup'}
                ],
            }
        ]

    request_content = {
        'recipient': {'id': recipient_id},
        'message': {
            'attachment': {
                'type': 'template',
                'payload': {
                    'template_type': 'generic',
                    'image_aspect_ratio': 'square',
                    'elements': menu_elements,
                },
            }
        },
    }
    response = requests.post(
        url=FB_API, params=params, headers=headers, json=request_content
    )
    response.raise_for_status()


@headers_wrapper
def handle_button(headers, params, recipient_id, message):
    categories = json.loads(db.get('categories')) or moltin.get_all_categories()
    products = json.loads(db.get('products'))

    if message in categories:
        menu_elements = create_all_menu(category_slug=message)

        request_content = {
            'recipient': {'id': recipient_id},
            'message': {
                'attachment': {
                    'type': 'template',
                    'payload': {
                        'template_type': 'generic',
                        'image_aspect_ratio': 'square',
                        'elements': menu_elements,
                    },
                }
            },
        }
        response = requests.post(
            url=FB_API, params=params, headers=headers, json=request_content
        )
        response.raise_for_status()
        return 'HANDLE_MENU'
    elif message == 'basket':
        create_basket_menu(recipient_id)
        return 'HANDLE_BASKET'
    elif message == 'sale':
        pass
    elif message in products:
        moltin.put_in_cart(recipient_id, message, 1)
        send_message(recipient_id, message='Добавили в корзину!')
        return 'HANDLE_MENU'


@headers_wrapper
def handle_basket(headers, params, recipient_id, message):
    if message == 'back_to_menu':
        menu_elements = create_all_menu()
        request_content = {
            'recipient': {'id': recipient_id},
            'message': {
                'attachment': {
                    'type': 'template',
                    'payload': {
                        'template_type': 'generic',
                        'image_aspect_ratio': 'square',
                        'elements': menu_elements,
                    },
                }
            },
        }
        response = requests.post(
            url=FB_API, params=params, headers=headers, json=request_content
        )
        response.raise_for_status()
        return 'HANDLE_MENU'
    elif message == 'order':
        send_message(
            recipient_id,
            message='Где вы находитесь? Введите адрес для выбора ближайшей пиццерии.',
        )
        return 'HANDLE_ORDER'
    elif message.split()[0] == 'add':
        product_id = message.split()[1]
        moltin.put_in_cart(recipient_id, product_id, 1)
        send_message(recipient_id, message='Добавили еще 1 пиццу.')
        create_basket_menu(recipient_id)
        return 'HANDLE_BASKET'
    elif message.split()[0] == 'remove':
        user_cart = moltin.get_cart(recipient_id)
        cart_id = [
            product['cart_id']
            for product in user_cart
            if product['product_id'] == message.split()[1]
        ][0]
        moltin.delete_item_in_cart(recipient_id, cart_id)
        send_message(recipient_id, message='Удалили из корзины.')
        create_basket_menu(recipient_id)
        return 'HANDLE_BASKET'


@headers_wrapper
def handle_order(headers, params, recipient_id, message):
    try:
        current_pos = Client.coordinates(message)
    except YandexGeocoderAddressNotFound as error:
        logging.error(error)
        send_message(
            recipient_id, message='Не смогли определить адрес, попробуйте еще.'
        )
        current_pos = None

    if current_pos is None:
        return 'HANDLE_ORDER'

    closest_pizzeria = utils.get_closest_pizzeria(db, current_pos)
    text, distance = utils.calculate_distance_for_message(closest_pizzeria)
    send_message(recipient_id, message='Данные приняты, спасибо')
    send_message(recipient_id, message=text)
    create_delivery_buttons(recipient_id, distance=distance)

    user = json.loads(db.get(f'facebook_{recipient_id}'))
    user['closest_pizzeria'] = closest_pizzeria
    user['user_address'] = message
    db.set(f'facebook_{recipient_id}', json.dumps(user))

    return 'WAITING_CHOOSING'


@headers_wrapper
def handle_delivery_choosing(headers, params, recipient_id, message):
    user = json.loads(db.get(f'facebook_{recipient_id}'))
    closest_pizzeria = user['closest_pizzeria']['address']
    user_address = user['user_address']

    if message == 'pickup':
        send_message(
            recipient_id,
            message=f'Отлично!\nСпасибо за заказ.\n\nВы можете забрать заказ по адресу: {closest_pizzeria}',
        )
    elif message == 'delivery':
        send_message(
            recipient_id,
            message=f'Спасибо за заказ!\n\nЗаказ будет доставлен по адресу: {user_address}',
        )


def handle_users_reply(messaging_event):
    user_id = messaging_event['sender']['id']

    if messaging_event.get('message'):
        user_reply = messaging_event['message']['text']
    elif messaging_event.get('postback'):
        user_reply = messaging_event['postback']['payload']
    else:
        return

    if user_reply.lower().strip(' ') in ['start', 'старт']:
        user_state = 'START'
    else:
        user = db.get(f'facebook_{user_id}')
        try:
            user_state = json.loads(user)['state']
        except TypeError as error:
            logging.exception(error)
            user_state = None

    states_functions = {
        'START': send_main_menu,
        'HANDLE_MENU': handle_button,
        'HANDLE_BASKET': handle_basket,
        'HANDLE_ORDER': handle_order,
        'WAITING_CHOOSING': handle_delivery_choosing,
    }

    state_handler = states_functions[user_state]

    try:
        next_state = state_handler(user_id, user_reply)
    except Exception as error:
        logging.exception(error)
        next_state = None

    if next_state is None:
        return None
    user = db.get(f'facebook_{user_id}')
    if user:
        user_data = json.loads(user)
        user_data['state'] = next_state
    else:
        user_data = {'state': next_state}
    db.set(f'facebook_{user_id}', json.dumps(user_data))


@app.route('/', methods=['POST'])
def webhook():
    """
    Основной вебхук, на который будут приходить сообщения от Facebook.
    """
    try:
        data = request.get_json()
        if data["object"] == "page":
            for entry in data["entry"]:
                for messaging_event in entry["messaging"]:
                    handle_users_reply(messaging_event)
    except Exception as error:
        logging.error(error)
    return "ok", 200


if __name__ == '__main__':
    load_dotenv()

    global db
    db = get_database()

    app.run(host='0.0.0.0', debug=True)
