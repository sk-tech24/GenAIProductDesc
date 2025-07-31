import requests
from bs4 import BeautifulSoup
import urllib.parse

def get_asin_from_search(product_name: str) -> str | None:
    url = "https://amazon-product-info2.p.rapidapi.com/Amazon/search_url"

    querystring = {"url":f"https://www.amazon.com/s?k={product_name}"}

    headers = {
        "x-rapidapi-key": "13b7138472msh960145738b578d8p1ab8a6jsn89711be2add3",
        "x-rapidapi-host": "amazon-product-info2.p.rapidapi.com"
    }

    response = requests.get(url, headers=headers, params=querystring)

    print(response.json())
    return response.json()

# Example usage
asin = get_asin_from_search("Sebastian Volupt Shampoo 250ml")
print("ASIN:", asin)
