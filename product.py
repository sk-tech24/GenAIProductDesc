import re
import time
import threading
from urllib.parse import quote_plus
from concurrent.futures import ThreadPoolExecutor, as_completed

from playwright.sync_api import sync_playwright
import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# import os
# os.system('playwright install')

# 🔍 Google Search
async def search_product_links(product_name: str, max_links=5):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"https://www.google.com/search?q={product_name}")
        await page.wait_for_timeout(2000)
        elements = await page.query_selector_all("a")
        links = []
        for e in elements:
            href = await e.get_attribute("href")
            if href and href.startswith("/url?q="):
                clean_link = href.split("/url?q=")[1].split("&")[0]
                if ("google" not in clean_link and not clean_link.startswith("#") and
                    not any(domain in clean_link for domain in ["youtube.com", "facebook.com", "instagram.com"])):
                    links.append(clean_link)
            if len(links) >= max_links:
                break
        await browser.close()
        return links

# def search_google_links(product_name: str, max_results=5):
#     search_url = f"https://www.google.com/search?q={quote_plus(product_name)}"
#     print(search_url)
#     links = []

#     with sync_playwright() as p:
#         browser = p.chromium.launch(headless=True)
#         context = browser.new_context()
#         page = context.new_page()
#         page.goto(search_url, timeout=60000)
#         page.wait_for_selector("a")

#         elements = page.query_selector_all("a")
#         for el in elements:
#             href = el.get_attribute("href")
#             if href and href.startswith("/url?q="):
#                 url = href.split("/url?q=")[1].split("&sa=U")[0]
#                 if "google.com" not in url and "webcache.googleusercontent.com" not in url:
#                     links.append(url)
#             if len(links) >= max_results:
#                 break

#         browser.close()
#     return links


def extract_prices(text: str):
    prices = re.findall(r'(?:(?:USD|US|\$|CAD|C\$)\s?)(\d+(?:\.\d{1,2})?)', text, re.IGNORECASE)
    usd_prices, cad_prices = [], []

    for match in re.finditer(r'((?:USD|US|\$)\s?(\d+(?:\.\d{1,2})?))', text, re.IGNORECASE):
        usd_prices.append(float(match.group(2)))

    for match in re.finditer(r'(?:CAD|C\$)\s?(\d+(?:\.\d{1,2})?)', text, re.IGNORECASE):
        cad_prices.append(float(match.group(1)))

    return usd_prices, cad_prices


def extract_product_info_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")

    def get_meta(name):
        tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
        return tag["content"] if tag and tag.has_attr("content") else ""

    meta_title = soup.title.string.strip() if soup.title else ""
    meta_description = get_meta("description") or get_meta("og:description")
    short_desc = soup.find("p")
    long_desc = soup.find("div")
    how_to_use = soup.find(string=re.compile("how to use", re.I))
    ingredients = soup.find(string=re.compile("ingredients", re.I))

    # Raw text for price scanning
    full_text = soup.get_text(separator=" ", strip=True)
    usd_prices, cad_prices = extract_prices(full_text)

    return {
        "meta_title": meta_title,
        "meta_description": meta_description,
        "short_description": short_desc.get_text(strip=True) if short_desc else "",
        "long_description": long_desc.get_text(strip=True)[:300] if long_desc else "",
        "how_to_use": how_to_use.strip() if how_to_use else "",
        "ingredients": ingredients.strip() if ingredients else "",
        "usd_prices": usd_prices,
        "cad_prices": cad_prices
    }


def scrape_url(url, browser):
    try:
        context = browser.new_context()
        page = context.new_page()
        page.goto(url, timeout=60000)
        page.wait_for_timeout(3000)
        html = page.content()
        context.close()
        return extract_product_info_from_html(html)
    except Exception as e:
        return {"error": str(e), "usd_prices": [], "cad_prices": []}


def scrape_product_details(product_name: str, max_links=5):
    links = await search_product_links(product_name, max_links)
    # links = search_google_links(product_name, max_links)
    print(links)
    combined_result = {
        "meta_title": "",
        "meta_description": "",
        "short_description": "",
        "long_description": "",
        "how_to_use": "",
        "ingredients": "",
        "min_price_usd": None,
        "max_price_usd": None,
        "min_price_cad": None,
        "max_price_cad": None,
        "source_links": links
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        results = []

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(scrape_url, url, browser) for url in links]
            for future in as_completed(futures):
                data = future.result()
                if "error" not in data:
                    results.append(data)

        browser.close()

    # Merge results
    usd_prices, cad_prices = [], []
    for res in results:
        for key in ["meta_title", "meta_description", "short_description", "long_description", "how_to_use", "ingredients"]:
            if not combined_result[key] and res.get(key):
                combined_result[key] = res[key]
        usd_prices.extend(res.get("usd_prices", []))
        cad_prices.extend(res.get("cad_prices", []))

    if usd_prices:
        combined_result["min_price_usd"] = min(usd_prices)
        combined_result["max_price_usd"] = max(usd_prices)
    if cad_prices:
        combined_result["min_price_cad"] = min(cad_prices)
        combined_result["max_price_cad"] = max(cad_prices)

    return combined_result


# ✅ Example usage
if __name__ == "__main__":
    product = "Sebastian Volupt Shampoo 250ml"
    result = scrape_product_details(product)
    from pprint import pprint
    pprint(result)
