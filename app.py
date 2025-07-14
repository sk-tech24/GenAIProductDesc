# 📦 Streamlit Product Info Scraper App (Hugging Face MVP with Cohere Summary)

import streamlit as st
import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import os
import cohere
import re
import aiohttp
import requests
from datasets import Dataset, DatasetDict, load_dataset, concatenate_datasets, disable_caching

os.system("playwright install")

# Load environment variables for API keys
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
HF_API_TOKEN = os.getenv("HF_API_TOKEN")
co = cohere.Client(COHERE_API_KEY)

# Disable datasets caching to avoid read-only FS issues on HF Spaces
# disable_caching()
HF_DATASET_NAME = "Jay-Rajput/product_desc"

# 1. 🔍 Google Search via Playwright
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

# 2. 🕷️ Async Scraper with Robust Validation
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

            # ✅ Validation rules to ensure it's a product page
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

# 3. 🧠 Aggregate and Summarize with Cohere
async def generate_aggregated_description(product_name, descriptions):
    combined_texts = "\n\n".join([f"Source {i+1}: {desc}" for i, desc in enumerate(descriptions)])
    prompt = f"""
You are a professional product copywriter. Based on the following product descriptions from various websites, write a single human-like, emotionally engaging, and informative product description for "{product_name}".

📌 Guidelines:
- Start with a **short description** (overview).
- Merge all **key features** into the main product description without a heading.
- Add a **How to Use** section.
- End the product description with any concluding insights — as a continuation of the main paragraph.
- Do NOT use subheadings like 'Conclusion' or 'Key Features'.
- Maintain a friendly, conversational tone like a real human would write.
- Format using **markdown** (e.g., bold titles).
- Keep it under 800 words.

{combined_texts}

Return only the final formatted product description.
"""
    try:
        response = co.chat(model="command-r-plus-08-2024", message=prompt)
        return response.text
    except Exception as e:
        return f"Error generating summary: {str(e)}"

# 4. 🤖 Optional Paraphrasing with Hugging Face

def paraphrase_with_huggingface(text):
    api_url = "https://api-inference.huggingface.co/models/tuner007/pegasus_paraphrase"
    headers = {
        "Authorization": f"Bearer {HF_API_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": text,
        "parameters": {
            "num_return_sequences": 1,
            "num_beams": 5
        }
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload)
        if response.status_code == 200:
            return response.json()[0]["generated_text"]
        else:
            return text  # fallback to original
    except Exception as e:
        return text

# 5. 💾 Save to Hugging Face Dataset
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

# 6. 🚀 Streamlit Async Wrapper
st.title("🛍️ ProductSense: Smart Product Descriptions")
product_name = st.text_input("Enter product name (e.g., Sebastian Volupt Shampoo 250ml):")

if product_name:
    async def run():
        with st.spinner("Searching and scraping..."):
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

            final_summary = await generate_aggregated_description(product_name, descriptions)
            human_like_summary = paraphrase_with_huggingface(final_summary)
            save_to_huggingface_dataset(product_name, human_like_summary)
            return human_like_summary, metadata

    summary, sources = asyncio.run(run())
    st.subheader("📝 Final Product Description")
    st.write(summary)

    # st.subheader("🔗 Sources Used")
    # for result in sources:
    #     url = result.get("url", "")
    #     title = result.get("title", "").strip()
    #     error = result.get("error")

    #     if error:
    #         st.warning(f"❌ {url} — {error}")
    #     else:
    #         display_title = title if title else "🔗 View Page"
    #         st.markdown(f"[**{display_title}**]({url})")
