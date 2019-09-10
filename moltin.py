import json
import logging
import os
from functools import wraps
from io import BytesIO

import requests

from dotenv import load_dotenv
from transliterate import translit

MOLTIN_URL = 'https://api.moltin.com/v2/'


def open_json(file):
    with open(file) as json_file:
        data = json.load(json_file)
    return data


def headers_wrapper(func):

    @wraps(func)
    def inner(*args, **kwargs):
        url = 'https://api.moltin.com/oauth/access_token'
        data = {
            'client_id': os.getenv('MOLTIN_CLIENT_ID'),
            'client_secret': os.getenv('MOLTIN_CLIENT_SECRET'),
            'grant_type': 'client_credentials',
        }
        response = requests.get(url, data=data)
        response.raise_for_status()
        token = response.json().get('access_token')
        headers = {
            'Authorization': f'Bearer {token}',
        }
        return func(headers, *args, **kwargs)
    return inner


@headers_wrapper
def create_product(headers, name, description, price):
    url = f'{MOLTIN_URL}products'
    slug = '-'.join(translit(name, reversed=True).lower().split())
    data = {
        'data': {
            'type': 'product',
            'name': name,
            'slug': slug,
            'sku': f'{slug}-001',
            'description': description,
            'manage_stock': False,
            'price': [
                {
                    'amount': int(f'{price}00'),
                    'currency': 'RUB',
                    'includes_tax': True,
                }
            ],
            'status': 'live',
            'commodity_type': 'physical',
        }}
    response = requests.post(url=url, headers=headers, json=data)
    response.raise_for_status()
    return response.json()['data']['id']


@headers_wrapper
def load_image(headers, image_url):
    url = f'{MOLTIN_URL}files'
    image_name = image_url.split('/')[-1]
    image_content = BytesIO(requests.get(image_url).content)
    files = {
        'file': (image_name, image_content)
    }
    response = requests.post(url=url, headers=headers, files=files)
    image_content.close()
    response.raise_for_status()
    return response.json()['data']['id']


@headers_wrapper
def attach_image(headers, product_id, image_id):
    url = f'{MOLTIN_URL}products/{product_id}/relationships/main-image'
    data = {
        'data': {
            'type': 'main_image',
            'id': image_id,
        }
    }
    response = requests.post(url=url, headers=headers, json=data)
    response.raise_for_status()


def create_full_product(name, description, price, image):
    product_id = create_product(name, description, price)
    image_id = load_image(image)
    attach_image(product_id, image_id)


def create_menu(file):
    try:
        pizzas = open_json(file)
    except FileNotFoundError as error:
        pizzas = None
        logging.error(error)

    if pizzas is None:
        exit

    for pizza in pizzas:
        try:
            name = pizza['name']
            description = pizza['description']
            price = pizza['price']
            image = pizza['product_image']['url']
            create_full_product(
                name=name,
                description=description,
                price=price,
                image=image
            )
        except requests.HTTPError as error:
            logging.error(error)


@headers_wrapper
def create_flow(headers, name, slug, description):
    url = f'{MOLTIN_URL}flows'
    data = {
        'data': {
            'type': 'flow',
            'enabled': True,
            'description': description,
            'slug': slug,
            'name': name,
        }
    }
    response = requests.post(url=url, headers=headers, json=data)
    response.raise_for_status()
    return response.json()['data']['id'], response.json()['data']['slug']


@headers_wrapper
def create_flow_fields(headers, flow_id, fields_dict):
    url = f'{MOLTIN_URL}fields'
    for name, slug in fields_dict.items():
        data = {
            'data': {
                'type': 'field',
                'name': name,
                'slug': slug,
                'field_type': 'string',
                'description': f'Field for {name}',
                'required': False,
                'enabled': True,
                'unique': True,
                'relationships': {
                    'flow': {
                        'data': {
                            'type': 'flow',
                            'id': flow_id
                        }
                    }
                }
            }
        }
        try:
            response = requests.post(url=url, headers=headers, json=data)
            response.raise_for_status()
        except requests.HTTPError as error:
            logging.error(error)


@headers_wrapper
def create_pizzeria_entry(headers, address, alias, longitude, latitude, flow_slug='pizzerias'):
    url = f'{MOLTIN_URL}flows/{flow_slug}/entries'

    data = {
        'data': {
            'type': 'entry',
            'pizza-address': address,
            'pizza-alias': alias,
            'longitude': longitude,
            'latitude': latitude,
        }
    }

    response = requests.post(url=url, headers=headers, json=data)
    response.raise_for_status()


@headers_wrapper
def create_customer_entry(headers, order_id, customer_name, longitude, latitude, flow_slug='addresses'):
    url = f'{MOLTIN_URL}flows/{flow_slug}/entries'
    data = {
        'data': {
            'type': 'entry',
            'order': order_id,
            'customer-name': customer_name,
            'longitude': longitude,
            'latitude': latitude,
        }
    }
    response = requests.post(url=url, headers=headers, json=data)
    response.raise_for_status()
    return response.json()['data']['id']


