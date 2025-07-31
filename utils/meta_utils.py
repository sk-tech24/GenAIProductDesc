# utils/meta_utils.py

import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote


def find_upc_by_product_name(product_name, max_results=5, validate_check_digit=False):
    """
    Search Google results for product pages and extract a 12-digit UPC (UPC-A).
    Returns the first valid UPC found, or "UPC Not Found".
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    query = requests.utils.quote(product_name)
    search_url = f"https://www.google.com/search?q={query}"
    r = requests.get(search_url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")
    
    # Extract result URLs
    links = []
    for a in soup.select("a[href]"):
        href = a['href']
        if href.startswith("/url?q="):
            url = href.split("/url?q=")[1].split("&")[0]
            if "google" not in url:
                links.append(url)
        if len(links) >= max_results:
            break

    upc_regex = re.compile(r'\b(\d{12})\b')
    
    def check_digit_valid(upc_str):
        # Validate check digit if needed
        digits = [int(d) for d in upc_str]
        odd = sum(digits[0:11:2])
        even = sum(digits[1:11:2])
        checksum = (odd * 3 + even) % 10
        check = (10 - checksum) if checksum != 0 else 0
        return check == digits[11]

    for url in links:
        try:
            resp = requests.get(url, headers=headers, timeout=5)
            if not resp.ok:
                continue
            html = resp.text
        except Exception:
            continue

        matches = upc_regex.findall(html)
        for candidate in matches:
            if validate_check_digit:
                if check_digit_valid(candidate):
                    return candidate
            else:
                return candidate

    return "UPC Not Found"


def extract_prices_from_html(html):
    """
    Extract all USD and CAD prices in a page HTML.
    """
    ua = re.compile(r'\$\s*([0-9]+(?:\.[0-9]{1,2})?)')
    cad1 = re.compile(r'CA\$\s*([0-9]+(?:\.[0-9]{1,2})?)')
    cad2 = re.compile(r'CAD\s*([0-9]+(?:\.[0-9]{1,2})?)')

    usd = [float(m) for m in ua.findall(html)]
    cad = [float(m) for m in cad1.findall(html)] + [float(m) for m in cad2.findall(html)]
    return usd, cad

def get_price_range(product_name, max_results=5):
    headers = {"User-Agent": "Mozilla/5.0"}
    query = quote(product_name + " price")
    url = f"https://www.google.com/search?q={query}"
    resp = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(resp.text, "html.parser")

    # find URLs from search results
    links = []
    for a in soup.select("a[href]"):
        href = a['href']
        if href.startswith("/url?q="):
            target = href.split("/url?q=")[1].split("&")[0]
            if "google.com" not in target:
                links.append(target)
        if len(links) >= max_results:
            break

    price_usd = []
    price_cad = []

    for link in links:
        try:
            r = requests.get(link, headers=headers, timeout=5)
            if not r.ok:
                continue
            us, ca = extract_prices_from_html(r.text)
            price_usd.extend(us)
            price_cad.extend(ca)
        except Exception:
            continue

    def summarize(prices):
        return (min(prices), max(prices)) if prices else (None, None)

    us_min, us_max = summarize(price_usd)
    ca_min, ca_max = summarize(price_cad)

    return {
        "us_min": us_min,
        "us_max": us_max,
        "ca_min": ca_min,
        "ca_max": ca_max
    }

