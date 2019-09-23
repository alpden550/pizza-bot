import json
import logging
import os
from io import BytesIO
from json.decoder import JSONDecodeError

import requests
import vk_api
from dotenv import load_dotenv
from vk_api import VkUpload
from vk_api.exceptions import ApiError
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.longpoll import VkEventType, VkLongPoll
from vk_api.utils import get_random_id
from yandex_geocoder import Client
from yandex_geocoder.exceptions import YandexGeocoderAddressNotFound

import moltin
import utils

VK_GRROUP_ID = 6976575
PAYEE = 91623053


def upload_photo_for_message(vk, image_url):
    upload = VkUpload(vk)

    attachment = []
    image_content = requests.get(image_url)
    image_content.raise_for_status()
    file_obj = BytesIO(image_content.content)
    photo = upload.photo_messages(file_obj)[0]
    attachment.append("photo{}_{}".format(photo["owner_id"], photo["id"]))
    return attachment


def create_menu_buttons(chunk):
    products = moltin.get_products()
    chunks = list(utils.create_chunks(products, size=5))
    last_chunk = len(chunks) - 1
    keyboard = VkKeyboard(one_time=True)

    for product in chunks[chunk]:
        slug, name = product
        keyboard.add_button(name, payload=json.dumps(slug))
        keyboard.add_line()
    if chunk == 0:
        keyboard.add_button("Следущие", payload=json.dumps("next"))
    elif chunk == last_chunk:
        keyboard.add_button("Предыдущие", payload=json.dumps("prev"))
    else:
        keyboard.add_button("Предыдущие", payload=json.dumps("prev"))
        keyboard.add_button("Следущие", payload=json.dumps("next"))
    keyboard.add_line()
    keyboard.add_button(
        "Корзина", payload=json.dumps("basket"), color=VkKeyboardColor.PRIMARY
    )
    return keyboard.get_keyboard()


def create_description_buttons():
    buttons_list = [["1 шт", "cart 1"], ["3 шт", "cart 3"], ["5 шт", "cart 5"]]
    keyboard = VkKeyboard()
    for button_name, button_id in buttons_list:
        keyboard.add_button(button_name, payload=json.dumps(button_id))
    keyboard.add_line()
    keyboard.add_button(
        "Назад в меню", payload=json.dumps("back"), color=VkKeyboardColor.POSITIVE
    )
    keyboard.add_line()
    keyboard.add_button(
        "Корзина", payload=json.dumps("basket"), color=VkKeyboardColor.PRIMARY
    )
    return keyboard.get_keyboard()


def create_basket_buttons(user_id=None):
    user_basket = moltin.get_cart(user_id)
    keyboard = VkKeyboard()
    for product in user_basket:
        pr_name = product["name"]
        cart_id = product["cart_id"]
        keyboard.add_button(f"Удалить {pr_name}", payload=json.dumps(cart_id))
        keyboard.add_line()
    keyboard.add_button(
        "Назад в меню", payload=json.dumps("back"), color=VkKeyboardColor.POSITIVE
    )
    keyboard.add_line()
    keyboard.add_button(
        "Оформить заказ", payload=json.dumps("order"), color=VkKeyboardColor.NEGATIVE
    )
    return keyboard.get_keyboard()


def create_delivery_buttons(distance):
    keyboard = VkKeyboard()
    if distance <= 20:
        keyboard.add_button("Доставка", payload=json.dumps("delivery"))
        keyboard.add_line()
        keyboard.add_button("Самовывоз", payload=json.dumps("pickup"))
    else:
        keyboard.add_button("Самовывоз", payload=json.dumps("pickup"))
    return keyboard.get_keyboard()


def create_payment_buttons(amount, recipient=PAYEE):
    keyboard = VkKeyboard()
    keyboard.add_button("Наличными", payload=json.dumps("cash"))
    keyboard.add_line()
    keyboard.add_button(
        "Банковской картой онлайн",
        payload=json.dumps("bank_card"),
        color=VkKeyboardColor.POSITIVE,
    )
    keyboard.add_line()
    pay_hash = (
        f"action=pay-to-user&aid={VK_GRROUP_ID}&amount={amount}&user_id={recipient}"
    )
    keyboard.add_vkpay_button(hash=pay_hash, payload=json.dumps("vk_pay"))
    return keyboard.get_keyboard()


