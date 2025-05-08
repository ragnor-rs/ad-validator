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

        self.detected_lang = 'en'

    def _detect_language(self, text):
        """Detect the language of the given text using OpenAI."""
        try:
            response = self.openai_client.chat.completions.create(
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
        
    def save_article(self, content, current_chapter, current_article, articles):
        if not content:
            return articles
        
        if len(articles) == 0:
            self.detected_lang = self._detect_language(content)
            print(f"Detected language: {self.detected_lang}")

        article = {
            'chapter': current_chapter,
            'article': current_article,
            'content': content
        }
        articles.append(article)
        
        return articles

    def generate_criterion_id(self, criterion):
        # Combine all fields into a single string
        combined = f"{criterion['chapter_number']}_{criterion['chapter_title']}_{criterion['article_number']}_{criterion['article_title']}_{criterion['description']}"
        
        # Generate a hash of the combined string
        hash_object = hashlib.md5(combined.encode())
        return f"criterion_{hash_object.hexdigest()[:12]}"  # Use first 12 chars of hash

    def generate_embedding(self, criterion):
        # Combine chapter title, article title, and content
        chapter_title = f"{criterion['chapter_title']}"
        article_title = f"{criterion['article_title']}"
        combined_text = f"{chapter_title}\n{article_title}\n{criterion['description']}"
        
        response = self.openai_client.embeddings.create(
            model="text-embedding-3-large",
            input=combined_text
        )
        return response.data[0].embedding

    def split_into_articles(self, text):
        # Split text into sections by double newlines
        sections = [s.strip() for s in text.split('\n\n') if s.strip()]
        articles = []
        current_chapter = None
        current_article = None
        current_content = ""

        for section in sections:
            # Check for chapter header
            chapter_match = re.match(r'Глава\s+((\d\.{0,1})+)\s+(.*)', section)
            if chapter_match:
                # Save previous article if exists
                if current_article and current_content:
                    articles = self.save_article(current_content, current_chapter, current_article, articles)
                
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
                    articles = self.save_article(current_content, current_chapter, current_article, articles)
                
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
            articles = self.save_article(current_content, current_chapter, current_article, articles)

        return articles
    
    def extract_criteria_from_text(self, text, chapter_title, article_title, chapter_number, article_number):
        system_prompt = f""""You are an expert in advertising law who extracts specific evaluation criteria from legal texts. You give criteria description in {self.detected_lang}."""

        user_prompt = f"""Law topic: {chapter_title}
Law subtopic: {article_title}
Law text:
{text}

Provide a clear, concise description of the criterion, one per line.

For example:
Ad must not overstate the benefits of gambling.
Medicine ad must mention side effects and contraindications.
Ad must not contain any inappropriate words."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = self.openai_client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=messages,
            temperature=0.3,
            max_tokens=1000
        )
        criteria_text = response.choices[0].message.content.strip()
        
        try:
            criteria = []
            
            # Split by newlines and process each line
            for line in criteria_text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                criteria.append({
                    "description": line,
                    "chapter_title": chapter_title,
                    "article_title": article_title,
                    "chapter_number": chapter_number,
                    "article_number": article_number
                })
            
            return criteria
        except Exception as e:
            print(f"Error parsing criteria from article {article_title}: {str(e)}")
            return []

    def run(self):
        print("Starting law scraping...")
        
        # Read law.txt
        with open('law.txt', 'r', encoding='utf-8') as file:
            content = file.read()

        # Split into articles
        articles = self.split_into_articles(content)
        print(f"Split content into {len(articles)} articles")

        # Process each article
        for i, article in enumerate(articles):
            try:
                # Extract criteria from the article
                criteria = self.extract_criteria_from_text(
                    article['content'],
                    article['chapter']['title'],
                    article['article']['title'],
                    article['chapter']['number'],
                    article['article']['number']
                )
            
                vectors = []

                for criterion in criteria:                    
                    # Generate unique ID based on criteria content
                    id = self.generate_criterion_id(criterion)

                    # Generate embedding
                    embedding = self.generate_embedding(criterion)

                    vectors.append({
                        'id': id,
                        'values': embedding,
                        'metadata': {
                            'description': criterion['description'],
                            'chapter_number': criterion['chapter_number'],
                            'chapter_title': criterion['chapter_title'],
                            'article_number': criterion['article_number'],
                            'article_title': criterion['article_title']
                        }
                    })
                    
                # Insert into Pinecone
                self.index.upsert(
                    vectors=vectors
                )

                print(f"Processed article {article['article']['number']} ({i+1}/{len(articles)}) from chapter {article['chapter']['number']} ({len(vectors)} criteria found)")
                
                # Small delay to avoid rate limits
                time.sleep(0.5)
                
            except Exception as e:
                print(f"Error processing article {article['article']['number']}: {str(e)}")

        print("Law scraping completed!")

if __name__ == "__main__":
    scraper = LawScraper()
    scraper.run() 