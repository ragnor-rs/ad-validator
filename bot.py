import os
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import openai
import pinecone
from dotenv import load_dotenv
import time

load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TrendBot:
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Initialize Pinecone
        api_key = os.getenv("PINECONE_API_KEY")
        environment = os.getenv("PINECONE_ENVIRONMENT")
        host = os.getenv("PINECONE_HOST")
        index_name = os.getenv("PINECONE_INDEX_NAME")
        
        # Initialize Pinecone with all parameters
        pinecone.init(api_key=api_key, environment=environment)
        
        # Connect directly to the index using the host
        self.index = pinecone.Index(index_name, host=host)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome_message = (
            "👋 Welcome to the Design Trends Bot! 🎨\n\n"
            "I can help you discover design trends for specific topics, months, and years.\n\n"
            "To get started, just send me a message in this format:\n"
            "`topic month year`\n\n"
            "For example:\n"
            "`sustainable design March 2024`\n"
            "`minimalist furniture January 2024`\n\n"
            "I'll analyze the trends and provide you with insights! 🚀"
        )
        await update.message.reply_text(welcome_message, parse_mode='Markdown')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "📚 How to use the Design Trends Bot:\n\n"
            "1. Send a message with your query in this format:\n"
            "`topic month year`\n\n"
            "2. I'll search through our database of design trends and provide you with relevant insights.\n\n"
            "Examples:\n"
            "- `sustainable design March 2024`\n"
            "- `minimalist furniture January 2024`\n"
            "- `color trends February 2024`\n\n"
            "Commands:\n"
            "/start - Start the bot\n"
            "/help - Show this help message"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')

    def generate_embedding(self, text):
        response = self.openai_client.embeddings.create(
            model="text-embedding-3-large",
            input=text
        )
        return response.data[0].embedding

    def search_trends(self, query, month=None, year=None):
        query_embedding = self.generate_embedding(query)
        
        # Search in Pinecone
        results = self.index.query(
            vector=query_embedding,
            top_k=5,
            include_metadata=True
        )

        # Filter results by month and year if specified
        filtered_results = []
        for match in results.matches:
            result_date = datetime.fromisoformat(match.metadata['date'])
            if month and year:
                if result_date.month == month and result_date.year == year:
                    filtered_results.append(match)
            elif year:
                if result_date.year == year:
                    filtered_results.append(match)
            else:
                filtered_results.append(match)

        return filtered_results

    def generate_response(self, query, results):
        if not results:
            return "I couldn't find any relevant trends for your query. Try a different topic or time period."

        # Prepare context from search results
        context = "\n\n".join([
            f"Date: {datetime.fromisoformat(r.metadata['date']).strftime('%B %d, %Y')}\n"
            f"Content: {r.metadata['content']}\n"
            f"Themes: {', '.join(r.metadata['themes'])}"
            for r in results
        ])

        # Generate response using OpenAI
        response = self.openai_client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": "You are a design trends analyst. Provide insightful analysis of design trends based on the given context. Focus on key insights and patterns."},
                {"role": "user", "content": f"Query: {query}\n\nContext:\n{context}\n\nPlease provide a comprehensive analysis of the design trends based on this information."}
            ],
            temperature=0.7,
            max_tokens=1000
        )

        return response.choices[0].message.content

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            # Parse the message
            message_parts = update.message.text.strip().split()
            if len(message_parts) < 2:
                await update.message.reply_text(
                    "Please provide a topic, month, and year in the format: `topic month year`\n"
                    "Example: `sustainable design March 2024`",
                    parse_mode='Markdown'
                )
                return

            # Extract query components
            topic = " ".join(message_parts[:-2])
            month_str = message_parts[-2]
            year_str = message_parts[-1]

            # Convert month name to number
            try:
                month = datetime.strptime(month_str, "%B").month
            except ValueError:
                await update.message.reply_text(
                    "Invalid month format. Please use the full month name (e.g., March, April)."
                )
                return

            # Convert year to integer
            try:
                year = int(year_str)
            except ValueError:
                await update.message.reply_text(
                    "Invalid year format. Please use a valid year (e.g., 2024)."
                )
                return

            # Send typing action
            await update.message.chat.send_action(action="typing")

            # Search for trends
            results = self.search_trends(topic, month, year)
            
            # Generate response
            response = self.generate_response(topic, results)

            # Send response
            await update.message.reply_text(response)

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            await update.message.reply_text(
                "Sorry, I encountered an error while processing your request. Please try again later."
            )

def main():
    # Initialize bot
    application = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
    trend_bot = TrendBot()

    # Add handlers
    application.add_handler(CommandHandler("start", trend_bot.start))
    application.add_handler(CommandHandler("help", trend_bot.help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, trend_bot.handle_message))

    # Start the bot
    application.run_polling()

if __name__ == "__main__":
    main() 