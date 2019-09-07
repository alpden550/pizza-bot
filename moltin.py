import json
import os
from io import BytesIO
import requests
import logging
from dotenv import load_dotenv
from transliterate import translit

MOLTIN_URL = 'https://api.moltin.com/v2/'


def open_json(file):
    with open(file) as json_file:
        data = json.load(json_file)
    return data


def get_moltin_token():
    url = 'https://api.moltin.com/oauth/access_token'
    data = {
        'client_id': os.getenv('MOLTIN_CLIENT_ID'),
        'client_secret': os.getenv('MOLTIN_CLIENT_SECRET'),
        'grant_type': 'client_credentials',
    }
    response = requests.get(url, data=data)
    response.raise_for_status()
    return response.json().get('access_token')


def create_product(name, description, price):
    token = get_moltin_token()
    url = f'{MOLTIN_URL}products'
    headers = {
        'Authorization': f'Bearer {token}',
    }
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


def load_image(image_url):
    token = get_moltin_token()
    url = f'{MOLTIN_URL}files'
    headers = {
        'Authorization': f'Bearer {token}',
    }
    image_name = image_url.split('/')[-1]
    image_content = BytesIO(requests.get(image_url).content)
    files = {
        'file': (image_name, image_content)
    }
    response = requests.post(url=url, headers=headers, files=files)
    image_content.close()
    response.raise_for_status()
    return response.json()['data']['id']


def attach_image(product_id, image_id):
    token = get_moltin_token()
    url = f'{MOLTIN_URL}products/{product_id}/relationships/main-image'
    headers = {
        'Authorization': f'Bearer {token}',
    }
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

    if pizzas:
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


def create_flow(name, description):
    token = get_moltin_token()
    url = f'{MOLTIN_URL}flows'
    headers = {
        'Authorization': f'Bearer {token}',
    }
    slug = '-'.join(translit(name, reversed=True).lower().split())
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


