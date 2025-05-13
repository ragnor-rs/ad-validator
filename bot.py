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


    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome_message = (
            "👋 Welcome to the Ad Validator! 🎨"
        )
        await update.message.reply_text(welcome_message, parse_mode='Markdown')

    def generate_embedding(self, text):
        response = self.openai_client.embeddings.create(
            model="text-embedding-3-large",
            input=text
        )
        return response.data[0].embedding

    def analyse_ad(self, ad_text):
        messages = [
            {"role": "system", "content": """You are an expert in law and advertising. 
            Analyze the ad text and return a plain text analysis with the following sections:
            1. Type: Whether this is an ad for goods or services or both
            2. Topics: List the main topics and categories that might be affected by advertising laws of different countries
            3. Legal Analysis: Describe the possible legal concerns
            Return only the analysis text, no additional formatting."""},
            {"role": "user", "content": f"Analyze this ad text:\n\n{ad_text}"}
        ]

        response = self.openai_client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=messages,
            temperature=0.5,
            max_tokens=1000
        )
        analysis = response.choices[0].message.content.strip()
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
                'description': metadata['description'],
                'id': id
            }

            criteria.append(entry)

            new_criteria.append(entry)

        print(f"Added {len(new_criteria)} new criteria.")

        return new_criteria

    def add_relevant_questions(self, criteria: list, questions: list, ad_text: str) -> None:
        if not criteria:
            return

        # Format criteria into a structured context
        law_context = ""
        for criterion in criteria:
            law_context += f"- {criterion['description']}\n"

        user_prompt = f"""Ad text:\n
{ad_text}\n

Relevant regulations:\n
{law_context}

Instructions:\n
- Generate specific questions to gather missing information needed for proper legal analysis.
- Return only the questions, one per line, without numbering or additional formatting.
- Generate questions in the same language as the ad text above.
- Do not ask about the content of the ad.
- Assume that no ad content exist other than the ad text"""

        print("=== add_relevant_questions { ===");
        print(user_prompt);
        print("=== } add_relevant_questions");

        messages = [
            {"role": "user", "content": user_prompt}
        ]

        # Generate questions using OpenAI
        response = self.openai_client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=messages,
            temperature=0.5,
            max_tokens=1000
        )

        # Process and add new questions
        new_questions = response.choices[0].message.content.strip().split('\n')
        for question in new_questions:
            question = question.strip()
            if question:
                questions.append(question)

        print(f"Added {len(new_questions)} new questions.")

    def generate_response(self, ad_text, criteria, additional_data, ad_analysis):
        if not criteria:
            return "I couldn't find any relevant law for your ad"

        # Format criteria into a structured context
        law_context = ""
        for criterion in criteria:
            if len(law_context) > 0:
                 law_context += "\n"
            law_context += f"From Chapter {criterion['chapter_number']}. {criterion['chapter_title']}, Article {criterion['article_number']}. {criterion['article_title']}:\n"
            law_context += f"{criterion['description']}\n"

        qna = ""
        for item in additional_data:
            if len(qna) > 0:
                 qna += "\n"
            qna += f"Question: {item['question']}\n" 
            qna += f"Answer: {item['answer']}\n"

        user_prompt = f"""Ad text to analyze:\n
{ad_text}\n

Preliminary analysis:\n
{ad_analysis}\n

Relevant legal requirements:\n
{law_context}

Additional data to consider:\n
{qna}

Instructions:\n
- Please evaluate if the ad text complies with these legal requirements. 
- Take questions and answers from the additional data into account.
- For each compliance issue, reference the specific chapter and article it relates to.
- If there are no compliance issues, state that the ad appears to comply with the relevant regulations."""

        print("=== generate_response { ===");
        print(user_prompt);
        print("=== } generate_response");

        messages = [
            {"role": "system", "content": """You are an expert ad analyst and lawyer. Analyze the ad text against the provided legal requirements. 
            Be specific and reference the exact chapters and articles when discussing compliance issues.
            Be concise and straight to the point.
            Take all provided legal requirements into account.
            If the ad text is in a language other than English, respond in that same language."""},
            {"role": "user", "content": user_prompt}
        ]

        # Generate response using OpenAI
        response = self.openai_client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=messages,
            temperature=0.5,
            max_tokens=1000
        )
        return response.choices[0].message.content

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if self.stage == 0:
                self.ad_text = update.message.text

                self.criteria = []
                self.questions = []

                await update.message.reply_text("Running preliminary analysis of the ad text...");
                await update.message.chat.send_action(action="typing")
                self.ad_analysis = self.analyse_ad(self.ad_text)

                new_criteria = []

                await update.message.reply_text("Looking for relevant criteria based on the preliminary analysis results...");
                await update.message.chat.send_action(action="typing")
                new_criteria += self.add_relevant_criteria(self.ad_analysis, self.criteria)

                # await update.message.reply_text("Looking for general criteria...");
                # await update.message.chat.send_action(action="typing")
                # new_criteria += self.add_relevant_criteria("General, placement", self.criteria)

                await update.message.reply_text("Looking for relevant criteria based on the ad text...");
                await update.message.chat.send_action(action="typing")
                new_criteria += self.add_relevant_criteria(self.ad_text, self.criteria)

                await update.message.reply_text("Gathering additional data from the user...");
                await update.message.chat.send_action(action="typing")
                self.add_relevant_questions(new_criteria, self.questions, self.ad_text)

                if len(self.questions) > 0: 
                    await update.message.reply_text(self.questions[0]);

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

                # new_criteria = []

                # await update.message.reply_text("Looking for relevant criteria based on the reply...");
                # await update.message.chat.send_action(action="typing")
                # new_criteria = self.add_relevant_criteria(f"{pair['question']} {pair['answer']}", self.criteria)

                # await update.message.reply_text("Generating more questions...");
                # await update.message.chat.send_action(action="typing")
                # self.add_relevant_questions(new_criteria, self.questions, self.ad_text)

                self.step += 1

                if self.step >= len(self.questions):
                    await update.message.reply_text("Running full analysis...");
                    await update.message.chat.send_action(action="typing")
                    response = self.generate_response(self.ad_text, self.criteria, self.additional_data, self.ad_analysis)

                    # Send response with markdown formatting
                    telegram_markdown = telegramify_markdown.markdownify(
                        response,
                        max_line_length=None,  # If you want to change the max line length for links, images, set it to the desired value.
                        normalize_whitespace=False
                    )
                    await update.message.reply_text(telegram_markdown, parse_mode='MarkdownV2')
                    
                    self.stage = 0

                else: 
                    await update.message.reply_text(self.questions[self.step]);

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