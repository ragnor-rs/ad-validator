import schedule
import time
from scraper import TrendScraper
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def run_scraper():
    try:
        logger.info("Starting scheduled scraping job")
        scraper = TrendScraper()
        scraper.run()
        logger.info("Scheduled scraping job completed successfully")
    except Exception as e:
        logger.error(f"Error in scheduled scraping job: {str(e)}")

def main():
    # Schedule the scraper to run daily at 00:00 UTC
    schedule.every().day.at("00:00").do(run_scraper)
    
    logger.info("Scheduler started. Scraper will run daily at 00:00 UTC")
    
    # Run the scraper immediately on startup
    run_scraper()
    
    # Keep the script running
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    main() 