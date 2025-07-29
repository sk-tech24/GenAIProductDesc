# 📦 Streamlit Product Info Scraper App (SEO-Optimized + Humanized)

import streamlit as st
import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import os
import cohere
import re
import aiohttp
import requests
from datasets import Dataset, load_dataset, concatenate_datasets
import google.generativeai as genai
from utils.meta_utils import extract_meta_title_description, find_upc_by_product_name, get_price_range

# 🚀 Setup
os.system("playwright install")

# 🔐 API Configuration
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
co = cohere.Client(COHERE_API_KEY)
HF_DATASET_NAME = "Jay-Rajput/product_desc"

# 🔍 Google Search
async def search_product_links(query, max_links=5):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"https://www.google.com/search?q={query}")
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

# 🕷️ Scraper
async def extract_product_info(session, url):
    try:
        async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10) as response:
            text = await response.text()
            soup = BeautifulSoup(text, "html.parser")
            title = soup.title.text.strip() if soup.title else ""
            meta_desc = soup.find("meta", attrs={"name": "description"})
            short_desc = meta_desc['content'] if meta_desc else ""
            paragraphs = soup.find_all("p")
            body_text = " ".join([p.text.strip() for p in paragraphs[:15] if len(p.text.strip()) > 30])

            keywords = ["price", "buy", "add to cart", "mrp", "product", "brand", "description"]
            combined_text = f"{title.lower()} {short_desc.lower()} {body_text.lower()}"
            keyword_matches = sum(1 for word in keywords if word in combined_text)

            if keyword_matches < 2 or len(body_text) < 100:
                return {"url": url, "error": "Page doesn't appear to be a product page."}

            return {
                "url": url,
                "title": title,
                "short_desc": short_desc,
                "long_desc": body_text
            }
    except Exception as e:
        return {"url": url, "error": str(e)}

# 🧠 Generate Structured Description
async def generate_aggregated_description(product_name, primary_keyword, secondary_keywords, descriptions):
    combined_texts = "\n\n".join([f"Source {i+1}: {desc}" for i, desc in enumerate(descriptions)])
    prompt = f"""
Create an SEO-optimized product description for: {product_name}

Use this format:

**Meta Title**: [max 60 chars, start with primary keyword]
**Meta Description**: [120–160 chars, include 1–2 primary keywords]

### Short Description:
[Concise overview using primary + secondary keywords. 2-4 sentences. 50–160 words.]

### Description:
[Full body including problem, solution, benefits, features. Use primary/secondary keywords naturally. 300–350 words. No headers inside.]

### How to Use:
[Simple usage instructions.]

### Ingredients:
[List of main ingredients, if available. Add note about full list on packaging.]

Descriptions from sources:
{combined_texts}
"""
    try:
        response = co.chat(model="command-r-plus-08-2024", message=prompt)
        return response.text
    except Exception as e:
        return f"Error generating summary: {str(e)}"

# 🤖 Humanizer
from utils.gemini_wrapper import humanize_text_with_gemini

# 💾 Save to HF Dataset
def save_to_huggingface_dataset(product_name, description):
    new_data = Dataset.from_dict({
        "product_name": [product_name],
        "description": [description]
    })
    try:
        existing = load_dataset(HF_DATASET_NAME, split="train")
        combined = concatenate_datasets([existing, new_data])
    except:
        combined = new_data

    combined.push_to_hub(HF_DATASET_NAME, split="train", private=False)

# 🚀 Streamlit UI
st.set_page_config(page_title="ProductSense", page_icon="🛍️", layout="wide")
st.title("🛍️ ProductSense: SEO-Enhanced Product Descriptions")

with st.form("product_form"):
    col1, col2 = st.columns([3, 2])
    with col1:
        product_name = st.text_input(
            "Product Name",
            placeholder="E.g. Sebastian Volupt Shampoo 250 ml",
            label_visibility="visible"
        )
    with col2:
        primary_keyword = st.text_input(
            "Primary Keyword (optional)",
            placeholder="e.g. volumizing shampoo"
        )
    secondary_keywords = st.text_input(
        "Secondary Keywords (optional, comma-separated)",
        placeholder="e.g. body, bounce, fine hair"
    )
    submitted = st.form_submit_button(label="Generate Description")

if submitted and product_name:
    async def run():
        with st.spinner("Fetching sources and generating..."):
            urls = await search_product_links(product_name, max_links=5)
            descriptions = []
            metadata = []
            async with aiohttp.ClientSession() as session:
                scrape_tasks = [extract_product_info(session, url) for url in urls]
                scraped_data = await asyncio.gather(*scrape_tasks)
                for raw in scraped_data:
                    if 'error' not in raw:
                        descriptions.append(raw['long_desc'])
                        metadata.append(raw)
                    else:
                        metadata.append(raw)

            ai_summary = await generate_aggregated_description(product_name, primary_keyword, secondary_keywords, descriptions)
            humanized_summary = humanize_text_with_gemini(ai_summary)

            upc = find_upc_by_product_name(product_name)
            price_data = get_price_range(product_name)

            # save_to_huggingface_dataset(product_name, humanized_summary)

            return humanized_summary, metadata, upc, price_data

    summary, sources, upc_code, price_info = asyncio.run(run())

    st.subheader("📝 Product Description")
    st.markdown(summary)

    st.subheader("📦 Additional Details")
    st.markdown(f"**UPC Code:** {upc_code if upc_code else 'Not Found'}")
    if price_info:
        us_range = f"${price_info['us_min']} – ${price_info['us_max']}" if price_info['us_min'] is not None else "Not found"
        ca_range = f"CA${price_info['ca_min']} – CA${price_info['ca_max']}" if price_info['ca_min'] is not None else "Not found"
        st.markdown(f"**Price Range:**\n- **USA**: {us_range}\n- **Canada**: {ca_range}")

