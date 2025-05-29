import os
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import openai
import pinecone
from dotenv import load_dotenv
import telegramify_markdown
import random

load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

default_model = "gpt-4o"
default_system_prompt = """You are a highly skilled legal compliance analyst specializing in advertising regulations. Your task is to analyze ad content and assess its compliance with relevant advertising laws and industry standards. This includes identifying potential violations, deceptive claims, required disclaimers, and age-restricted content. Your assessment should be clear and specific.

Note: Tailor your analysis based on the jurisdiction(s) provided or infer based on context if not specified."""

class AdValidatorBot:
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Initialize Pinecone with the new syntax
        pc = pinecone.Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        self.index = pc.Index(os.getenv("PINECONE_INDEX_NAME"))

        self.ad_text = None

        self.ad_analysis = None

        self.criteria = []
        self.questions = []
        self.additional_data = []

        self.stage = 0
        self.step = 0

        self.detected_lang = "English"
        self.law_context = ""

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome_message = (
            "👋 Welcome to the Ad Validator! 🎨"
        )
        await update.message.reply_text(welcome_message, parse_mode='Markdown')

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

    def generate_embedding(self, text):
        response = self.openai_client.embeddings.create(
            model="text-embedding-3-large",
            input=text
        )
        return response.data[0].embedding

    def analyse_ad(self, ad_text, detected_lang):
        user_prompt = f"""I. Ad text to analyze:

{ad_text}


II. Jurisdiction:

{detected_lang} law


III. Instructions:
- Analyze this ad text from a legal perspective
- Highlight each possible violation on a separate line
- Do not group items
- Do not use any formatting"""

        messages = [
            {"role": "system", "content": default_system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        print("=== BEGIN analyse_ad ===")
        print(user_prompt)
        print("=== END analyse_ad ===")
        print()

        response = self.openai_client.chat.completions.create(
            model=default_model,
            messages=messages,
            temperature=0.5,
            max_tokens=1000
        )
        analysis = [line.strip() for line in response.choices[0].message.content.strip().splitlines() if line.strip()]
        return analysis

    def add_relevant_criteria(self, query: str, criteria: list) -> list:
        # Generate embedding for the query
        response = self.openai_client.embeddings.create(
            model="text-embedding-3-large",
            input=query
        )
        query_embedding = response.data[0].embedding

        # Query Pinecone
        results = self.index.query(
            vector=query_embedding,
            top_k=10,
            include_metadata=True
        )

        new_criteria = []

        # Format the context from the results
        for match in results.matches:
            id = match.id

            # Skip if criteria with this ID already exists
            if any(c['id'] == id for c in criteria):
                continue
                
            metadata = match.metadata
            entry = {
                'chapter_number': metadata['chapter_number'],
                'chapter_title': metadata['chapter_title'],
                'article_number': metadata['article_number'],
                'article_title': metadata['article_title'],
                'clause_number': metadata['clause_number'],
                'description': metadata['description'],
                'id': id
            }

            criteria.append(entry)

            new_criteria.append(entry)

        print(f"Added {len(new_criteria)} new criteria.")

        return new_criteria

    def to_law_context(self, new_criteria: list):
        new_law_context = ""
        for i, criterion in enumerate(new_criteria):
            if len(new_law_context) > 0:
                new_law_context += "\n\n"
            new_law_context += f"""From chapter \"{criterion['chapter_number']}. {criterion['chapter_title']}”, article \"{criterion['article_number']}. {criterion['article_title']}”, clause {criterion['clause_number']}:
{criterion['description']}""" 

        return new_law_context

    def add_relevant_questions(self, criteria: list, questions: list, ad_text: str, detected_lang) -> None:
        if not criteria:
            return

        law_context = self.to_law_context(criteria);

        user_prompt = f"""I. Ad text to analyze:

{ad_text}


II. Jurisdiction:

{detected_lang} law


III. Law context:

{law_context}


IV. Instructions:

- Determine factors affecting legal assessment based strictly on the relevant excerpts
- Determine which data is missing to proceed with evaluation of the factors
- Formulate questions in {detected_lang} to retrieve the missing data
- Do not give questions to which you can answer by yourself
- Give only questions to which the author of the ad can answer
- Give each question on a separate line
- Don't use any formatting"""

        print("=== BEGIN add_relevant_questions ===")
        print(user_prompt)
        print("=== END add_relevant_questions ===")
        print()

        messages = [
            {"role": "system", "content": default_system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # Generate questions using OpenAI
        response = self.openai_client.chat.completions.create(
            model=default_model,
            messages=messages,
            temperature=0.5,
            max_tokens=1000
        )

        # Process and add new questions
        new_questions = [line.strip() for line in response.choices[0].message.content.strip().splitlines() if line.strip()]
        questions += new_questions

        print(f"Added {len(new_questions)} new questions.")

    def generate_response(self, ad_text, criteria, additional_data, detected_lang):
        if not criteria:
            return "I couldn't find any relevant law for your ad"

        # Format criteria into a structured context
        law_context = self.to_law_context(criteria)

        ad_context = ""
        for item in additional_data:
            if len(ad_context) > 0:
                 ad_context += "\n\n"
            ad_context += f"{item['question']}\n{item['answer']}" 

        user_prompt = f"""I. Ad text to analyze:

{ad_text}


II. Jurisdiction:

{detected_lang} law


III. Relevant law:

{law_context}


IV. Ad context:

{ad_context}


V. Instructions:

- Analyze this ad text from a legal perspective
- Give the summary in {detected_lang}
- Don't use any formatting"""

        print("=== BEGIN generate_response ===")
        print(user_prompt)
        print("=== END generate_response ===")
        print()


        messages = [
            {"role": "system", "content": default_system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # Generate response using OpenAI
        response = self.openai_client.chat.completions.create(
            model=default_model,
            messages=messages,
            temperature=0.5,
            max_tokens=1000
        )
        return response.choices[0].message.content

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if self.stage == 0:
                self.ad_text = update.message.text

                await update.message.reply_text("Detecting language...");
                await update.message.chat.send_action(action="typing")
                self.detected_lang = self._detect_language(self.ad_text)
                print(f"Detected language: {self.detected_lang}")

                self.criteria = []
                self.questions = []

                new_criteria = []

                await update.message.reply_text("Looking for relevant criteria based on the ad text...");
                await update.message.chat.send_action(action="typing")
                new_criteria += self.add_relevant_criteria(self.ad_text, self.criteria)

                await update.message.reply_text("Running preliminary analysis of the ad text...");
                await update.message.chat.send_action(action="typing")
                self.ad_analysis = self.analyse_ad(self.ad_text, self.detected_lang)

                await update.message.reply_text("Looking for relevant criteria based on the preliminary analysis results...");
                await update.message.chat.send_action(action="typing")
                for line in self.ad_analysis:
                    new_criteria += self.add_relevant_criteria(line, self.criteria)

                await update.message.reply_text("Generating questions...");
                await update.message.chat.send_action(action="typing")
                self.add_relevant_questions(new_criteria, self.questions, self.ad_text, self.detected_lang)

                if len(self.questions) > 0: 
                    await update.message.reply_text(f"Question 1/{len(self.questions)}:\n" + self.questions[0]);

                    self.stage = 1
                    self.step = 0
                
                else: 
                    self.stage = 2

            elif self.stage == 1:
                answer = update.message.text
                pair = {
                    "question": self.questions[self.step],
                    "answer": answer
                }
                self.additional_data.append(pair)

                self.step += 1

                if self.step >= len(self.questions):
                    await update.message.reply_text("Running full analysis...");
                    await update.message.chat.send_action(action="typing")
                    response = self.generate_response(self.ad_text, self.criteria, self.additional_data, self.detected_lang)

                    # Send response with markdown formatting
                    telegram_markdown = telegramify_markdown.markdownify(
                        response,
                        max_line_length=None,  # If you want to change the max line length for links, images, set it to the desired value.
                        normalize_whitespace=False
                    )
                    await update.message.reply_text(telegram_markdown, parse_mode='MarkdownV2')
                    
                    self.stage = 0

                else: 
                    await update.message.reply_text(f"Question {self.step + 1}/{len(self.questions)}:\n" + self.questions[self.step]);

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            await update.message.reply_text(
                "Sorry, I encountered an error while processing your request. Please try again later."
            )

def runBot():
    # Initialize bot
    application = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
    ad_validator_bot = AdValidatorBot()

    # Add handlers
    application.add_handler(CommandHandler("start", ad_validator_bot.start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ad_validator_bot.handle_message))

    # Start the bot
    application.run_polling()

if __name__ == "__main__":
    runBot() 