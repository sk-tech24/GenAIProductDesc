# 📦 Streamlit Product Info Scraper App (SEO-Optimized + Humanized)

import streamlit as st
import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import os
import re
import aiohttp
from datasets import Dataset, concatenate_datasets, load_dataset
import google.generativeai as genai

# --- Configuration ---
# Make sure to set your GEMINI_API_KEY as an environment variable
# For Streamlit Community Cloud, you can set this in the app's secrets.
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

HF_DATASET_NAME = "Jay-Rajput/product_desc"

# --- Core Functions ---

# 🚀 Setup Playwright (runs only once)
@st.cache_resource
def install_playwright():
    os.system("playwright install chromium")
    return True

install_playwright()

# 🔍 Google Search using Playwright
async def search_product_links(query, max_links=5):
    """Searches Google for a product and returns the top relevant links."""
    links = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(f"https://www.google.com/search?q={query.replace(' ', '+')}&tbm=shop")
            await page.wait_for_load_state('networkidle', timeout=5000)

            # Select links specifically from Google Shopping results for higher relevance
            locators = page.locator('a')
            for i in range(await locators.count()):
                href = await locators.nth(i).get_attribute('href')
                if href and href.startswith('/url?q='):
                    clean_link = href.split('/url?q=')[1].split('&')[0]
                    # Filter out irrelevant domains
                    if "google.com" not in clean_link and not any(domain in clean_link for domain in ["youtube.com", "facebook.com", "instagram.com", "pinterest.com"]):
                        links.append(clean_link)
                if len(links) >= max_links:
                    break
            await browser.close()
    except Exception as e:
        st.error(f"Error during Google search: {e}")
    return links

# 🕷️ Scrape Product Info from a URL
async def extract_product_info(session, url):
    """Extracts product title and description from a given URL."""
    try:
        async with session.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}, timeout=10) as response:
            if response.status != 200:
                return {"url": url, "error": f"Failed with status code {response.status}"}
            
            text = await response.text()
            soup = BeautifulSoup(text, "html.parser")
            
            title = soup.title.text.strip() if soup.title else ""
            
            # Find all paragraphs and join them to form a comprehensive description
            paragraphs = soup.find_all("p")
            long_desc = " ".join([p.text.strip() for p in paragraphs if len(p.text.strip()) > 50])
            long_desc = re.sub(r'\s+', ' ', long_desc) # Clean up extra whitespace

            # Basic check to see if it's a valid product page
            if len(long_desc) < 150:
                return {"url": url, "error": "Content too short, likely not a product page."}

            return {
                "url": url,
                "title": title,
                "description": long_desc
            }
    except Exception as e:
        return {"url": url, "error": str(e)}

# 🧠✨ Generate and Humanize Description with Gemini
async def generate_and_humanize_description(product_name, descriptions):
    """
    Calls the Gemini API with a consolidated prompt to format, aggregate,
    and humanize the scraped product descriptions in a single step.
    """
    # Combine all scraped descriptions into one block of text for the prompt
    combined_texts = "\n\n---\n\n".join([f"Source Document from a website:\n{desc}" for desc in descriptions if desc])

    prompt = f"""
    **Instructions:**

    1.  **Analyze and Synthesize:** Read all the source documents to understand the product's key features, benefits, and how it's used. Synthesize this information into a single, coherent description.
    2.  **Strict Formatting:** You MUST format the output in Markdown exactly as follows. Do not add any other headers, notes, or introductory text.

    ---
    ### Short Description:
    [A concise, captivating overview in 2-3 sentences.]

    ### Description:
    [This is the main body. Combine all key features, benefits, and a concluding thought into a single, flowing text block. Do NOT use sub-headers like 'Key Features' or 'Conclusion' within this section.]

    ### How to Use:
    [Provide clear, step-by-step instructions for using the product. If this information is not available in the source documents, don't add it."]
    ---

    **Source Documents to Analyze:**

    {combined_texts}
    
    Follow the Instructions provided above and Rewrite the following description to make it sound as if it were written by a human, not an AI. Use a varied sentence structure, a natural and slightly more personal tone, and incorporate rhetorical devices or asides where appropriate. The goal is to significantly increase the text's "perplexity" and "burstiness" to make it undetectable by AI content detectors, while strictly preserving the original meaning and information.
    """

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        # Use the asynchronous version of the generate_content method
        response = await model.generate_content_async(prompt)
        return response.text
    except Exception as e:
        st.error(f"Error calling Gemini API: {e}")
        return f"[ERROR]: Could not generate description due to an API error. {str(e)}"

