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

def split_into_sentences(text):
    if not text.strip():
        return []
        
    sentences = []
    current = []
    paren_level = 0
    i = 0
    
    while i < len(text):
        char = text[i]
        current.append(char)
        
        # Track parentheses level
        if char == '(':
            paren_level += 1
        elif char == ')':
            if paren_level > 0:  # Only decrease if we have a matching opening parenthesis
                paren_level -= 1
            
        # Check for sentence endings
        if char in '.!?' and paren_level == 0:
            # Look ahead to avoid splitting on abbreviations, numbers, or numbered items
            if i + 1 < len(text):
                next_char = text[i + 1]
                # Don't split if:
                # 1. Next char is a digit (number)
                # 2. Next char is a lowercase letter (abbreviation)
                # 3. Current char is part of a numbered item (look back for digits)
                is_numbered_item = False
                if char == '.':
                    # Look back for digits
                    j = i - 1
                    while j >= 0 and text[j].isdigit():
                        j -= 1
                    if j < i - 1:  # Found digits before the dot
                        is_numbered_item = True
                
                if not (next_char.isdigit() or next_char.islower() or is_numbered_item):
                    sentence = ''.join(current).strip()
                    if sentence:  # Only add non-empty sentences
                        sentences.append(sentence)
                    current = []
            else:
                sentence = ''.join(current).strip()
                if sentence:  # Only add non-empty sentences
                    sentences.append(sentence)
                current = []
                
        i += 1
    
    # Add any remaining content
    if current:
        sentence = ''.join(current).strip()
        if sentence:  # Only add non-empty sentences
            sentences.append(sentence)
    
    return sentences

def save_chunk(content, current_chapter, current_article, chunks, max_content_length=4000):
    if not content:
        return chunks
    # Split content into sentences if it's too long
    if len(content) > max_content_length:
        # Split content into sentences
        sentences = split_into_sentences(content)
        
        current_chunk_content = []
        current_length = 0
        
        for sentence in sentences:
            sentence_length = len(sentence)
            # If adding this sentence would exceed max length, save current chunk
            if current_length + sentence_length > max_content_length and current_chunk_content:
                chunk = {
                    'chapter': current_chapter,
                    'article': current_article,
                    'content': ' '.join(current_chunk_content)
                }
                chunks.append(chunk)
                current_chunk_content = []
                current_length = 0
            
            current_chunk_content.append(sentence)
            current_length += sentence_length
        
        # Save any remaining content
        if current_chunk_content:
            chunk = {
                'chapter': current_chapter,
                'article': current_article,
                'content': ' '.join(current_chunk_content)
            }
            chunks.append(chunk)
    else:
        # Content fits in one chunk
        chunk = {
            'chapter': current_chapter,
            'article': current_article,
            'content': content
        }
        chunks.append(chunk)
    
    return chunks

class LawScraper:
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Initialize Pinecone with the new syntax
        pc = pinecone.Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        self.index = pc.Index(os.getenv("PINECONE_INDEX_NAME"))

    def generate_chunk_id(self, chunk):
        # Combine all fields into a single string
        combined = f"{chunk['chapter']['number']}_{chunk['chapter']['title']}_{chunk['article']['number']}_{chunk['article']['title']}_{chunk['content']}"
        
        # Generate a hash of the combined string
        hash_object = hashlib.md5(combined.encode())
        return f"law_{hash_object.hexdigest()[:12]}"  # Use first 12 chars of hash

    def generate_embedding(self, chunk):
        # Combine chapter title, article title, and content
        chapter_title = f"{chunk['chapter']['title']}"
        article_title = f"{chunk['article']['title']}"
        combined_text = f"{chapter_title}\n{article_title}\n{chunk['content']}"
        
        response = self.openai_client.embeddings.create(
            model="text-embedding-3-large",
            input=combined_text
        )
        return response.data[0].embedding

    def split_into_chunks(self, text, max_content_length=4000):
        # Split text into sections by double newlines
        sections = [s.strip() for s in text.split('\n\n') if s.strip()]
        chunks = []
        current_chapter = None
        current_article = None
        current_content = ""

        for section in sections:
            # Check for chapter header
            chapter_match = re.match(r'Глава\s+((\d\.{0,1})+)\s+(.*)', section)
            if chapter_match:
                # Save previous article if exists
                if current_article and current_content:
                    chunks = save_chunk(current_content, current_chapter, current_article, chunks, max_content_length)
                
                # Start new chapter
                current_chapter = {
                    'number': chapter_match.group(1).rstrip('.'),
                    'title': chapter_match.group(3).strip()
                }
                current_article = None
                current_content = ""
                continue

            # Check for article header
            article_match = re.match(r'Статья\s+((\d\.{0,1})+)\s+(.*)', section)
            if article_match:
                # Save previous article if exists
                if current_article and current_content:
                    chunks = save_chunk(current_content, current_chapter, current_article, chunks, max_content_length)
                
                # Start new article
                current_article = {
                    'number': article_match.group(1).rstrip('.'),
                    'title': article_match.group(3).strip()
                }
                current_content = ""
                # Add the rest of the section after the article title as content
                content_part = section[article_match.end():].strip()
                if content_part:
                    current_content = content_part
                continue

            # If we have an article, this is its content
            if current_article:
                if current_content:
                    current_content += " " + section
                else:
                    current_content = section

        # Save the last article if exists
        if current_article and current_content:
            chunks = save_chunk(current_content, current_chapter, current_article, chunks, max_content_length)

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
                            'content': chunk['content'],
                            'chapter_number': chunk['chapter']['number'],
                            'chapter_title': chunk['chapter']['title'],
                            'article_number': chunk['article']['number'],
                            'article_title': chunk['article']['title'],
                            'timestamp': datetime.now().isoformat()
                        }
                    }]
                )
                print(f"Processed chunk {i+1}/{len(chunks)} with ID: {chunk_id} (Chapter {chunk['chapter']['number']}, Article {chunk['article']['number']})")
                
                # Small delay to avoid rate limits
                time.sleep(0.5)
                
            except Exception as e:
                print(f"Error processing chunk {i}: {str(e)}")

        print("Law scraping completed!")

if __name__ == "__main__":
    scraper = LawScraper()
    scraper.run() 