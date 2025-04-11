from flask import Flask, jsonify
from bot import runBot
import os
import threading
import schedule
import time
import asyncio
from datetime import datetime

app = Flask(__name__)

def scheduler_thread():
    # Run the Flask app
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port) 
    
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

    runBot()
