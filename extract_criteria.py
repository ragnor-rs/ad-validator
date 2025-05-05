import os
import openai
import pinecone
from dotenv import load_dotenv
import json
import random

load_dotenv()

class CriteriaExtractor:
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Initialize Pinecone
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
        
    def extract_criteria_from_text(self, text, chapter_title, article_title, chapter_number, article_number, entry_id):
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
        
        try:
            # Parse the response text
            criteria_text = response.choices[0].message.content.strip()
            criteria = []
            
            # Split by newlines and process each line
            for line in criteria_text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                criteria.append({
                    "description": line,
                    "from": {
                        "chapter_title": chapter_title,
                        "article_title": article_title,
                        "chapter_number": chapter_number,
                        "article_number": article_number,
                        "entry_id": entry_id
                    }
                })
            
            return criteria
        except Exception as e:
            print(f"Error parsing criteria from article {article_title}: {str(e)}")
            return []
    
    def process_index(self):
        """Process all entries in the Pinecone index and extract criteria."""
        # Create a randomized dummy vector
        dummy_vector = [random.uniform(-1, 1) for _ in range(3072)]  # Dimension of text-embedding-3-large
        
        # Get all entries (adjust top_k as needed)
        results = self.index.query(
            vector=dummy_vector,
            top_k=3,  # Adjust based on your index size
            include_metadata=True
        )
        
        print(f"Processing {len(results.matches)} entries from the index...")
        
        # Detect language from the first article
        if results.matches:
            first_article = results.matches[0].metadata.get('content', '')
            if first_article:
                self.detected_lang = self._detect_language(first_article)
                print(f"Detected language: {self.detected_lang}")
        
        # Track progress
        total_entries = len(results.matches)
        processed = 0
        
        all_criteria = []
        
        for match in results.matches:
            metadata = match.metadata
            entry_id = match.id  # Get the entry ID
            
            # Skip entries that don't have the expected structure
            if not all(key in metadata for key in ['chapter_title', 'article_title', 'content']):
                continue
                
            processed += 1
            print(f"Processing: Chapter {metadata['chapter_number']} - Article {metadata['article_number']} ({processed}/{total_entries})")
            
            # Extract criteria from this entry
            criteria = self.extract_criteria_from_text(
                metadata['content'],
                metadata['chapter_title'],
                metadata['article_title'],
                metadata['chapter_number'],
                metadata['article_number'],
                entry_id
            )
            
            all_criteria.extend(criteria)
            
        return all_criteria
    
    def save_criteria(self, criteria, output_file="ad_evaluation_criteria.txt"):
        """Save the extracted criteria to a JSON file."""
        # Create the top-level object with the criteria array
        output_data = {
            "criteria": criteria,
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        print(f"Saved {len(criteria)} criteria to {output_file}")
    
    def run(self):
        """Run the extraction process."""
        print("Starting criteria extraction...")
        criteria = self.process_index()
        self.save_criteria(criteria, "ad_evaluation_criteria.raw.txt")
        print("Extraction complete!")

if __name__ == "__main__":
    extractor = CriteriaExtractor()
    extractor.run() 