# utils/gemini_wrapper.py

import os
import google.generativeai as genai

# You must set your Gemini API key in environment variable or directly in code
GENAI_API_KEY = os.getenv("GENAI_API_KEY") or "YOUR_GEMINI_API_KEY"
genai.configure(api_key=GENAI_API_KEY)

model = genai.GenerativeModel("gemini-1.5-flash")


def humanize_text_with_gemini(text: str) -> str:
    try:
        prompt = (
            f"Please humanize the following text to sound natural, engaging, and SEO-friendly, "
            f"preserving the original formatting:\n\n{text}"
        )
        response = model.generate_content(prompt)
        return response.text.strip() if response and response.text else text
    except Exception as e:
        print(f"[Gemini Error] {e}")
        return text
