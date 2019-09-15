import json
import logging
import os

import redis
import requests
from dotenv import load_dotenv
from flask import Flask, request

import moltin

app = Flask(__name__)
FB_TOKEN = os.getenv('FB_PAGE_TOKEN')
FB_API = 'https://graph.facebook.com/v2.6/me/messages'


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
    if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.challenge'):
        if not request.args.get('hub.verify_token') == os.getenv('FB_VERIFY_TOKEN'):
            return 'Verification token mismatch', 403
        print('SUCCESS', request.args)
        return request.args['hub.challenge'], 200

    return 'Hello world, епта!', 200


def send_message(recipient_id, message_text):
    params = {'access_token': FB_TOKEN}
    headers = {'Content-Type': 'application/json'}
    request_content = {
        'recipient': {
            'id': recipient_id
        },
        'message': {
            'text': message_text
        }
    }
    response = requests.post(
        url=FB_API,
        params=params, headers=headers, json=request_content
    )
    response.raise_for_status()


def send_menu(recipient_id):
    pizzas = moltin.get_products()[0:3]

    menu_elements = []
    for pizza in pizzas:
        pizza_id, pizza_slug = pizza
        pizza_data = moltin.get_by_id(pizza_id)
        pizza_name = pizza_data['name']
        pizza_text = pizza_data['description']
        pizza_price = pizza_data['meta']['display_price']['with_tax']['formatted']
        image_id = pizza_data['relationships']['main_image']['data']['id']
        image_url = moltin.get_picture(image_id)
        data = {
            'title': pizza_name,
            'subtitle': pizza_text,
            'image_url': image_url,
            'buttons': [{
                'type': 'postback',
                'title': 'Купить',
                'payload': pizza_slug
            }]
        }
        menu_elements.append(data)

    params = {'access_token': FB_TOKEN}
    headers = {'Content-Type': 'application/json'}
    request_content = {
        'recipient': {
            'id': recipient_id
        },
        'message': {
            'attachment': {
                'type': 'template',
                'payload': {
                    'template_type': 'generic',
                    'elements': menu_elements
                }
            }
        }
    }
    response = requests.post(
        url=FB_API,
        params=params, headers=headers, json=request_content
    )
    response.raise_for_status()
    return 'HANDLE_MENU'


def handle_users_reply(recipient_id, message_text):
    if message_text in ['start', 'старт']:
        user_state = 'START'
    else:
        user = db.get(recipient_id)
        user_state = json.loads(user).get('state')

    states_functions = {
        'START': send_message,
    }

    state_handler = states_functions[user_state]

    try:
        next_state = state_handler(recipient_id, message_text)
    except Exception as error:
        logging.error(error)
        next_state = None

    if next_state is not None:
        user = db.get(recipient_id)
        if user:
            user_data = json.loads(user)
            user_data['state'] = next_state
        else:
            user_data = {'state': next_state}
        db.set(recipient_id, json.dumps(user_data))


@app.route('/', methods=['POST'])
def webhook():
    '''
    Основной вебхук, на который будут приходить сообщения от Facebook.
    '''
    data = request.get_json()
    print(data)
    if data['object'] == 'page':
        for entry in data['entry']:
            for messaging_event in entry['messaging']:
                if messaging_event.get('message'):
                    sender_id = messaging_event['sender']['id']
                    recipient_id = messaging_event['recipient']['id']
                    message_text = messaging_event['message']['text']
                    handle_users_reply(sender_id, message_text)
    return 'ok', 200


if __name__ == '__main__':
    load_dotenv()

    global db
    db = get_database()

    app.run(debug=True)
