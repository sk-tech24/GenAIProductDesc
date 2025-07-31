# --------------------------------------------------------------------------
# ProductSense AI Agent - Enhanced Version
#
# This Streamlit application acts as a sophisticated AI agent for e-commerce.
# It takes a product name and keywords, scours the web for information,
# and generates a comprehensive, SEO-optimized, and human-like product
# listing.
#
# Author: Jay
# Version: 2.0
# --------------------------------------------------------------------------

import streamlit as st
import asyncio
import os
import google.generativeai as genai
import json
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import aiohttp
from datasets import Dataset, load_dataset, concatenate_datasets


# --- Configuration & Initialization ---
import os
os.system('playwright install')

# Configure the Gemini API key
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


# Hugging Face dataset configuration
HF_DATASET_NAME = "Jay-Rajput/product_desc"
HF_TOKEN = st.secrets.get("HF_TOKEN") or os.getenv("HF_TOKEN")


# --- Web Scraping and Data Extraction Modules ---
async def get_search_links(query: str, num_links: int = 5) -> list:
    """
    Uses Playwright to perform a Google search and return top organic results.
    Filters out common non-product domains.
    """
    links = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(f"https://www.google.com/search?q={query.replace(' ', '+')}")
            await page.wait_for_selector('div#search', state='attached', timeout=10000)

            elements = await page.query_selector_all("a")
            for element in elements:
                href = await element.get_attribute("href")
                if href and href.startswith("/url?q="):
                    clean_link = href.split("/url?q=")[1].split("&")[0]
                    # Filter out irrelevant domains
                    if not any(domain in clean_link for domain in ["google.com", "youtube.com", "facebook.com", "instagram.com", "pinterest.com"]):
                        links.append(clean_link)
                if len(links) >= num_links:
                    break
            await browser.close()
    except Exception as e:
        st.error(f"An error occurred during web search: {e}")
    return links

