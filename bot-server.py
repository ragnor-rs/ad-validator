"""Cloud Run wrapper: serves a health check on $PORT and runs the bot.

Cloud Run requires the container to listen on $PORT, but the bot itself uses
long polling and needs no inbound endpoint - hence the health check in a
background thread and the bot on the main one.
"""

import os
import sys
import threading

from flask import Flask, jsonify

from bot import runBot
from config import ConfigError

app = Flask(__name__)

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

def serve_health_check():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    # Start the health-check server in a background thread, then run the bot.
    threading.Thread(target=serve_health_check, daemon=True).start()

    try:
        runBot()
    except ConfigError as error:
        sys.exit(f"\n{error}\n")
