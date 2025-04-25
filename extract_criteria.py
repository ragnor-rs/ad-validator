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
        self.used_categories = set()
        
    def extract_criteria_from_text(self, text, chapter_title, article_title, chapter_number, article_number, entry_id):
        """Extract advertising evaluation criteria from a law text using GPT."""
        # Create category guidance based on existing categories
        category_guidance = ""
        if self.used_categories:
            category_guidance = "Use the provided categories from the dictionary of categories or extract new categories for classifying ad texts from the law topic and the law text if no suitable category is found."
        else:
            category_guidance = "Extract categories for classifying ad texts from the law topic and the law text."
        
        prompt = f"""Determine the language of the law topic and the law text. 

        For each criterion, do this:
        1. {category_guidance} Use the determined language for the category.
        2. Provide a clear, concise description of the criterion. Translate the description into the determined language.

        Format your response with each criterion on a new line using the pipe symbol (|) as a separator:
        category | description
        
        For example:
        Gambling | Ad must not overstate the benefits of gambling
        Medical goods and services | Medicine ad must mention side effects and contraindications
        General | Ad must not contain any inappropriate words

        IMPORTANT: 
        - The category MUST BE in the determined language.
        - The description MUST BE in the determined language.
        - Return ONLY the list, no additional text or explanations.
        - Categories MUST DESCRIBE goods or services, not the law text.

        GODD categories (USE FREELY): Gambling, Medical servicse, Real estate, Public events, Financial instruments, Loans, Foreign exchange, Invenstments, Digital assets, Digital products, Food supplements, E-commerce, Products for children, etc.
        
        BAD categories (AVOID AT ALL COSTS): Administrative responsibility, Antimonopoly law, Violation, Fines, Content, Placement, Legislation, Prohibition, Compliance, Ethics, Culture, Language, Improper words, etc.
        
        Use General category when you can't come up with a suitable category."""

        messages = [
            {"role": "system", "content": "You are an expert in advertising law who extracts specific evaluation criteria from legal texts. You know what is advertised, so you can classify the ad content into a category without doing any research."},
            {"role": "developer", "content": f"Law topic: {article_title}"},
            {"role": "developer", "content": f"Law text: {text}"},
        ]
        
        if self.used_categories:
            messages.append({"role": "developer", "content": f"Category dictionary: {', '.join(self.used_categories)}"})
            
        messages.append({"role": "user", "content": prompt})
        
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