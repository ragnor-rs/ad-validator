from flask import Flask, jsonify
from scraper import TrendScraper
import os
import threading
import schedule
import time
from datetime import datetime

app = Flask(__name__)
scraper = TrendScraper()

def run_scraper():
    try:
        print(f"Starting scraper run at {datetime.now()}")
        scraper.run()
        print(f"Completed scraper run at {datetime.now()}")
    except Exception as e:
        print(f"Error in scraper run: {str(e)}")

def scheduler_thread():
    run_scraper()

    # Schedule the scraper to run daily at midnight UTC
    schedule.every().day.do(run_scraper)
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    # Start the scheduler in a background thread
    scheduler = threading.Thread(target=scheduler_thread, daemon=True)
    scheduler.start()
    
    # Run the Flask app
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port) 
