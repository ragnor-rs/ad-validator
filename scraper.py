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

        # self.detected_lang = 'en'

    # def _detect_language(self, text):
    #     """Detect the language of the given text using OpenAI."""
    #     try:
    #         response = self.openai_client.chat.completions.create(
    #             model="gpt-4-turbo-preview",
    #             messages=[
    #                 {"role": "system", "content": "You are a language detection expert. Respond with only the full name of the language in English (e.g., 'English', 'Russian', 'Spanish')."},
    #                 {"role": "user", "content": f"Detect the language of this text and respond with only the full name of the language in English: {text[:1000]}"}
    #             ],
    #             temperature=0,
    #             max_tokens=20
    #         )
    #         return response.choices[0].message.content.strip()
    #     except Exception as e:
    #         print(f"Language detection error: {str(e)}")
    #         return 'English'
        
    def save_article(self, content, current_chapter, current_article, articles):
        if not content:
            return articles
        
        # if len(articles) == 0:
        #     self.detected_lang = self._detect_language(content)
        #     print(f"Detected language: {self.detected_lang}")

        article = {
            'chapter': current_chapter,
            'article': current_article,
            'content': content
        }
        articles.append(article)
        
        return articles

    def generate_criterion_id(self, criterion):
        # Combine all fields into a single string
        combined = f"{criterion['chapter_number']}_{criterion['article_number']}_{criterion['clause_number']}"
        return combined
    
        # # Generate a hash of the combined string
        # hash_object = hashlib.md5(combined.encode())
        # return f"criterion_{hash_object.hexdigest()[:12]}"  # Use first 12 chars of hash

    def generate_embedding(self, criterion):
        # Combine chapter title, article title, and content
        combined_text = f"{criterion['chapter_title']}\n{criterion['article_title']}\n{criterion['description']}"
        
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
        """Extract clauses from text and format them as criteria.
        Each clause starts with a number and a dot (e.g., "1.").
        Subitems within a clause are included as part of the clause."""
        
        # Split text into lines and remove empty lines
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        clauses = []
        current_clause = []
        current_clause_number = None
        
        for line in lines:
            # Check if line starts with a number and a dot (e.g., "1.", "2.")
            clause_match = re.match(r'^((\d+\.)+)\s*(.*)', line)
            if clause_match:
                # If we have a previous clause, add it to the list
                if current_clause:
                    clause_text = '\n'.join(current_clause)
                    clauses.append({
                        'description': clause_text,
                        'clause_number': current_clause_number if current_clause_number else '1',
                        'chapter_number': chapter_number,
                        'chapter_title': chapter_title,
                        'article_number': article_number,
                        'article_title': article_title
                    })
                # Start a new clause
                current_clause_number = clause_match.group(1).strip('.')
                current_clause = [clause_match.group(3)]  # Start with the text after the number
            else:
                # Add line to current clause
                current_clause.append(line)
        
        # Add the last clause if exists
        if current_clause:
            clause_text = '\n'.join(current_clause)
            clauses.append({
                'description': clause_text,
                'clause_number': current_clause_number if current_clause_number else '1',
                'chapter_number': chapter_number,
                'chapter_title': chapter_title,
                'article_number': article_number,
                'article_title': article_title
            })
        
        return clauses

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
                            'article_title': criterion['article_title'],
                            'clause_number': criterion['clause_number']
                        }
                    })

                    print(f"Extracted criterion {id}")
                    
                # Insert into Pinecone
                self.index.upsert(
                    vectors=vectors
                )

                print(f"Processed article {article['article']['number']} ({i+1}/{len(articles)}) from chapter {article['chapter']['number']} ({len(vectors)} criteria found)")
                
                # Small delay to avoid rate limits
                time.sleep(0.1)
                
            except Exception as e:
                print(f"Error processing article {article['article']['number']}: {str(e)}")

        print("Law scraping completed!")

if __name__ == "__main__":
    scraper = LawScraper()
    scraper.run() 