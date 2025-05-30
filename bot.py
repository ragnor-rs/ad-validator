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

        # Dictionary to store user states
        self.user_states = {}

    def _get_user_state(self, user_id):
        """Get or create user state"""
        if user_id not in self.user_states:
            self.user_states[user_id] = {
                'ad_text': None,
                'ad_analysis': None,
                'criteria': [],
                'questions': [],
                'additional_data': [],
                'stage': 0,
                'step': 0,
                'detected_lang': "English"
            }
        return self.user_states[user_id]

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

    def add_relevant_questions(self, criteria: list, questions: list, ad_text: str, detected_lang: str, additional_data: list) -> None:
        if not criteria:
            return

        law_context = self.to_law_context(criteria)

        ad_context = self.to_ad_context(additional_data) if len(additional_data) > 0 else "None"

        user_prompt = f"""I. Ad text to analyze:

{ad_text}


II. Jurisdiction:

{detected_lang} law


III. Related clauses from the law:

{law_context}


IV. Extra knowledge about the ad:

{ad_context}


V. Instructions:

- What you would ask about the given ad in {detected_lang} if you were going to assess if the given ad is compliant with the relevant clauses above?
- Give a short example answer in {detected_lang}.
- Do not use formatting.
- Give each question, then |, then an example answer on a separate line.


VI. IMPORTANT! 

- Do NOT ask about content, impressions, claims, promises, statements, mandatory indications, mentions, mandatory disclaimers, accuracy, contained information, meaning of the ad.
- Do NOT assume anything. For example, if it's not known whether the ad is placed on a website then don't ask about websites.
- Do NOT ask about information contained in the extra knowledge section.
- Do NOT repeat questions.
"""

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
            temperature=0.25,
            max_tokens=1000
        )

        # Process and add new questions
        new_questions = []
        for line in response.choices[0].message.content.strip().splitlines():
            line = line.strip()
            if line:
                parts = line.split('|')
                if len(parts) == 2:
                    new_questions.append({
                        'question': parts[0].strip(),
                        'example_answer': parts[1].strip()
                    })
                else:
                    new_questions.append({
                        'question': line,
                        'example_answer': ''
                    })
        questions.extend(new_questions)

        print(f"Added {len(new_questions)} new questions.")

        return new_questions
    
    def to_ad_context(self, additional_data: list):
        ad_context = ""
        for item in additional_data:
            if len(ad_context) > 0:
                 ad_context += "\n\n"
            ad_context += f"{item['question']}\n{item['answer']}" 

        return ad_context;

    def generate_response(self, ad_text, criteria, additional_data, detected_lang):
        if not criteria:
            return "I couldn't find any relevant law for your ad"

        # Format criteria into a structured context
        law_context = self.to_law_context(criteria)

        ad_context = self.to_ad_context(additional_data)

        user_prompt = f"""I. Ad text to analyze:

{ad_text}


II. Jurisdiction:

{detected_lang} law


III. Relevant law:

{law_context}


IV. Ad context:

{ad_context}


V. Instructions:

- Analyze the given ad text from a legal perspective
- Apply the relevant law
- Apply the ad context
- Give the summary in {detected_lang}
- Be straight to the point, short and concise
- Be as detailed as possible"""

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
            user_id = update.effective_user.id
            state = self._get_user_state(user_id)

            if state['stage'] == 0:
                state = {
                    'ad_text': update.message.text,
                    'ad_analysis': None,
                    'criteria': [],
                    'questions': [],
                    'additional_data': [],
                    'stage': 0,
                    'step': 0,
                    'detected_lang': "English"
                }
                
                self.user_states[user_id] = state
                
                await update.message.reply_text("Detecting language...");
                await update.message.chat.send_action(action="typing")
                state['detected_lang'] = self._detect_language(state['ad_text'])
                print(f"Detected language: {state['detected_lang']}")

                new_criteria = []

                await update.message.reply_text("Looking for relevant criteria based on the ad text...");
                await update.message.chat.send_action(action="typing")
                new_criteria += self.add_relevant_criteria(state['ad_text'], state['criteria'])

                await update.message.reply_text("Running preliminary analysis of the ad text...");
                await update.message.chat.send_action(action="typing")
                state['ad_analysis'] = self.analyse_ad(state['ad_text'], state['detected_lang'])

                await update.message.reply_text("Looking for relevant criteria based on the preliminary analysis results...");
                await update.message.chat.send_action(action="typing")
                for line in state['ad_analysis']:
                    new_criteria += self.add_relevant_criteria(line, state['criteria'])
                
                await update.message.reply_text("Generating questions...");
                await update.message.chat.send_action(action="typing")
                new_questions = self.add_relevant_questions(new_criteria, state['questions'], state['ad_text'], state['detected_lang'], state['additional_data'])

                if len(new_questions) > 0: 
                    await update.message.reply_text(f"Question 1/{len(state['questions'])}:\n" + state['questions'][0]['question'] + "\n\nExample answer:\n" + state['questions'][0]['example_answer']);
                    state['stage'] = 1
                else: 
                    state['stage'] = 2

            elif state['stage'] == 1:
                answer = update.message.text
                pair = {
                    "question": state['questions'][state['step']]['question'],
                    "answer": answer
                }
                state['additional_data'].append(pair)

                state['step'] += 1

                if state['step'] >= len(state['questions']):
                    new_questions = []

                    if len(new_questions) > 0:
                        state['questions'] += new_questions

                if state['step'] >= len(state['questions']):
                    await update.message.reply_text("Running full analysis...");
                    await update.message.chat.send_action(action="typing")
                    response = self.generate_response(state['ad_text'], state['criteria'], state['additional_data'], state['detected_lang'])

                    # Send response with markdown formatting
                    telegram_markdown = telegramify_markdown.markdownify(
                        response,
                        max_line_length=None,
                        normalize_whitespace=False
                    )
                    await update.message.reply_text(telegram_markdown, parse_mode='MarkdownV2')
                    
                    state['stage'] = 0

                else: 
                    await update.message.reply_text(f"Question {state['step'] + 1}/{len(state['questions'])}:\n" + state['questions'][state['step']]['question'] + "\n\nExample answer:\n" + state['questions'][state['step']]['example_answer']);

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