def create_pizzaries_from_json(file):
    try:
        pizzerias = open_json(file)
    except FileNotFoundError as error:
        pizzerias = None
        logging.error(error)

    if pizzerias is None:
        exit

    for pizzeria in pizzerias:
        try:
            create_pizzeria_entry(
                flow_slug='pizzerias',
                addresses=pizzeria.get('address').get('full'),
                alias=pizzeria.get('alias'),
                longitude=pizzeria.get('coordinates').get('lon'),
                latitude=pizzeria.get('coordinates').get('lat')
            )
        except requests.HTTPError as error:
            logging.error(error)


@headers_wrapper
def get_products(headers):
    url = f'{MOLTIN_URL}products'
    response = requests.get(url=url, headers=headers)
    response.raise_for_status()
    products = response.json()['data']
    return [(product['id'], product['name']) for product in products]


@headers_wrapper
def get_by_id(headers, product_id):
    url = f'{MOLTIN_URL}products/{product_id}'

    response = requests.get(url=url, headers=headers)
    response.raise_for_status()
    return response.json()['data']


@headers_wrapper
def get_picture(headers, product_id):
    url = f'{MOLTIN_URL}files/{product_id}'

    response = requests.get(url=url, headers=headers)
    response.raise_for_status()
    return response.json()['data']['link']['href']


@headers_wrapper
def put_in_cart(headers, reference, product_id, quantity):
    url = f'{MOLTIN_URL}carts/{reference}/items'
    data = {
        'data': {
            'id': product_id,
            'type': 'cart_item',
            'quantity': quantity,
        }
    }
    response = requests.post(url=url, headers=headers, json=data)
    response.raise_for_status()


@headers_wrapper
def get_cart(headers, reference):
    url = f'{MOLTIN_URL}carts/{reference}/items'
    response = requests.get(url=url, headers=headers)
    response.raise_for_status()

    user_cart = []
    for product in response.json()['data']:
        user_cart.append({
            'cart_id': product['id'],
            'product_id': product['product_id'],
            'name': product['name'],
            'quantity': product['quantity'],
            'price': product['meta']['display_price']['with_tax']['unit']['formatted'],
            'total': product['meta']['display_price']['with_tax']['value']['formatted']
        })
    return user_cart


@headers_wrapper
def get_total(headers, reference):
    url = f'{MOLTIN_URL}carts/{reference}'

    response = requests.get(url=url, headers=headers)
    response.raise_for_status()
    return response.json()['data']['meta']['display_price']['with_tax']['formatted']


def format_basket_for_sending(user_id):
    user_basket = get_cart(user_id)
    user_total = get_total(user_id)
    message = []
    for product in user_basket:
        name = product['name']
        quantity = product['quantity']
        total = product['total']
        text = f'_{name}_\n_{quantity}шт в корзине на сумму {total}_\n'
        message.append(text)
    message.append(f' *Всего:* {user_total}')
    return '\n'.join(message)


@headers_wrapper
def delete_item_in_cart(headers, reference, product_id):
    url = f'{MOLTIN_URL}carts/{reference}/items/{product_id}'
    response = requests.delete(url, headers=headers)
    response.raise_for_status()


@headers_wrapper
def create_customer(headers, user_id, user_email, user_name, user_surname=None):
    url = f'{MOLTIN_URL}customers'
    data = {
        'data': {
            'type': 'customer',
            'name': f'{user_name} {user_surname}',
            'email': user_email
        }
    }

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()


def check_product_in_cart(reference, product_id):
    carts = get_cart(reference)
    for item in carts:
        if item['product_id'] == product_id:
            quantity, total = item['quantity'], item['total']
            return f'*Уже в корзине:* {quantity} шт., всего на сумму {total}'


@headers_wrapper
def get_all_entries(headers, flow_slug):
    url = f'{MOLTIN_URL}flows/{flow_slug}/entries'
    response = requests.get(url=url, headers=headers)
    response.raise_for_status()
    return response.json()['data']


@headers_wrapper
def get_deliverer(headers, entry_id, flow_slug='pizzerias'):
    url = f'{MOLTIN_URL}flows/{flow_slug}/entries/{entry_id}'
    response = requests.get(url=url, headers=headers)
    response.raise_for_status()
    return response.json()['data']['deliverer']


@headers_wrapper
def get_customer_coordinates(headers, entry_id, flow_slug='addresses'):
    url = f'{MOLTIN_URL}flows/{flow_slug}/entries/{entry_id}'
    response = requests.get(url=url, headers=headers)
    response.raise_for_status()
    return float(response.json()['data']['longitude']), float(response.json()['data']['latitude'])


if __name__ == "__main__":
    load_dotenv()
