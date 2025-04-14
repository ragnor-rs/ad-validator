import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import openai
import pinecone
import re
from dotenv import load_dotenv
import time
import hashlib

load_dotenv()

class LawScraper:
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Initialize Pinecone with the new syntax
        pc = pinecone.Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        self.index = pc.Index(os.getenv("PINECONE_INDEX_NAME"))

    def generate_chunk_id(self, chunk):
        # Generate a hash of the chunk content
        hash_object = hashlib.md5(chunk.encode())
        return f"law_{hash_object.hexdigest()[:12]}"  # Use first 12 chars of hash

    def generate_embedding(self, text):
        response = self.openai_client.embeddings.create(
            model="text-embedding-3-large",
            input=text
        )
        return response.data[0].embedding

    def split_into_chunks(self, text, chunk_size=4000):
        sections = re.split(r'\n\n', text)
        chunks = []
        current_chunk = []
        current_size = 0

        for section in sections:
            section_size = len(section)
            
            # If section is larger than chunk_size, split it into sentences
            if section_size > chunk_size:
                sentences = re.split(r'(?<=[.!?])\s+', section)
                temp_chunk = []
                temp_size = 0
                
                for sentence in sentences:
                    sentence_size = len(sentence)
                    if temp_size + sentence_size > chunk_size and temp_chunk:
                        chunks.append(' '.join(temp_chunk))
                        temp_chunk = [sentence]
                        temp_size = sentence_size
                    else:
                        temp_chunk.append(sentence)
                        temp_size += sentence_size
                
                if temp_chunk:
                    chunks.append(' '.join(temp_chunk))
                continue
            
            # Handle normal-sized sections
            if current_size + section_size > chunk_size and current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = [section]
                current_size = section_size
            else:
                current_chunk.append(section)
                current_size += section_size

        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks

    def run(self):
        print("Starting law scraping...")
        
        # Read law.txt
        with open('law.txt', 'r', encoding='utf-8') as file:
            content = file.read()

        # Split into chunks
        chunks = self.split_into_chunks(content)
        print(f"Split content into {len(chunks)} chunks")

        # Process each chunk
        for i, chunk in enumerate(chunks):
            try:
                # Generate embedding
                embedding = self.generate_embedding(chunk)
                
                # Generate unique ID based on chunk content
                chunk_id = self.generate_chunk_id(chunk)
                
                # Insert into Pinecone
                self.index.upsert(
                    vectors=[{
                        'id': chunk_id,
                        'values': embedding,
                        'metadata': {
                            'content': chunk,
                            'timestamp': datetime.now().isoformat()
                        }
                    }]
                )
                print(f"Processed chunk {i+1}/{len(chunks)} with ID: {chunk_id}")
                
                # Small delay to avoid rate limits
                time.sleep(0.5)
                
            except Exception as e:
                print(f"Error processing chunk {i}: {str(e)}")

        print("Law scraping completed!")

if __name__ == "__main__":
    scraper = LawScraper()
    scraper.run() 