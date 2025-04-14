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

    def search_law(self, query):
        query_embedding = self.generate_embedding(query)
        
        # Search in Pinecone
        results = self.index.query(
            vector=query_embedding,
            top_k=5,
            include_metadata=True
        )

        return results.matches  # Return the matches directly

    def generate_response(self, query, results):
        if not results:
            return "I couldn't find any relevant law for your query"

        # Prepare context from search results
        context = "\n\n".join([
            f"Content: {r.metadata['content']}\n"
            for r in results
        ])

        # Generate response using OpenAI
        response = self.openai_client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": "You are a ad analyst and a lawyer. You provide insightful analysis of ad based on the given query and context. You are a helpful assistant. You are straight to the point and concise."},
                {"role": "developer", "content": f"Query:\n{query}"},
                {"role": "developer", "content": f"Law context:\n\n{context}"},
                {"role": "user", "content": "Please evaluate if the ad is compliant with the law. Strictly adhere to the query. Do not invent anything. If there's no topic of the query then admit there's no relevant knowledge in the context. Say you don't know if there's no information in the context. Do not explain nor summarize the context if there's no relevant information in it. Mention the month and the year. Use the language of the query. Add the sources of the information in the separate paragraph as a list if and only if there's relevant information in the context."}
            ],
            temperature=0.3,
            max_tokens=1000
        )

        return response.choices[0].message.content

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            query = update.message.text
        
            await update.message.chat.send_action(action="typing")
            
            results = self.search_law(query)
            
            # Generate response
            response = self.generate_response(query, results)
            
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