def start(event, vk):
    user_id = event.user_id
    keyboard = create_menu_buttons(chunk=0)

    user_data = json.loads(db.get(f"vk_{user_id}"))
    user_data["last_chunk"] = 0
    db.set(f"vk_{user_id}", json.dumps(user_data))

    vk.messages.send(
        user_id=user_id,
        message="Пожалуйста, выберите пиццу или много пицц :)",
        random_id=get_random_id(),
        keyboard=keyboard,
    )
    return "HANDLE_MENU"


def handle_button(event, vk):
    payload = json.loads(event.payload)
    user_id = event.user_id
    user_data = json.loads(db.get(f"vk_{user_id}"))
    chunk = user_data["last_chunk"]

    if payload == "basket":
        total = moltin.get_total(user_id)
        keyboard = create_basket_buttons(user_id)
        vk.messages.send(
            user_id=user_id,
            message=f"В корзине пицц на {total}",
            random_id=get_random_id(),
            keyboard=keyboard,
        )
        return "HANDLE_BASKET"
    elif payload == "next":
        keyboard = create_menu_buttons(chunk=chunk + 1)
        vk.messages.send(
            user_id=user_id,
            message="Пожалуйста, выберите пиццу или много пицц :)",
            random_id=get_random_id(),
            keyboard=keyboard,
        )
        user_data["last_chunk"] += 1
        db.set(f"vk_{user_id}", json.dumps(user_data))
        return "HANDLE_MENU"
    elif payload == "prev":
        keyboard = create_menu_buttons(chunk=chunk - 1)
        vk.messages.send(
            user_id=user_id,
            message="Пожалуйста, выберите пиццу или много пицц :)",
            random_id=get_random_id(),
            keyboard=keyboard,
        )
        user_data["last_chunk"] -= 1
        db.set(f"vk_{user_id}", json.dumps(user_data))
        return "HANDLE_MENU"
    else:
        pizza_data = json.loads(db.get(payload)) or moltin.get_by_id(payload)
        pizza_name = pizza_data["name"]
        pizza_text = pizza_data["description"]
        pizza_price = pizza_data["meta"]["display_price"]["with_tax"]["formatted"]
        image_id = pizza_data["relationships"]["main_image"]["data"]["id"]
        image_url = db.get(image_id) or moltin.get_picture(image_id)

        user_data = json.loads(db.get(f'vk_{user_id}'))
        user_data['last_product'] = payload
        db.set(f'vk_{user_id}', json.dumps(user_data))

        try:
            attachments = upload_photo_for_message(vk, image_url)
        except (requests.HTTPError, requests.ConnectionError, ApiError) as error:
            attachments = []
            logging.exception(error)
        message = f"{pizza_name}\n{pizza_text}\n\nЦена {pizza_price}"
        keyboard = create_description_buttons()

        vk.messages.send(
            user_id=user_id,
            message=message,
            random_id=get_random_id(),
            attachment=",".join(attachments),
            keyboard=keyboard,
        )
        return "HANDLE_DESCRIPTION"


def handle_description(event, vk):
    try:
        payload = json.loads(event.payload)
    except AttributeError:
        return "HANDLE_DESCRIPTION"
    user_id = event.user_id
    user_data = json.loads(db.get(f"vk_{user_id}"))
    chunk = user_data["last_chunk"]
    product_id = user_data["last_product"]
    keyboard = VkKeyboard().get_empty_keyboard()
    vk.messages.send(
        user_id=user_id, message="Принято", random_id=get_random_id(), keyboard=keyboard
    )

    if payload == "back":
        keyboard = create_menu_buttons(chunk=chunk)
        vk.messages.send(
            user_id=user_id,
            message="Пожалуйста, выберите пиццу или много пицц :)",
            random_id=get_random_id(),
            keyboard=keyboard,
        )
        return "HANDLE_MENU"
    elif payload == "basket":
        total = moltin.get_total(user_id)
        keyboard = create_basket_buttons(user_id)
        vk.messages.send(
            user_id=user_id,
            message=f"В корзине пицц на {total}",
            random_id=get_random_id(),
            keyboard=keyboard,
        )
        return "HANDLE_BASKET"
    elif payload.split()[0] == "cart":
        quantity = int(payload.split()[1])
        moltin.put_in_cart(user_id, product_id, quantity)
        keyboard = VkKeyboard().get_empty_keyboard()
        vk.messages.send(
            user_id=user_id,
            message=f"{quantity} добавили в корзину",
            random_id=get_random_id(),
        )
        keyboard = create_menu_buttons(chunk=chunk)
        vk.messages.send(
            user_id=user_id,
            message="Пожалуйста, выберите пиццу или много пицц :)",
            random_id=get_random_id(),
            keyboard=keyboard,
        )
        return "HANDLE_MENU"


