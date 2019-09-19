import json
from operator import itemgetter

from geopy import Point, distance

import moltin


def get_closest_pizzeria(db, coordinates, flow_slug='pizzerias'):
    entries = json.loads(
        db.get(flow_slug)) or moltin.get_all_entries(flow_slug)
    pizzerias = []
    for entry in entries:
        pizzeria_name = entry['pizza-alias']
        pizzeria_address = entry['pizza-address']
        pizzeria_longitude = entry['longitude']
        pizzetia_latitude = entry['latitude']
        pizzeria_point = Point(pizzetia_latitude, pizzeria_longitude)
        coordinates_point = Point(coordinates[1], coordinates[0])
        pizzeria_distance = distance.distance(
            pizzeria_point, coordinates_point).km
        pizzeria_id = entry['id']
        data = {
            'alias': pizzeria_name,
            'address': pizzeria_address,
            'longitude': pizzeria_longitude,
            'latitude': pizzetia_latitude,
            'distance': pizzeria_distance,
            'id': pizzeria_id,
        }
        pizzerias.append(data)
    closest_pizzeria = min(pizzerias, key=itemgetter('distance'))
    return closest_pizzeria


def calculate_distance_for_message(pizzeria):
    distance = pizzeria['distance']
    alias = pizzeria['alias']
    address = pizzeria['address']
    if distance <= 0.5:
        message = f'Есть ресторан совсем рядом с вами. Доставка бесплатна, или можете забрать заказ самостоятельно, если не хотите ждать, адресс {address}.'
    elif 0.5 < distance <= 5:
        message = f'Ближайшая пиццерия всего в {int(distance)} км. Похоже, придется ехать до вас на самокате, стоимость доставки 100 рублей. Доставляем или самовывоз?'
    elif 5 < distance <= 20:
        message = f'Ваша пиццерия {alias}, стоимость доставки составит 300 рублей.'
    else:
        message = f'Простите, так далеко мы не доставляем. Ближайшая к вам пиццерия аж в {int(distance)} км от вас.'
    return message, int(distance)


if __name__ == "__main__":
    pass
