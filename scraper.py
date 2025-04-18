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
        # Split text into sections by double newlines
        sections = [s.strip() for s in text.split('\n\n') if s.strip()]
        chunks = []
        current_chapter = None
        current_article = None
        current_content = []

        print(f"Total sections found: {len(sections)}")
        
        for i, section in enumerate(sections):
            print(f"\nProcessing section {i+1}:")
            print(f"Section preview: {section[:100]}...")

            # Check for chapter header
            chapter_match = re.match(r'Глава\s+(\d+)[\.\s]+(.+)', section)
            if chapter_match:
                print(f"Found chapter: {chapter_match.group(1)} - {chapter_match.group(2)}")
                # Save previous article if exists
                if current_article and current_content:
                    chunk = {
                        'chapter': current_chapter,
                        'article': current_article,
                        'content': '\n\n'.join(current_content)
                    }
                    chunks.append(chunk)
                    print(f"Saved chunk for article {current_article['number']}")
                
                # Start new chapter
                current_chapter = {
                    'number': chapter_match.group(1),
                    'title': chapter_match.group(2).strip()
                }
                current_article = None
                current_content = []
                continue

            # Check for article header
            article_match = re.match(r'Статья\s+(\d+)[\.\s]+(.+)', section)
            if article_match:
                print(f"Found article: {article_match.group(1)} - {article_match.group(2)}")
                # Save previous article if exists
                if current_article and current_content:
                    chunk = {
                        'chapter': current_chapter,
                        'article': current_article,
                        'content': '\n\n'.join(current_content)
                    }
                    chunks.append(chunk)
                    print(f"Saved chunk for article {current_article['number']}")
                
                # Start new article
                current_article = {
                    'number': article_match.group(1),
                    'title': article_match.group(2).strip()
                }
                current_content = []
                # Add the rest of the section after the article title as content
                content_part = section[article_match.end():].strip()
                if content_part:
                    current_content.append(content_part)
                continue

            # If we have an article, this is its content
            if current_article:
                current_content.append(section)
                print(f"Added content to article {current_article['number']}")

        # Save the last article if exists
        if current_article and current_content:
            chunk = {
                'chapter': current_chapter,
                'article': current_article,
                'content': '\n\n'.join(current_content)
            }
            chunks.append(chunk)
            print(f"Saved final chunk for article {current_article['number']}")

        print(f"\nFinal chunks count: {len(chunks)}")
        for i, chunk in enumerate(chunks):
            print(f"\nChunk {i+1}:")
            print(f"Chapter: {chunk['chapter']['number']} - {chunk['chapter']['title']}")
            print(f"Article: {chunk['article']['number']} - {chunk['article']['title']}")
            print(f"Content length: {len(chunk['content'])} chars")
            print(f"Content preview: {chunk['content'][:100]}...")

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
        # for i, chunk in enumerate(chunks):
        #     try:
        #         # Generate embedding
        #         embedding = self.generate_embedding(chunk)
                
        #         # Generate unique ID based on chunk content
        #         chunk_id = self.generate_chunk_id(chunk)
                
        #         # Insert into Pinecone
        #         self.index.upsert(
        #             vectors=[{
        #                 'id': chunk_id,
        #                 'values': embedding,
        #                 'metadata': {
        #                     'content': chunk,
        #                     'timestamp': datetime.now().isoformat()
        #                 }
        #             }]
        #         )
        #         print(f"Processed chunk {i+1}/{len(chunks)} with ID: {chunk_id}")
                
        #         # Small delay to avoid rate limits
        #         time.sleep(0.5)
                
        #     except Exception as e:
        #         print(f"Error processing chunk {i}: {str(e)}")

        print("Law scraping completed!")

if __name__ == "__main__":
    scraper = LawScraper()
    scraper.run() 