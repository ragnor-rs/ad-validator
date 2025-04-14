# Ad Validator Telegram Bot

A Telegram bot that evaluates advertisements if the comply with the law. The bot uses OpenAI's GPT-4 for generating responses and Pinecone for vector storage.

## Features

- Vector storage of laws concerning advertising using Pinecone
- Natural language queries
- Retrieval Augmented Generation (RAG) for accurate responses
- Deployed on Google Cloud Run

## Prerequisites

- Python 3.11+
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- OpenAI API Key
- Pinecone API Key and Environment
- Google Cloud Project

## Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd trend-parser
```

2. Create a virtual environment and install dependencies:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Create a `.env` file with your credentials:
```bash
cp .env.example .env
# Edit .env with your actual credentials
```

## Local Development

1. Run the bot:
```bash
python bot.py
```

2. Run the scraper (in a separate terminal):
```bash
python scheduler.py
```

## Deployment to Google Cloud

1. Install and initialize the Google Cloud SDK:
```bash
# Install Google Cloud SDK
gcloud init
```

2. Enable required APIs:
```bash
gcloud services enable cloudbuild.googleapis.com run.googleapis.com
```

3. Deploy using Cloud Build:
```bash
gcloud builds submit --config cloudbuild.yaml
```

## Usage

1. Start a chat with your bot on Telegram
2. Send a message with ad text
3. The bot will respond with evaluation on the given ad text

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

MIT License
