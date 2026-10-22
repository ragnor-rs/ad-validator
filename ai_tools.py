from config import EMBEDDING_MODEL, REASONING_MODEL

def detect_language(text, openai_client):
    """Detect the language of the given text using OpenAI."""
    try:
        response = openai_client.chat.completions.create(
            model=REASONING_MODEL,
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
        model=EMBEDDING_MODEL,
        input=text
    )
    return response.data[0].embedding
