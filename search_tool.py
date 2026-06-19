import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def search_web(query: str) -> dict:
    """Calls Gemini with the Google Search grounding tool for `query`.
    Returns the response text plus grounding metadata (search queries used + sources)."""
    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=query,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        ),
    )

    grounding_metadata = response.candidates[0].grounding_metadata

    return {
        "text": response.text,
        "search_queries": grounding_metadata.web_search_queries,
        "sources": [
            chunk.web.uri
            for chunk in grounding_metadata.grounding_chunks
        ] if grounding_metadata.grounding_chunks else [],
    }


if __name__ == "__main__":
    result = search_web("current wheat prices Qatar")
    print(result)