# 💾 Save to Hugging Face Dataset
def save_to_huggingface_dataset(product_name, description):
    """Saves the generated product description to a Hugging Face dataset."""
    if "[ERROR]" in description:
        st.warning("Skipping save to Hugging Face due to generation error.")
        return

    try:
        new_data = Dataset.from_dict({
            "product_name": [product_name],
            "description": [description]
        })
        
        # Try to load the existing dataset and append new data
        try:
            existing_dataset = load_dataset(HF_DATASET_NAME, split="train")
            combined_dataset = concatenate_datasets([existing_dataset, new_data])
        except Exception:
            # If dataset doesn't exist, the new data is the dataset
            st.info("Creating new Hugging Face dataset.")
            combined_dataset = new_data

        # Push the updated dataset to the hub
        combined_dataset.push_to_hub(HF_DATASET_NAME, private=False)
        st.success(f"Successfully saved to Hugging Face Dataset: {HF_DATASET_NAME}")
    except Exception as e:
        st.error(f"Could not save to Hugging Face Hub: {e}")


# --- Streamlit UI ---

st.set_page_config(page_title="ProductSense", page_icon="🛍️", layout="wide")
st.title("🛍️ ProductSense: AI-Powered Product Descriptions")
st.markdown("Enter a product name to scrape the web and generate a human-like description.")

if "submitted" not in st.session_state:
    st.session_state.submitted = False

with st.form("product_form"):
    product_name = st.text_input("Enter a specific product name (e.g., 'Sony WH-1000XM5 Wireless Headphones'):", key="product_input")
    submitted = st.form_submit_button("✨ Generate Description")

if submitted and product_name:
    st.session_state.submitted = True
    st.session_state.product_name = product_name
else:
    st.session_state.submitted = False

if st.session_state.submitted and st.session_state.get("product_name"):
    
    async def main_flow():
        product_to_process = st.session_state.product_name
        final_description = ""
        scraped_metadata = []

        with st.spinner(f"Step 1/3: Searching Google for '{product_to_process}'..."):
            urls = await search_product_links(product_to_process, max_links=5)
            if not urls:
                st.error("Could not find any relevant links. Please try a more specific product name.")
                return

        with st.spinner(f"Step 2/3: Scraping {len(urls)} websites for product info..."):
            descriptions = []
            async with aiohttp.ClientSession() as session:
                scrape_tasks = [extract_product_info(session, url) for url in urls]
                scraped_results = await asyncio.gather(*scrape_tasks)
                
                for result in scraped_results:
                    if 'error' not in result:
                        descriptions.append(result['description'])
                    scraped_metadata.append(result)
        
        if not descriptions:
            st.error("Scraping failed for all sources. Could not gather enough information to write a description.")
            # Optionally display errors from metadata here
            return

        with st.spinner("Step 3/3: AI is writing and humanizing the description..."):
            final_description = await generate_and_humanize_description(product_to_process, descriptions)
        
        # Display final output
        st.subheader("📝 Final Product Description")
        st.markdown(final_description)

        # Save to Hugging Face
        save_to_huggingface_dataset(product_to_process, final_description)
        
        # Display sources for transparency
        with st.expander("View Scraped Sources"):
            for result in scraped_metadata:
                url = result.get("url", "")
                title = result.get("title", "").strip()
                error = result.get("error")
                if error:
                    st.warning(f"⚠️ **{url}** — Error: {error}")
                else:
                    st.success(f"✅ **{title}** — Successfully scraped from [{url}]({url})")

    # Run the main asynchronous process
    asyncio.run(main_flow())
    st.session_state.submitted = False # Reset state after completion

