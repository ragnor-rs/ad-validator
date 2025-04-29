import os
import openai
import pinecone
from dotenv import load_dotenv
import json
from collections import defaultdict
import random

load_dotenv()

class CriteriaExtractor:
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Initialize Pinecone
        pc = pinecone.Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        self.index = pc.Index(os.getenv("PINECONE_INDEX_NAME"))
        
        # Dictionary to store criteria by category
        self.criteria_by_category = defaultdict(list)
        
        # Set to track all categories used so far
        self.used_categories = {
            "General requirements",
            "Informational content",
            "Use of foreign words",
            "Pharmaceuticals",
            "Dietary supplements (nutraceuticals)",
            "Distance (remote) selling",
            "Real estate",
            "Financial products",
            "Loans and credit",
            "Forex (foreign exchange trading)",
            "Investment services using investment platforms",
            "Promotional campaigns and incentive offers",
            "Products for children",
            "Digital financial assets"
        }

        self.detected_lang = 'en'
        
    def extract_criteria_from_text(self, text, chapter_title, article_title, chapter_number, article_number, entry_id):
        system_prompt = "You are an expert legal text analyst. You will be given an article from a long law text concerning advertising regulations. Your task is to extract specific legal requirements or restrictions stated in the article and group them according to the relevant categories of advertisement content."
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "developer", "content": f"Specific topic: {article_title}"},
            {"role": "developer", "content": f"Output language: {self.detected_lang}"},
            {"role": "developer", "content": f"Article from a long law text: {text}"},
        ]
        
        if self.used_categories:
            messages.append({"role": "developer", "content": f"Use the following example categories as your primary reference (reuse them whenever possible; only create a new category only if none of these clearly apply): {', '.join(self.used_categories)}"})
            
        instructions = """Instructions:
- Use the exact wording from the article for both category and description.
- Group all extracted requirements under the most relevant existing category.
- When a requirement could fit both a specific category and General requirements, prefer the specific category.
- Only introduce a new category if none of the examples fit.
- For each applicable category, list the requirement or restriction verbatim as it appears in the article.
- If a single requirement applies to multiple categories, include it under each relevant one.
- Ignore procedural or administrative rules unless they directly affect advertising content.

Output format:
Each requirement on its own line, using the pipe symbol as separator:
category | description

Examples:
Pharmaceuticals | Advertisements must state active ingredients, contraindications, and approved dosage.
Products for children | Advertisements may not exploit children's inexperience or trust; must include parental guidance notice.
Digital financial assets | Advertisements must disclose volatility risks and platform's regulatory status."""
        
        messages.append({"role": "user", "content": instructions})  
        
        response = self.openai_client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=messages,
            temperature=0.2,
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
                
                # Split by pipe symbol
                parts = [part.strip() for part in line.split('|')]
                
                # Ensure we have at least 2 parts (category, description)
                if len(parts) >= 2:
                    category = parts[0].strip()
                    description = parts[1].strip()
                    
                    # Add the category to our set of used categories and print if it's new
                    if category not in self.used_categories:
                        print(f"New category discovered: {category}")
                    self.used_categories.add(category)
                    
                    # Always use the article title as the source
                    source = article_title
                    
                    criteria.append({
                        "category": category,
                        "description": description,
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
    
    def _detect_language(self, text):
        """Detect the language of the given text using OpenAI."""
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": "You are a language detection expert. Respond with only the ISO 639-1 language code (e.g., 'en', 'es', 'fr')."},
                    {"role": "user", "content": f"Detect the language of this text and respond with only the ISO 639-1 code: {text[:1000]}"}
                ],
                temperature=0,
                max_tokens=10
            )
            return response.choices[0].message.content.strip().lower()
        except Exception as e:
            print(f"Language detection error: {str(e)}")
            return 'en'

    def _translate_categories(self, categories, target_lang):
        """Translate categories to the target language using OpenAI."""
        if target_lang == 'en':
            return categories
            
        try:
            categories_text = "\n".join(categories)
            response = self.openai_client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": f"You are a professional translator. Translate the following categories to {target_lang}. Maintain the exact same format, one category per line."},
                    {"role": "user", "content": categories_text}
                ],
                temperature=0,
                max_tokens=1000
            )
            
            translated_categories = set()
            for line in response.choices[0].message.content.strip().split('\n'):
                translated_categories.add(line.strip())
            
            return translated_categories
        except Exception as e:
            print(f"Translation error: {str(e)}")
            return categories

    def process_index(self):
        """Process all entries in the Pinecone index and extract criteria."""
        # Create a randomized dummy vector
        dummy_vector = [random.uniform(-1, 1) for _ in range(3072)]  # Dimension of text-embedding-3-large
        
        # Get all entries (adjust top_k as needed)
        results = self.index.query(
            vector=dummy_vector,
            top_k=100,  # Adjust based on your index size
            include_metadata=True
        )
        
        print(f"Processing {len(results.matches)} entries from the index...")
        
        # Detect language from the first article
        if results.matches:
            first_article = results.matches[0].metadata.get('content', '')
            if first_article:
                self.detected_lang = self._detect_language(first_article)
                print(f"Detected language: {self.detected_lang}")
                
                # Translate categories if needed
                if self.detected_lang != 'en':
                    print(f"Translating categories to {self.detected_lang}")
                    self.used_categories = self._translate_categories(self.used_categories, self.detected_lang)

        print("\nInitial categories:")
        for category in sorted(self.used_categories):
            print(f"- {category}")
        print()

        # Track progress
        total_entries = len(results.matches)
        processed = 0
        
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
            
            # Add entry_id to each criterion
            for criterion in criteria:
                category = criterion.get('category', 'Uncategorized')
                self.criteria_by_category[category].append(criterion)
    
    def save_criteria(self, output_file="ad_evaluation_criteria.txt"):
        """Save the extracted criteria to a JSON file."""
        # Convert defaultdict to regular dict for JSON serialization
        criteria_dict = dict(self.criteria_by_category)
        
        # Create a flat list of all criteria
        all_criteria = []
        for category, criteria in criteria_dict.items():
            all_criteria.extend(criteria)
        
        # Create the top-level object with the criteria array
        output_data = {
            "criteria": all_criteria,
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        print(f"Saved {len(all_criteria)} criteria to {output_file}")
        
        # Print summary sorted by number of criteria
        print("\nCriteria Summary:")
        # Sort categories by number of criteria (descending)
        sorted_categories = sorted(criteria_dict.items(), key=lambda x: len(x[1]), reverse=True)
        for category, criteria in sorted_categories:
            print(f"{category}: {len(criteria)} criteria")
    
    def run(self):
        """Run the extraction process."""
        print("Starting criteria extraction...")
        self.process_index()
        self.save_criteria("ad_evaluation_criteria.raw.txt")
        print("Extraction complete!")

if __name__ == "__main__":
    extractor = CriteriaExtractor()
    extractor.run() 