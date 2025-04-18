import os
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import openai
import pinecone
from dotenv import load_dotenv
import telegramify_markdown

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
        response = self.openai_client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": """You are an expert in law and advertising. 
                Analyze the ad text and return a plain text analysis with the following sections:
                1. Type: Whether this is an ad for goods or services or both
                2. Topics: List the main topics and categories that might be affected by advertising laws of different countries
                3. Legal Analysis: Describe the possible legal concerns
                Return only the analysis text, no additional formatting."""},
                {"role": "user", "content": f"Analyze this ad text:\n\n{ad_text}"}
            ],
            temperature=0.3,
            max_tokens=500
        )
        
        analysis = response.choices[0].message.content.strip()
        print(f"Ad analysis:\n{analysis}")
        return analysis

    def get_law_context(self, query):
        # Generate embedding for the query
        response = self.openai_client.embeddings.create(
            model="text-embedding-3-large",
            input=query
        )
        query_embedding = response.data[0].embedding

        # Query Pinecone
        results = self.index.query(
            vector=query_embedding,
            top_k=5,
            include_metadata=True
        )

        # Format the context from the results
        context_parts = []
        for match in results.matches:
            metadata = match.metadata
            context_parts.append(
                f"Chapter: {metadata['chapter_number']}. {metadata['chapter_title']}\n"
                f"Article: {metadata['article_number']}. {metadata['article_title']}\n"
                f"Content:\n{metadata['content']}\n"
            )

        return "\n".join(context_parts)

    def generate_response(self, ad_text, law_context):
        if not law_context:
            return "I couldn't find any relevant law for your ad"

        print(f"Law context:\n{law_context}")

        # Generate response using OpenAI
        response = self.openai_client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": "You are a ad analyst and a lawyer. You provide insightful analysis of ad based on the given query and context. You are a helpful assistant. You are straight to the point and concise."},
                {"role": "developer", "content": f"Ad text:\n{ad_text}"},
                {"role": "developer", "content": f"Law context:\n\n{law_context}"},
                {"role": "user", "content": """Please evaluate if the ad text is compliant with the law. 
Reply only in the language of the ad text.
If there's no law context then admit you don't know relevant law. 
Mention related articles and sections of the law."""}
            ],
            temperature=0.2,
            max_tokens=1000
        )

        return response.choices[0].message.content

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            ad_text = update.message.text
        
            await update.message.chat.send_action(action="typing")

            ad_analysis = self.analyse_ad(ad_text)
            
            law_context = self.get_law_context(ad_analysis)
            
            # Generate response
            response = self.generate_response(ad_text, law_context)
            
            # Convert response to Telegram MarkdownV2 format
            telegram_markdown = telegramify_markdown.markdownify(
                response,
                max_line_length=None,  # If you want to change the max line length for links, images, set it to the desired value.
                normalize_whitespace=False
            )
            
            # Send response with markdown formatting
            await update.message.reply_text(telegram_markdown, parse_mode='MarkdownV2')

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