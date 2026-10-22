import os
import re
import sys
import time

import config
from config import ConfigError
from ai_tools import generate_embedding

LAW_FILE = 'law.txt'

class LawScraper:
    def __init__(self, dry_run=False):
        """With dry_run=True the law is parsed but nothing is embedded or
        uploaded, so no credentials and no paid API calls are needed."""
        self.dry_run = dry_run

        if dry_run:
            self.openai_client = None
            self.index = None
        else:
            config.require("OPENAI_API_KEY", "PINECONE_API_KEY", "PINECONE_INDEX_NAME")
            self.openai_client = config.openai_client()
            self.index = config.pinecone_index()

    def save_article(self, content, current_chapter, current_article, articles):
        if not content:
            return articles

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

    def unique_criterion_id(self, criterion, used_ids):
        """Disambiguate a repeated key.

        IDs are the law's own numbering, so a clause number appearing twice in
        one article - article 19 clause 4 does, in the bundled law - would
        otherwise upsert over the earlier clause and drop it from the index.
        Suffixes are assigned in document order, so they stay stable across
        re-runs of the same text.
        """
        base = self.generate_criterion_id(criterion)
        candidate = base
        occurrence = 1
        while candidate in used_ids:
            occurrence += 1
            candidate = f"{base}_{occurrence}"
        used_ids.add(candidate)
        return candidate

    def get_criterion_text(self, criterion):
        # Combine chapter title, article title, and content
        return f"{criterion['chapter_title']}\n{criterion['article_title']}\n{criterion['description']}"

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
        if self.dry_run:
            print(f"Starting law parsing (dry run: nothing is embedded or uploaded)...")
        else:
            print("Starting law scraping...")

        # Read law.txt
        try:
            with open(LAW_FILE, 'r', encoding='utf-8') as file:
                content = file.read()
        except FileNotFoundError:
            raise ConfigError(
                f"'{LAW_FILE}' not found in {os.getcwd()}.\n\n"
                "Run this from the repository root, where law.txt lives."
            )

        # Split into articles
        articles = self.split_into_articles(content)
        print(f"Split content into {len(articles)} articles")

        if not articles:
            raise ConfigError(
                f"No articles were found in '{LAW_FILE}'.\n\n"
                "The parser splits on 'Глава N' / 'Статья N' headers, each on its "
                "own paragraph. If your law uses different wording, adjust the two "
                "regexes in split_into_articles() - see 'Using a different law' in "
                "the README."
            )

        total_criteria = 0
        failed_articles = []
        used_ids = set()

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
                    id = self.unique_criterion_id(criterion, used_ids)

                    # Generate embedding using the shared function
                    criterion_text = self.get_criterion_text(criterion)
                    embedding = None if self.dry_run else generate_embedding(criterion_text, self.openai_client)

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
                if vectors and not self.dry_run:
                    self.index.upsert(
                        vectors=vectors
                    )

                total_criteria += len(vectors)

                print(f"Processed article {article['article']['number']} ({i+1}/{len(articles)}) from chapter {article['chapter']['number']} ({len(vectors)} criteria found)")

                # Small delay to avoid rate limits
                if not self.dry_run:
                    time.sleep(0.1)

            except Exception as e:
                failed_articles.append(article['article']['number'])
                print(f"Error processing article {article['article']['number']}: {str(e)}")

        if self.dry_run:
            print(f"\nDry run completed: {len(articles)} articles, {total_criteria} criteria parsed from '{LAW_FILE}'.")
            print("Re-run without --dry-run to embed them and upload them to Pinecone.")
        else:
            print(f"\nLaw scraping completed: {total_criteria} criteria upserted from {len(articles)} articles.")

        if failed_articles:
            # Without this the run ends in "completed" even when every article
            # failed - for example on a rejected API key - leaving an index that
            # the bot cannot retrieve anything from.
            raise ConfigError(
                f"{len(failed_articles)} of {len(articles)} articles failed: "
                f"{', '.join(failed_articles)}.\n\n"
                "The index is incomplete. Fix the errors printed above and re-run; "
                "criteria are keyed by chapter, article and clause, so re-running "
                "overwrites in place rather than duplicating."
            )

if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv[1:]
    try:
        scraper = LawScraper(dry_run=dry_run)
        scraper.run()
    except ConfigError as error:
        sys.exit(f"\n{error}\n")
