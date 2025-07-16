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
import os

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


# 🚀 Setup
os.system("playwright install")

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

# 🧠 Generate SEO-Friendly Description
async def generate_aggregated_description(product_name, descriptions):
    combined_texts = "\n\n".join([f"Source {i+1}: {desc}" for i, desc in enumerate(descriptions)])
    prompt = f"""
    Use the dependency grammar linguistic framework rather than phrase structure grammar to craft a product description. The idea is that the closer together each pair of words you're connecting is, the easier the copy will be to comprehend. Here is the topic and additional details: 
    Based on the following descriptions for "{product_name}", generate one product description.

    Strictly follow this format:

    ### Short Description:
    [A concise overview in 2-3 sentences]

    ### Description:
    [Combine all key features and conclusion into this section. Avoid adding any headers inside.]

    ### How to Use:
    [Step-by-step usage instructions]

    Guidelines:
    - Do NOT use any extra headers like 'Key Features' or 'Conclusion'
    - Use markdown formatting exactly as shown
    - Avoid repetition

    Descriptions from sources:
    {combined_texts}
    """
    try:
        response = co.chat(model="command-r-plus-08-2024", message=prompt)
        return response.text
    except Exception as e:
        return f"Error generating summary: {str(e)}"

def build_humanizer_prompt(ai_description):
    return f"""
    
    You are a highly skilled product description writer with a knack for making products sound incredibly appealing and relatable to real people. Your goal is to take the following AI-generated product description and rewrite it with a genuine human voice, as if you are personally excited about this product and want to share its benefits with a friend.

    Ensure the output maintains the following format:

    **Short Description:** [Write a very brief, engaging summary that sparks curiosity and highlights the main reason someone would want this product. Imagine you're telling a friend about it in one or two quick sentences.]

    **Long Description:** [Craft a detailed description that goes beyond just listing features. Focus on painting a picture of how this product will fit into the customer's life and solve their problems or fulfill their desires. Use emotional language and relatable scenarios. Include a bulleted list of key features written as direct benefits to the user.]

        **Key Features (written as benefits):**
        * Imagine [Benefit 1, starting with an action verb and focusing on the 'you'] - this means you can finally [Positive outcome].
        * Get ready to [Benefit 2, again focusing on the 'you'] thanks to [Specific feature].
        * You'll love how [Benefit 3, highlighting a feeling or positive experience] because [Reason].
        * ... [Continue as needed, always focusing on the 'you' and the positive outcome]

    **How to Use:** [Explain how to use the product in a simple, conversational way. Avoid overly technical terms and focus on the user's experience.]

    **Remember, the language should feel natural, enthusiastic, and like it's coming from a real person who loves the product. Incorporate variations in sentence structure and use everyday language, including occasional contractions or interjections if appropriate for the product and target audience. The description should sound like a genuine recommendation, not a robotic listing of facts.**

    Here is the AI-generated product description you need to humanize:

    {ai_description}
    """

# 🤖 Humanize AI Output
def humanize_text_with_gemini(text):
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt_text = build_humanizer_prompt(text)
        response = model.generate_content(prompt_text)
        return response.text
    except Exception as e:
        return f"[ERROR]: {str(e)}"
    
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
st.title("🛍️ ProductSense: AI-Powered Product Descriptions")
st.markdown("Enter a product name to scrape the web and generate a description.")

if "submitted" not in st.session_state:
    st.session_state.submitted = False

with st.form("product_form"):
    product_name = st.text_input("Enter product name (e.g., Sebastian Volupt Shampoo 250ml):")
    submitted = st.form_submit_button("Generate Description")

if submitted and product_name:
    st.session_state.submitted = True
    st.session_state.product_name = product_name
elif submitted and not product_name:
    st.warning("Please enter a product name.")
    st.session_state.submitted = False

if st.session_state.submitted and product_name:
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

            ai_summary = await generate_aggregated_description(product_name, descriptions)
            human_like_summary = humanize_text_with_gemini(ai_summary)
            save_to_huggingface_dataset(product_name, human_like_summary)
            return human_like_summary, metadata

    summary, sources = asyncio.run(run())
    st.subheader("📝 Final Product Description")
    st.write(summary)

    # if seo_score:
    #     st.markdown(f"📈 **SEO Readability Score**: {round(seo_score, 2)}")

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

    st.session_state.submitted = False
