# Ad Validator Telegram Bot

A Telegram bot that checks advertising copy against **Russian Federal Law No. 38-FZ of 13 March 2006 "On Advertising"** (Федеральный закон «О рекламе») and reports which requirements the ad may violate.

The bot uses retrieval-augmented generation: the text of the law is split into articles, individual legal requirements are extracted from each article and stored as embeddings in Pinecone. When you submit an ad, the bot retrieves the requirements most relevant to it, asks you clarifying questions where the law's applicability depends on facts not present in the ad, and then returns an assessment.

> ### Disclaimer
>
> This project is **not legal advice**. It is an experimental tool built on top of a large language model, which can misread the law, miss applicable requirements, or report violations that do not exist. Do not rely on its output for any compliance, regulatory, or commercial decision. Consult a qualified lawyer. The software is provided "as is", without warranty of any kind — see [LICENSE](LICENSE).

## How it works

| File | Role |
| --- | --- |
| `scraper.py` | One-time ingestion: parses `law.txt` into articles, extracts legal requirements with an LLM, writes embeddings to Pinecone. |
| `bot.py` | The Telegram bot itself (long polling). Retrieves relevant requirements, runs the question/answer flow, produces the verdict. |
| `bot-server.py` | Wrapper for Cloud Run: serves a health-check endpoint on `$PORT` and runs the bot. |
| `bot_prompts.py` | All LLM prompt templates. |
| `ai_tools.py` | Shared OpenAI helpers (language detection, embeddings). |
| `law.txt` | Text of Federal Law No. 38-FZ. See [Source of the law text](#source-of-the-law-text). |

Models used: `gpt-4o` for reasoning and `text-embedding-3-large` (3072 dimensions) for embeddings.

## Prerequisites

- Python 3.11+
- Telegram bot token (from [@BotFather](https://t.me/botfather))
- OpenAI API key
- Pinecone API key and an index
- Google Cloud project (only if you want to deploy)

Running the ingestion step and the bot both consume paid OpenAI tokens. Ingesting the full law makes one LLM call per article plus one embedding call per extracted requirement.

## Setup

1. Clone the repository:

```bash
git clone https://github.com/ragnor-rs/ad-validator.git
cd ad-validator
```

2. Create a virtual environment and install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Create a Pinecone index. It must match the embedding model:

- **dimension:** `3072` (for `text-embedding-3-large`)
- **metric:** `cosine`

4. Configure credentials:

```bash
cp .env.example .env
# Edit .env with your actual credentials, including the index name from step 3
```

5. Ingest the law into Pinecone. **This is required** — until it is done the index is empty and the bot has nothing to retrieve, so it will return meaningless results:

```bash
python scraper.py
```

This runs once, not on a schedule. Re-run it only after replacing `law.txt` with a newer version of the law. Each requirement is keyed by its chapter, article and clause number, so re-running overwrites requirements in place instead of duplicating them — but requirements that were renumbered or repealed in the meantime are left behind as stale entries. Clear the index first if that matters to you.

## Local development

Run the bot (long polling, no public endpoint needed):

```bash
python bot.py
```

## Deployment to Google Cloud

The provided configuration deploys `bot-server.py` to Cloud Run.

1. Install and initialize the Google Cloud SDK:

```bash
gcloud init
```

2. Enable the required APIs:

```bash
gcloud services enable cloudbuild.googleapis.com run.googleapis.com
```

3. Deploy using Cloud Build:

```bash
gcloud builds submit --config cloudbuild.yaml
```

Supply `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `PINECONE_API_KEY` and `PINECONE_INDEX_NAME` to the Cloud Run service as environment variables or secrets — `.env` is excluded from the deployed image by `.gcloudignore`.

## Usage

1. Start a chat with your bot on Telegram and send `/start`.
2. Send the text of the ad you want checked.
3. Answer any clarifying questions the bot asks.
4. The bot replies with its assessment, citing the articles and clauses it relied on.

## Source of the law text

`law.txt` is the consolidated text of Federal Law No. 38-FZ of 13 March 2006 "On Advertising", including amendments **up to and including No. 411-FZ of 23 November 2024**. The law has been amended since; this copy is not guaranteed to reflect the current version. Check the [official publication portal](http://pravo.gov.ru) or [government.ru](http://government.ru/docs/all/98086/) and replace `law.txt` (then re-run `python scraper.py`) if you need an up-to-date edition.

Official documents of state authorities, including laws, are not subject to copyright under Article 1259(6) of the Civil Code of the Russian Federation. The MIT license in [LICENSE](LICENSE) covers the code in this repository, not the text of the statute.

## Contributing

Issues and pull requests are welcome.

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a pull request

## License

[MIT](LICENSE) © Renat Sarymsakov
