import os
import requests
from dotenv import load_dotenv

load_dotenv()


def list_gemini_models():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: GEMINI_API_KEY not found in .env")
        return

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"

    try:
        response = requests.get(url)
        response.raise_for_status()
        models = response.json().get("models", [])

        print("\n✅ Your API Key has access to these models:")
        print("-" * 40)
        for model in models:
            clean_name = model["name"].split("/")[-1]
            methods = ", ".join(model.get("supportedGenerationMethods", []))
            print(f"👉 gemini/{clean_name} (Supports: {methods})")
        print("-" * 40)
        print("\nCopy one of the names above into your .env as LITELLM_MODEL.")

    except Exception as e:
        print(f"❌ Failed to fetch models: {e}")


if __name__ == "__main__":
    list_gemini_models()