def create_flow_fields(flow_id, *args):
    token = get_moltin_token()
    url = f'{MOLTIN_URL}fields'
    headers = {
        'Authorization': f'Bearer {token}',
    }
    for field in args:
        slug = '-'.join(field.lower().split())
        data = {
            'data': {
                'type': 'field',
                'name': field,
                'slug': slug,
                'field_type': 'string',
                'description': f'Field for {field}',
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


def create_pizzeria_entry(addresses, allias, longitude, latitude, flow_slug='nashi-pitstserii'):
    token = get_moltin_token()
    url = f'{MOLTIN_URL}flows/{flow_slug}/entries'
    headers = {
        'Authorization': f'Bearer {token}',
    }

    data = {
        'data': {
            'type': 'entry',
            'pizza-address': addresses,
            'pizza-alias': allias,
            'longitude': longitude,
            'latitude': latitude,
        }
    }

    response = requests.post(url=url, headers=headers, json=data)
    response.raise_for_status()


def create_customer_entry(order_id, customer_name, longitude, latitude, flow_slug='adresa-pokupatelej'):
    token = get_moltin_token()
    url = f'{MOLTIN_URL}flows/{flow_slug}/entries'
    headers = {
        'Authorization': f'Bearer {token}',
    }
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

    if pizzerias:
        for pizzeria in pizzerias:
            try:
                create_pizzeria_entry(
                    flow_slug='nashi-pitstserii',
                    addresses=pizzeria.get('address').get('full'),
                    allias=pizzeria.get('alias'),
                    longitude=pizzeria.get('coordinates').get('lon'),
                    latitude=pizzeria.get('coordinates').get('lat')
                )
            except requests.HTTPError as error:
                logging.error(error)


def get_products():
    token = get_moltin_token()
    url = f'{MOLTIN_URL}products'
    headers = {
        'Authorization': f'Bearer {token}',
    }
    response = requests.get(url=url, headers=headers)
    response.raise_for_status()
    products = response.json().get('data')
    return [(product['id'], product['name']) for product in products]


def get_by_id(id):
    token = get_moltin_token()
    url = f'{MOLTIN_URL}products/{id}'
    headers = {
        'Authorization': f'Bearer {token}',
    }
    response = requests.get(url=url, headers=headers)
    response.raise_for_status()
    return response.json().get('data')


def get_picture(id):
    token = get_moltin_token()
    url = f'{MOLTIN_URL}files/{id}'
    headers = {
        'Authorization': f'Bearer {token}',
    }
    response = requests.get(url=url, headers=headers)
    response.raise_for_status()
    return response.json().get('data')['link']['href']


def put_in_cart(reference, product_id, quantity):
    token = get_moltin_token()
    url = f'{MOLTIN_URL}carts/{reference}/items'
    headers = {
        'Authorization': f'Bearer {token}',
    }
    data = {
        'data': {
            'id': product_id,
            'type': 'cart_item',
            'quantity': quantity,
        }
    }
    response = requests.post(url=url, headers=headers, json=data)
    response.raise_for_status()


def get_cart(reference):
    token = get_moltin_token()
    url = f'{MOLTIN_URL}carts/{reference}/items'
    headers = {
        'Authorization': f'Bearer {token}',
    }
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


def get_total(reference):
    token = get_moltin_token()
    url = f'{MOLTIN_URL}carts/{reference}'
    headers = {
        'Authorization': f'Bearer {token}',
    }
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


def delete_item_in_cart(reference, product_id):
    token = get_moltin_token()
    url = f'{MOLTIN_URL}carts/{reference}/items/{product_id}'
    headers = {
        'Authorization': f'Bearer {token}',
    }
    response = requests.delete(url, headers=headers)
    response.raise_for_status()


def create_customer(user_id, user_email, user_name, user_surname=None):
    token = get_moltin_token()
    url = f'{MOLTIN_URL}customers'
    headers = {
        'Authorization': f'Bearer {token}',
    }
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


def get_all_entries(flow_slug):
    token = get_moltin_token()
    url = f'{MOLTIN_URL}flows/{flow_slug}/entries'
    headers = {
        'Authorization': f'Bearer {token}',
    }
    response = requests.get(url=url, headers=headers)
    response.raise_for_status()
    return response.json()['data']


def get_deliverer(entry_id, flow_slug='nashi-pitstserii'):
    token = get_moltin_token()
    url = f'{MOLTIN_URL}flows/{flow_slug}/entries/{entry_id}'
    headers = {
        'Authorization': f'Bearer {token}',
    }
    response = requests.get(url=url, headers=headers)
    response.raise_for_status()
    return response.json()['data']['deliverer']


def get_customer_coordinates(entry_id, flow_slug='adresa-pokupatelej'):
    token = get_moltin_token()
    url = f'{MOLTIN_URL}flows/{flow_slug}/entries/{entry_id}'
    headers = {
        'Authorization': f'Bearer {token}',
    }
    response = requests.get(url=url, headers=headers)
    response.raise_for_status()
    return float(response.json()['data']['longitude']), float(response.json()['data']['latitude'])


if __name__ == "__main__":
    load_dotenv()

    # create_menu('menu.json')
    # print(create_flow('Наши пиццерии', 'Наши поезда самые поездатые поезда!'))
    # create_flow_fields('eba3d649-707d-4439-96ce-db0082dc2df0', 'Pizza Address', 'Pizza Alias', 'Longitude', 'Latitude')
    # create_entries_from_json('addresses.json')
    # print(create_flow('Адреса покупателей', 'Адреса наших покупателей, координаты геопозиции'))
    # create_flow_fields('577c36c1-6727-475c-8de2-84e3a035105c', 'Order', 'Customer name', 'Longitude', 'Latitude')
    # print(create_customer_entry(1, 2, 3, 4))
    # print(get_all_entries('adresa-pokupatelej'))
