# utils/meta_utils.py

import re
import requests
from bs4 import BeautifulSoup


def extract_meta_title_description(product_title: str, primary_keyword: str, secondary_keyword: str) -> tuple[str, str]:
    meta_title = f"Buy {product_title} - {primary_keyword} | Best Price Online"
    meta_description = (
        f"Shop {product_title} online at the best price. Discover more about {secondary_keyword}, "
        f"benefits, usage, and ingredients. Fast delivery and genuine products."
    )
    return meta_title, meta_description


def find_upc_from_amazon(amazon_url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(amazon_url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")
        product_info = soup.find(id="detailBullets_feature_div") or soup.find(id="productDetails_detailBullets_sections1")

        if product_info:
            text = product_info.get_text(separator=" ").lower()
            match = re.search(r'upc[\s:]*([\d\-]+)', text)
            if match:
                return match.group(1).replace("-", "")
    except Exception as e:
        print(f"[UPC Fetch Error] {e}")
    return "UPC Not Found"


def get_price_range(amazon_url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(amazon_url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")
        price = soup.find("span", {"class": "a-price-whole"})
        fraction = soup.find("span", {"class": "a-price-fraction"})

        if price and fraction:
            full_price = f"{price.get_text().strip()}.{fraction.get_text().strip()}"
            return f"${full_price} USD (Approx)"
    except Exception as e:
        print(f"[Price Fetch Error] {e}")
    return "Price Not Available"