def handle_basket(event, vk):
    try:
        payload = json.loads(event.payload)
    except AttributeError:
        return "HANDLE_DESCRIPTION"
    user_id = event.user_id
    user_data = json.loads(db.get(f"vk_{user_id}"))
    chunk = user_data["last_chunk"]
    keyboard = VkKeyboard().get_empty_keyboard()
    vk.messages.send(
        user_id=user_id, message="Принято", random_id=get_random_id(), keyboard=keyboard
    )
    if payload == "back":
        keyboard = create_menu_buttons(chunk=chunk)
        vk.messages.send(
            user_id=user_id,
            message="Пожалуйста, выберите пиццу или много пицц :)",
            random_id=get_random_id(),
            keyboard=keyboard,
        )
        return "HANDLE_MENU"
    elif payload == "order":
        vk.messages.send(
            user_id=user_id,
            message=f"Введите адрес для доставки:",
            random_id=get_random_id(),
        )
        return "HANDLE_GEO"
    else:
        moltin.delete_item_in_cart(user_id, product_id=payload)
        keyboard = create_basket_buttons(user_id)
        total = moltin.get_total(user_id)
        vk.messages.send(
            user_id=user_id,
            message=f"В корзине пицц на {total}",
            random_id=get_random_id(),
            keyboard=keyboard,
        )
        return "HANDLE_BASKET"


def handle_locations(event, vk):
    message = event.text
    user_id = event.user_id

    try:
        current_pos = Client.coordinates(message)
    except YandexGeocoderAddressNotFound as error:
        logging.error(error)
        vk.messages.send(
            user_id=user_id,
            message=f"Введите адрес для доставки:",
            random_id=get_random_id(),
        )
        current_pos = None

    if current_pos is None:
        return "HANDLE_GEO"

    closest_pizzeria = utils.get_closest_pizzeria(db, current_pos)
    message, dist = utils.calculate_distance_for_message(closest_pizzeria)
    keyboard = create_delivery_buttons(distance=dist)
    vk.messages.send(
        user_id=user_id, message=message, random_id=get_random_id(), keyboard=keyboard
    )
    user_data = json.loads(db.get(f"vk_{user_id}"))
    user_data["closest_pizzeria"] = closest_pizzeria
    user_data["customer_geo"] = current_pos
    db.set(f"vk_{user_id}", json.dumps(user_data))
    return "HANDLE_DELIVERY"


