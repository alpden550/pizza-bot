import json
import redis
from dotenv import load_dotenv

import moltin
from utils import get_database


def cache_categories(db):
    categories = moltin.get_all_categories()
    db.set('categories', json.dumps(categories))
    for slug in categories:
        category_data = moltin.get_category_by_slug(slug)
        db.set(slug, json.dumps(category_data))


def cache_products(db):
    products_data = moltin.get_products()
    product_idies = [product_id for product_id, product_name in products_data]
    db.set('products', json.dumps(products_data))
    for product_id in product_idies:
        product = moltin.get_by_id(product_id)
        image_id = product['relationships']['main_image']['data']['id']
        image_url = moltin.get_picture(image_id)

        db.set(product_id, json.dumps(product))
        db.set(image_id, image_url)


def cache_pizzerias(db):
    pizzerias = moltin.get_all_entries(flow_slug='pizzerias')
    db.set('pizzerias', json.dumps(pizzerias))


def main():
    db = redis.Redis(decode_responses=True)
    cache_categories(db)
    cache_products(db)
    cache_pizzerias(db)


if __name__ == "__main__":
    load_dotenv()
    main()
