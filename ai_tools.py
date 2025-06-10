import os
import openai

def detect_language(text, openai_client):
    """Detect the language of the given text using OpenAI."""
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": "You are a language detection expert. Respond with only the full name of the language in English (e.g., 'English', 'Russian', 'Spanish')."},
                {"role": "user", "content": f"Detect the language of this text and respond with only the full name of the language in English: {text[:1000]}"}
            ],
            temperature=0,
            max_tokens=20
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Language detection error: {str(e)}")
        return 'English'

def generate_embedding(text, openai_client):
    """Generate an embedding for the given text using OpenAI."""
    response = openai_client.embeddings.create(
        model="text-embedding-3-large",
        input=text
    )
    return response.data[0].embedding 