def handle_delivery(event, vk):
    try:
        payload = json.loads(event.payload)
    except AttributeError:
        return "HANDLE_DELIVERY"
    user_id = event.user_id

    user_data = json.loads(db.get(f"vk_{user_id}"))
    closest_pizzeria = user_data["closest_pizzeria"]
    pizzeria_name = closest_pizzeria["alias"]
    pizzeria_address = closest_pizzeria["address"]
    customer_geo = user_data["customer_geo"]
    user_total = moltin.get_total(user_id)
    amount = user_total.split()[0].split(".")[0].replace(",", "")

    keyboard = VkKeyboard().get_empty_keyboard()
    vk.messages.send(
        user_id=user_id,
        message=f"Принято",
        random_id=get_random_id(),
        keyboard=keyboard,
    )

    if payload in ["pickup"]:
        locations = Client.coordinates(pizzeria_address)
        pizza_map = utils.get_yandex_map(locations)
        keyboard = create_payment_buttons(amount)
        try:
            attachments = upload_photo_for_message(vk, pizza_map)
        except (requests.HTTPError, requests.ConnectionError, ApiError) as error:
            attachments = []
            logging.exception(error)
        message = f"Спасибо за заказ. Вы можете забрать его в {pizzeria_name}, по адресу: {pizzeria_address}\n\n"
        message += f"Ваш заказ на {amount} руб. Какой способ оплаты выберете?"
        vk.messages.send(
            user_id=user_id,
            message=message,
            random_id=get_random_id(),
            keyboard=keyboard,
            attachment=",".join(attachments),
        )
        return "HANDLE_PAYMENT"

    elif payload == "delivery":
        pizza_map = utils.get_yandex_map(customer_geo)
        keyboard = create_payment_buttons(amount)
        try:
            attachments = upload_photo_for_message(vk, pizza_map)
        except (requests.HTTPError, requests.ConnectionError, ApiError) as error:
            attachments = []
            logging.exception(error)
        message = f"Спасибо за заказ, вы выбрали доставку по адресу.\n\n"
        message += f"Ваш заказ на {amount} руб. Какой способ оплаты выберете?"
        vk.messages.send(
            user_id=user_id,
            message=message,
            random_id=get_random_id(),
            keyboard=keyboard,
            attachment=",".join(attachments),
        )
        return "HANDLE_PAYMENT"


def handle_payment(event, vk):
    user_id = event.user_id
    try:
        payload = json.loads(event.payload)
    except AttributeError:
        return "HANDLE_PAYMENT"

    keyboard = VkKeyboard().get_empty_keyboard()
    vk.messages.send(
        user_id=user_id,
        message=f"Принято.",
        random_id=get_random_id(),
        keyboard=keyboard,
    )

    if payload == "cash":
        vk.messages.send(
            user_id=user_id,
            message="Спасибо за заказ, приходите еще.",
            random_id=get_random_id(),
        )
        return "START"
    elif payload == "bank_card":
        message = "Тут должна быть реализация оплаты банковской картой онлайн: робокасса, яндекс касса, и т.п."
        vk.messages.send(user_id=user_id, message=message, random_id=get_random_id())
        return "START"
    elif payload == "vk_pay":
        vk.messages.send(
            user_id=user_id,
            message="Спасибо за заказ, приходите еще!",
            random_id=get_random_id(),
        )
        return "START"


def handle_user_reply(event, vk):
    if event.extra_values.get("payload"):
        user_reply = json.loads(event.payload)
        user_id = event.user_id
    elif event.message:
        user_reply = event.text
        user_id = event.user_id
    else:
        return

    if type(user_reply) is dict:
        user_state = "START"
    elif user_reply.lower().strip() in ["начать", "старт", "start"]:
        user_state = "START"
    else:
        user = db.get(f"vk_{user_id}")
        try:
            user_state = json.loads(user)["state"]
        except (TypeError, JSONDecodeError) as error:
            logging.exception(error)
            user_state = None

    states_functions = {
        "START": start,
        "HANDLE_MENU": handle_button,
        "HANDLE_DESCRIPTION": handle_description,
        "HANDLE_BASKET": handle_basket,
        "HANDLE_GEO": handle_locations,
        "HANDLE_DELIVERY": handle_delivery,
        "HANDLE_PAYMENT": handle_payment,
    }
    state_handler = states_functions.get(user_state)

    try:
        next_state = state_handler(event, vk)
    except Exception as error:
        logging.exception(error)
        next_state = None

    if next_state is None:
        return

    user = db.get(f"vk_{user_id}")
    if user:
        user_data = json.loads(user)
        user_data["state"] = next_state
    else:
        user_data = {"state": next_state}
    db.set(f"vk_{user_id}", json.dumps(user_data))


if __name__ == "__main__":
    load_dotenv()

    global db
    db = utils.get_database()

    vk_session = vk_api.VkApi(token=os.getenv("VK_TOKEN"))
    vk = vk_session.get_api()
    longpoll = VkLongPoll(vk_session)
    for event in longpoll.listen():
        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
            handle_user_reply(event, vk)