async def scrape_page_content(session: aiohttp.ClientSession, url: str) -> dict:
    """
    Asynchronously scrapes the text content of a given URL.
    Returns a dictionary with the URL and its cleaned text content or an error.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        async with session.get(url, headers=headers, timeout=15) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")
                # Remove script and style elements
                for script_or_style in soup(["script", "style"]):
                    script_or_style.decompose()
                # Get text and clean it up
                text = soup.get_text()
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                cleaned_text = '\n'.join(chunk for chunk in chunks if chunk)
                return {"url": url, "content": cleaned_text[:5000]} # Limit content length
            else:
                return {"url": url, "error": f"HTTP Status {response.status}"}
    except Exception as e:
        return {"url": url, "error": str(e)}

async def get_shopping_data(product_name: str, country_code: str) -> str:
    """
    Scrapes Google Shopping results for a product in a specific country.
    """
    country_domains = {"ca": "google.ca", "us": "google.com"}
    gl_codes = {"ca": "ca", "us": "us"}
    domain = country_domains.get(country_code.lower(), "google.com")
    gl = gl_codes.get(country_code.lower(), "us")
    
    query = f"{product_name} upc"
    search_url = f"https://www.{domain}/search?q={query.replace(' ', '+')}&tbm=shop&gl={gl}"

    content = ""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(search_url)
            await page.wait_for_selector('body', state='attached', timeout=10000)
            content = await page.inner_text('body')
            await browser.close()
    except Exception as e:
        st.warning(f"Could not fetch shopping data for {country_code.upper()}: {e}")
    
    return content


# --- AI Content Generation Module ---
def build_master_prompt(product_name: str, primary_keywords: str, secondary_keywords: str, web_context: str, shopping_context_us: str, shopping_context_ca: str) -> str:
    """
    Constructs the detailed, structured prompt for the Gemini model.
    """
    return f"""
    As an expert eCommerce content strategist and copywriter, your task is to generate a complete and optimized product listing.

    **Product Information:**
    - Product Name: "{product_name}"
    - Primary Keywords: "{primary_keywords}"
    - Secondary Keywords: "{secondary_keywords}"

    **Source Content (from web scraping):**
    --- WEB CONTEXT ---
    {web_context}
    --- END WEB CONTEXT ---

    **Google Shopping Scraped Data (for pricing/UPC extraction):**
    --- USA SHOPPING CONTEXT ---
    {shopping_context_us}
    --- END USA SHOPPING CONTEXT ---

    --- CANADA SHOPPING CONTEXT ---
    {shopping_context_ca}
    --- END CANADA SHOPPING CONTEXT ---

    **Your Task:**
    Based on all the provided information, generate a JSON object with the following structure and adhere to all constraints. Do not include any text outside of the JSON object.

    {{
      "meta_title": "string",
      "meta_description": "string",
      "short_description": "string",
      "description": "string",
      "how_to_use": "string",
      "ingredients": "string",
      "upc": "string",
      "usa_prices": {{
        "highest": "string",
        "lowest": "string"
      }},
      "canada_prices": {{
        "highest": "string",
        "lowest": "string"
      }}
    }}

    **Content Constraints and Instructions:**

    1.  **meta_title**:
        - Length: 50-60 characters MAXIMUM.
        - Content: Must include the most important primary keywords at the beginning. Be concise and compelling.

    2.  **meta_description**:
        - Length: 120-160 characters MAXIMUM.
        - Content: Include 1-2 primary keywords and create an engaging summary to encourage clicks.

    3.  **short_description**:
        - Length: 50-160 words (2-4 sentences).
        - Content: Use one or two primary keywords and 1-2 secondary keywords naturally. Do not stuff keywords. Write in a human, engaging tone.

    4.  **description**:
        - Length: 300-350 words.
        - Content: This is the main body. It should be well-structured and persuasive.
        - Address the target problem the product solves.
        - Highlight the key benefits and features.
        - Incorporate primary and secondary keywords naturally throughout the text.
        - Use a human-like, slightly informal, and trustworthy tone. Use varied sentence structures. Avoid marketing cliches.

    5.  **how_to_use**:
        - Content: Provide simple, clear, step-by-step instructions for using the product.

    6.  **ingredients**:
        - Content: Based on the web context, list the main active or key ingredients. If you cannot find any, state "Ingredients not available online.". Conclude with the note: "For a complete list of ingredients, please refer to the product packaging."

    7.  **upc**:
        - Content: Extract the product's UPC (Universal Product Code) from the shopping context. If multiple are found, list the most likely one. If none is found, return "Not found".

    8.  **usa_prices** & **canada_prices**:
        - Content: From the respective shopping contexts, identify the highest and lowest prices.
        - Format as a string, e.g., "$25.99 USD" or "$32.50 CAD".
        - If no prices can be reliably determined, return "Not found".

    Generate only the JSON object as your response.
    """

def generate_content_with_gemini(prompt: str) -> dict:
    """
    Calls the Gemini API to generate the product content and parses the JSON response.
    """
    try:
        model = genai.GenerativeModel("gemini-1.5-pro-latest")
        response = model.generate_content(prompt)
        
        # Clean the response to ensure it's valid JSON
        text_response = response.text.strip()
        # Find the start and end of the JSON object
        json_start = text_response.find('{')
        json_end = text_response.rfind('}') + 1
        
        if json_start != -1 and json_end != 0:
            json_str = text_response[json_start:json_end]
            return json.loads(json_str)
        else:
            return {"error": "Failed to parse valid JSON from the AI response."}

    except Exception as e:
        st.error(f"Error during AI content generation: {e}")
        return {"error": str(e)}

# --- Data Persistence ---

def save_to_huggingface(product_name: str, generated_data: dict):
    """Saves the generated data to a Hugging Face dataset."""
    if not HF_TOKEN:
        st.warning("Hugging Face token not found. Skipping dataset save.")
        return

    try:
        # Convert the dictionary to a JSON string for the 'description' column
        data_to_save = {
            "product_name": [product_name],
            "description": [json.dumps(generated_data)]
        }
        new_hf_dataset = Dataset.from_dict(data_to_save)

        # Append to the existing dataset
        new_hf_dataset.push_to_hub(HF_DATASET_NAME, token=HF_TOKEN)
        st.success(f"Successfully saved to Hugging Face Dataset: {HF_DATASET_NAME}")

    except Exception as e:
        st.error(f"Failed to save to Hugging Face Hub: {e}")


# --- Streamlit User Interface ---

st.set_page_config(page_title="ProductSense AI Agent", page_icon="🛍️", layout="wide")

st.title("🛍️ ProductSense AI Agent")
st.markdown("Enter product details to generate a complete, SEO-optimized product listing using AI.")

with st.form("product_agent_form"):
    st.subheader("1. Input Product Details")
    product_name = st.text_input(
        "**Product Name**",
        placeholder="e.g., Fanola No Yellow Shampoo 350 ml",
        help="The full, specific name of the product."
    )
    primary_keywords = st.text_input(
        "**Primary Keywords**",
        placeholder="e.g., Shampoo, violet shampoo, toning shampoo",
        help="The most important keywords for your product."
    )
    secondary_keywords = st.text_input(
        "**Secondary Keywords**",
        placeholder="e.g., hair care, colored hair, brassy hair treatment",
        help="Related keywords that add context."
    )
    
    submit_button = st.form_submit_button("✨ Generate Product Listing")

if submit_button and product_name and primary_keywords:
    
    st.markdown("---")
    st.subheader("2. AI Processing and Generation")
    
    progress_bar = st.progress(0)
    status_text = st.empty()

    async def main_process():
        # Step 1: Web Scraping for general content
        status_text.info("🔍 Searching Google for product pages...")
        links = await get_search_links(product_name, num_links=5)
        if not links:
            st.error("Could not find any relevant web pages. Please check the product name.")
            return None
        progress_bar.progress(10)

        status_text.info(f"🕷️ Scraping {len(links)} web pages for content...")
        async with aiohttp.ClientSession() as session:
            tasks = [scrape_page_content(session, link) for link in links]
            results = await asyncio.gather(*tasks)
        
        web_context = "\n\n".join(
            f"--- Source: {res['url']} ---\n{res['content']}"
            for res in results if "content" in res
        )
        progress_bar.progress(30)

        # Step 2: Scraping Google Shopping for US and CA
        status_text.info("🇺🇸 Fetching USA shopping data...")
        shopping_context_us = await get_shopping_data(product_name, "us")
        progress_bar.progress(50)

        status_text.info("🇨🇦 Fetching Canada shopping data...")
        shopping_context_ca = await get_shopping_data(product_name, "ca")
        progress_bar.progress(70)

        # Step 3: AI Content Generation
        status_text.info("🧠 Building prompt and calling AI model... This may take a moment.")
        master_prompt = build_master_prompt(
            product_name, primary_keywords, secondary_keywords, 
            web_context, shopping_context_us, shopping_context_ca
        )
        
        # For debugging the prompt
        with st.expander("Show Master Prompt Sent to AI"):
            st.text(master_prompt)

        generated_data = generate_content_with_gemini(master_prompt)
        progress_bar.progress(100)
        status_text.success("✅ Content generation complete!")
        
        return generated_data

    # Run the main async process
    final_data = asyncio.run(main_process())

    if final_data and "error" not in final_data:
        st.markdown("---")
        st.subheader("3. Generated Product Listing")

        # Displaying the results in a structured and clean way
        st.text_input("Meta Title", value=final_data.get("meta_title", ""), disabled=True)
        st.text_area("Meta Description", value=final_data.get("meta_description", ""), height=100, disabled=True)
        
        col1, col2 = st.columns(2)
        with col1:
            st.info("🇺🇸 USA Pricing")
            st.metric("Lowest Price", final_data.get("usa_prices", {}).get("lowest", "N/A"))
            st.metric("Highest Price", final_data.get("usa_prices", {}).get("highest", "N/A"))
        with col2:
            st.info("🇨🇦 Canada Pricing")
            st.metric("Lowest Price", final_data.get("canada_prices", {}).get("lowest", "N/A"))
            st.metric("Highest Price", final_data.get("canada_prices", {}).get("highest", "N/A"))

        st.markdown(f"**UPC:** `{final_data.get('upc', 'Not found')}`")
        
        st.markdown("### Short Description")
        st.markdown(final_data.get("short_description", ""))

        st.markdown("### Full Description")
        st.markdown(final_data.get("description", ""))

        st.markdown("### How to Use")
        st.markdown(final_data.get("how_to_use", ""))

        st.markdown("### Key Ingredients")
        st.warning(final_data.get("ingredients", ""))

        # Step 4: Save to Hugging Face
        save_to_huggingface(product_name, final_data)

    elif final_data and "error" in final_data:
        st.error(f"An error occurred: {final_data['error']}")
    else:
        st.error("The process failed to generate data. Please try again.")

elif submit_button:
    st.warning("Please fill in both Product Name and Primary Keywords.")
