import os
from operator import itemgetter

import requests
import redis
from geopy import Point, distance

import moltin
from dotenv import load_dotenv


def get_database():
    database = redis.Redis(
        charset="utf-8",
        decode_responses=True,
    )
    return database


def get_closest_pizzeria(coordinates, flow_slug="pizzerias", all_pizzerias=None):
    entries = all_pizzerias or moltin.get_all_entries(flow_slug)
    pizzerias = []
    for entry in entries:
        pizzeria_name = entry["pizza-alias"]
        pizzeria_address = entry["pizza-address"]
        pizzeria_longitude = entry["longitude"]
        pizzetia_latitude = entry["latitude"]
        pizzeria_point = Point(pizzetia_latitude, pizzeria_longitude)
        coordinates_point = Point(coordinates[1], coordinates[0])
        pizzeria_distance = distance.distance(pizzeria_point, coordinates_point).km
        pizzeria_id = entry["id"]
        data = {
            "alias": pizzeria_name,
            "address": pizzeria_address,
            "longitude": pizzeria_longitude,
            "latitude": pizzetia_latitude,
            "distance": pizzeria_distance,
            "id": pizzeria_id,
        }
        pizzerias.append(data)
    closest_pizzeria = min(pizzerias, key=itemgetter("distance"))
    return closest_pizzeria


def calculate_distance_for_message(pizzeria):
    distance = pizzeria["distance"]
    alias = pizzeria["alias"]
    address = pizzeria["address"]
    if distance <= 0.5:
        message = f"Есть ресторан совсем рядом с вами. Доставка бесплатна, или можете забрать заказ самостоятельно, если не хотите ждать, адресс {address}."
    elif 0.5 < distance <= 5:
        message = f"Ближайшая пиццерия всего в {int(distance)} км. Похоже, придется ехать до вас на самокате, стоимость доставки 100 рублей. Доставляем или самовывоз?"
    elif 5 < distance <= 20:
        message = f"Ваша пиццерия {alias}, стоимость доставки составит 300 рублей."
    else:
        message = f"Простите, так далеко мы не доставляем. Ближайшая к вам пиццерия аж в {int(distance)} км от вас."
    return message, int(distance)


def create_chunks(products, size=7):
    for i in range(0, len(products), size):
        yield products[i: i + size]


def get_yandex_map(locations):
    url = "https://static-maps.yandex.ru/1.x/"
    params = {
        "l": "map",
        "ll": f"{locations[0]},{locations[1]}",
        "size": "650,400",
        "z": 17,
        "pt": f"{locations[0]},{locations[1]},comma",
        "scale": 1,
    }
    response = requests.get(url=url, params=params)
    response.raise_for_status()
    return response.url


def fetch_coordinates(place):
    apikey = os.getenv('YANDEX_API_KEY')
    base_url = "https://geocode-maps.yandex.ru/1.x"
    params = {"geocode": place, "apikey": apikey, "format": "json"}
    response = requests.get(base_url, params=params)
    response.raise_for_status()
    places_found = response.json()['response']['GeoObjectCollection']['featureMember']
    most_relevant = places_found[0]
    lon, lat = most_relevant['GeoObject']['Point']['pos'].split(" ")
    return lon, lat


if __name__ == "__main__":
    load_dotenv()
    db = get_database()
