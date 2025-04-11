import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import openai
import pinecone
import re
from dotenv import load_dotenv
import time

load_dotenv()

class TrendScraper:
    def __init__(self):
        self.base_url = "https://www.trendhunter.com"
        self.openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Initialize Pinecones
        pinecone.init()
        
        # Connect directly to the index using the host
        self.index = pinecone.Index(os.getenv("PINECONE_INDEX_NAME"))

    def get_article_links(self):
        response = requests.get(self.base_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        links = soup.select("a.tha__relArticle")
        return [link.get('href') for link in links if link.get('href')]

    def extract_article_data(self, url):
        full_url = url if url.startswith('http') else f"{self.base_url}{url}"
        response = requests.get(full_url)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract date
        date_div = soup.select_one("div.tha__references div")
        date_text = date_div.text if date_div else ""
        # Remove author name and clean date
        date_text = re.sub(r'^[^—]*\s—\s', '', date_text).strip()
        date_text = re.sub(r'\s—[^—]*$', '', date_text).strip()
        try:
            date = datetime.strptime(date_text, '%B %d, %Y')
        except ValueError:
            date = datetime.now()

        # Extract content
        content_div = soup.select_one("div.tha__articleText")
        content = content_div.text.strip() if content_div else ""

        # Extract themes
        themes_div = soup.select(".tpt__aSecCont .tpt__aItemText")
        themes = [theme.text.strip() for theme in themes_div]

        return {
            'date': date,
            'content': content,
            'themes': themes,
            'url': full_url
        }

    def generate_embedding(self, text):
        response = self.openai_client.embeddings.create(
            model="text-embedding-3-large",
            input=text
        )
        return response.data[0].embedding

    def process_article(self, article_data):
        # Combine content and themes for embedding
        content = article_data['content']
        
        # Remove the last line if it starts with "Image Credit: "
        cleaned_content = content
        content_lines = cleaned_content.split('\n\n')
        if content_lines and content_lines[-1].strip().startswith("Image Credit: "):
            cleaned_content = '\n'.join(content_lines[:-1])
        
        # Clean themes by removing numbering using regex
        cleaned_themes = []
        for theme in article_data['themes']:
            # Remove numbering like "1.", "1a.", "2b.", etc.
            cleaned_theme = re.sub(r'^\d*\.\s', '', theme.strip())
            cleaned_themes.append(cleaned_theme)
        
        combined_text = f"{content} {' '.join(cleaned_themes)}"
        embedding = self.generate_embedding(combined_text)

        # Prepare metadata
        metadata = {
            'date': article_data['date'].isoformat(),
            'content': cleaned_content,
            'themes': cleaned_themes,
            'url': article_data['url']
        }

        # Upsert to Pinecone
        self.index.upsert(
            vectors=[{
                'id': str(hash(article_data['url'])),
                'values': embedding,
                'metadata': metadata
            }]
        )

    def run(self):
        print("Starting trend scraping...")
        links = self.get_article_links()
        
        for link in links:
            try:
                article_data = self.extract_article_data(link)
                self.process_article(article_data)
                print(f"Processed article: {link}")
            except Exception as e:
                print(f"Error processing article {link}: {str(e)}")

        print("Trend scraping completed!")

if __name__ == "__main__":
    scraper = TrendScraper()
    scraper.run() 