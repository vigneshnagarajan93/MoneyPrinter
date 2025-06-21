import re
import os
import g4f
import json
import openai
import google.generativeai as genai

from g4f.client import Client
from termcolor import colored
from dotenv import load_dotenv
from typing import Tuple, List
import httpx  # <-- you must also import this at the top


# Load environment variables
load_dotenv("../.env")

# Set environment variables
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
openai.api_key = OPENAI_API_KEY
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)


def generate_response(prompt: str, ai_model: str) -> str:
    import openai
    import os

    client = openai.OpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1"
    )

    response = client.chat.completions.create(
        model=ai_model,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content

def generate_script(topic, paragraph_number, ai_model, voice, custom_prompt=None):
    """
    Generates a script using OpenRouter (OpenAI-compatible API).
    Cleans response by extracting only main paragraph content and strips out search term JSON block.
    """
    import httpx
    system_prompt = "You are a helpful assistant who generates engaging and informative scripts for short-form videos."

    user_prompt = custom_prompt if custom_prompt else f"Explain in {paragraph_number} paragraph(s) why {topic} is trending and why Gen Z finds it interesting."

    payload = {
        "model": ai_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    response = httpx.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers)
    response.raise_for_status()

    full_text = response.json()["choices"][0]["message"]["content"]

    # Clean up common prefixes like "Script": or similar
    cleaned = re.sub(r'^["\']?script["\']?\s*:\s*', '', full_text, flags=re.IGNORECASE).strip()

    # Only keep first block of text, excluding search terms / lists
    split_markers = ["\n\n", "\n- ", "[", "```", "Search terms", "search_term", "video_name"]
    split_index = len(cleaned)
    for marker in split_markers:
        idx = cleaned.find(marker)
        if idx != -1:
            split_index = min(split_index, idx)

    cleaned_script = cleaned[:split_index].strip()

    print("\n[Full GPT Response for Debugging]\n", full_text)
    print("\n[Cleaned Script for TTS/Subtitles]\n", cleaned_script)

    return cleaned_script


def get_search_terms(video_subject: str, amount: int, script: str, ai_model: str) -> List[str]:
    """
    Generate a JSON-Array of search terms for stock videos,
    depending on the subject of a video.

    Args:
        video_subject (str): The subject of the video.
        amount (int): The amount of search terms to generate.
        script (str): The script of the video.
        ai_model (str): The AI model to use for generation.

    Returns:
        List[str]: The search terms for the video subject.
    """

    # Build prompt
    prompt = f"""
    Generate {amount} search terms for stock videos,
    depending on the subject of a video.
    Subject: {video_subject}

    The search terms are to be returned as
    a JSON-Array of strings.

    Each search term should consist of 1-3 words,
    always add the main subject of the video.
    
    YOU MUST ONLY RETURN THE JSON-ARRAY OF STRINGS.
    YOU MUST NOT RETURN ANYTHING ELSE. 
    YOU MUST NOT RETURN THE SCRIPT.
    
    The search terms must be related to the subject of the video.
    Here is an example of a JSON-Array of strings:
    ["search term 1", "search term 2", "search term 3"]

    For context, here is the full text:
    {script}
    """

    # Generate search terms
    response = generate_response(prompt, ai_model)
    print(response)

    # Parse response into a list of search terms
    search_terms = []
    
    try:
        search_terms = json.loads(response)
        if not isinstance(search_terms, list) or not all(isinstance(term, str) for term in search_terms):
            raise ValueError("Response is not a list of strings.")

    except (json.JSONDecodeError, ValueError):
        # Get everything between the first and last square brackets
        response = response[response.find("[") + 1:response.rfind("]")]

        print(colored("[*] GPT returned an unformatted response. Attempting to clean...", "yellow"))

        # Attempt to extract list-like string and convert to list
        match = re.search(r'\["(?:[^"\\]|\\.)*"(?:,\s*"[^"\\]*")*\]', response)
        print(match.group())
        if match:
            try:
                search_terms = json.loads(match.group())
            except json.JSONDecodeError:
                print(colored("[-] Could not parse response.", "red"))
                return []


    # Let user know
    print(colored(f"\nGenerated {len(search_terms)} search terms: {', '.join(search_terms)}", "cyan"))

    # Return search terms
    return search_terms


def generate_metadata(video_subject: str, script: str, ai_model: str) -> Tuple[str, str, List[str]]:  
    """  
    Generate metadata for a YouTube video, including the title, description, and keywords.  
  
    Args:  
        video_subject (str): The subject of the video.  
        script (str): The script of the video.  
        ai_model (str): The AI model to use for generation.  
  
    Returns:  
        Tuple[str, str, List[str]]: The title, description, and keywords for the video.  
    """  
  
    # Build prompt for title  
    title_prompt = f"""  
    Generate a catchy and SEO-friendly title for a YouTube shorts video about {video_subject}.  
    """  
  
    # Generate title  
    title = generate_response(title_prompt, ai_model).strip()  
    
    # Build prompt for description  
    description_prompt = f"""  
    Write a brief and engaging description for a YouTube shorts video about {video_subject}.  
    The video is based on the following script:  
    {script}  
    """  
  
    # Generate description  
    description = generate_response(description_prompt, ai_model).strip()  
  
    # Generate keywords  
    keywords = get_search_terms(video_subject, 6, script, ai_model)  

    return title, description, keywords  
