# Ad Validator Telegram Bot

A Telegram bot that checks advertising copy against an advertising law of your choice and reports which requirements the ad may violate.

The bot uses retrieval-augmented generation: the law is split into articles, individual legal requirements are extracted from each article and stored as embeddings in Pinecone. When you submit an ad, the bot retrieves the requirements most relevant to it, asks you clarifying questions where the law's applicability depends on facts not present in the ad, and then returns an assessment.

The law is supplied as a plain text file, `law.txt`, and nothing about the analysis is specific to any one jurisdiction — see [Using a different law](#using-a-different-law). This repository ships with Russian Federal Law No. 38-FZ of 13 March 2006 "On Advertising" (Федеральный закон «О рекламе») as the worked example, since that is what the bot was developed and tested against.

> ### Disclaimer
>
> This project is **not legal advice**. It is an experimental tool built on top of a large language model, which can misread the law, miss applicable requirements, or report violations that do not exist. Do not rely on its output for any compliance, regulatory, or commercial decision. Consult a qualified lawyer. The software is provided "as is", without warranty of any kind — see [LICENSE](LICENSE).

## Project status

This is a **working prototype** (a proof of concept, not an MVP): no authentication, no billing, no interface beyond the Telegram chat, and no automated tests. Work on it was declared finished on 30 May 2025 and the repository is published as a portfolio piece. It is not maintained, but it runs.

It began as a clone of a sibling "trend parser" bot that answered design-trend questions over scraped articles — same RAG machinery, different knowledge source. Both were first prototyped on n8n (no-code) and then rewritten in Python for control and speed. That shared ancestry is why the two projects look alike structurally.

## How it works

Naive RAG over the law did not work: embedding whole articles and retrieving by similarity to the ad text produced either "no relevant law found" or a verdict citing five unrelated articles. The bundled Russian law alone contains on the order of 50 distinct requirements, and relevance to an ad is usually not a surface-level semantic match. What the bot does instead is a seven-step chain, one LLM call per step:

0. **Detect the language** of the ad. Every prompt then instructs the model to work *in the language of the ad*, and no prompt names a country, a statute, or an article. This is why the law is swappable.
1. **Retrieve candidate requirements** from Pinecone by similarity to the raw ad text (`top_k=10`).
2. **Run a preliminary analysis** of the ad on its own, without the law, to surface topics and sensitive angles — then retrieve a second round of requirements against each line of that analysis. This two-pass retrieval is what fixed the original relevance problem.
3. **Extract a flat list of requirements** from the retrieved articles and clauses.
4. **Drop requirements that do not apply** to this ad.
5. **Drop requirements that can already be judged** from the ad text alone, leaving only those whose applicability depends on facts the ad does not state (where it will be placed, who the issuer is, what share of broadcast time it occupies).
6. **Turn each remaining requirement into a question** for the user, and ask them one at a time.
7. **Produce the verdict** from the ad text, the retrieved law, and the user's answers.

| File | Role |
| --- | --- |
| `scraper.py` | One-time ingestion: parses `law.txt` into chapters, articles and clauses, then writes one embedding per clause to Pinecone. The only component that cares about the law's formatting. `python scraper.py --dry-run` parses and reports without calling any paid API. |
| `bot.py` | The Telegram bot itself (long polling). Runs the seven-step chain above. |
| `bot-server.py` | Wrapper for Cloud Run: serves a health-check endpoint on `$PORT` and runs the bot. |
| `bot_prompts.py` | All LLM prompt templates — one per step of the chain. |
| `ai_tools.py` | Shared OpenAI helpers (language detection, embeddings). |
| `config.py` | Model names, and the environment check that both entry points run before they start. |
| `law.txt` | The law to check against. Replaceable — see [Using a different law](#using-a-different-law) and [The bundled law text](#the-bundled-law-text). |

Models used: `gpt-4o` for reasoning and `text-embedding-3-large` (3072 dimensions) for embeddings. Ingesting the bundled law yields 290 clauses across 43 articles, one vector each; step 3 of the chain then expands whatever was retrieved into a flat list of individual requirements at query time, which is where the larger counts come from.

## Prerequisites

- Python 3.11+
- Telegram bot token (from [@BotFather](https://t.me/botfather))
- OpenAI API key
- Pinecone API key and an index
- Google Cloud project (only if you want to deploy)

Running the ingestion step and the bot both consume paid OpenAI tokens. Ingesting the bundled law makes 290 embedding calls and no LLM calls; checking one ad makes seven LLM calls plus one embedding call per retrieval pass. To see the ingestion parse without spending anything, run `python scraper.py --dry-run`.

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

5. Check the law parses, without spending anything:

```bash
python scraper.py --dry-run
```

Against the bundled `law.txt` this reports `43 articles, 290 criteria`. Needs no credentials, makes no API calls.

6. Ingest the law into Pinecone. **This is required** — until it is done the index is empty, so the bot refuses to start:

```bash
python scraper.py
```

This runs once, not on a schedule. Re-run it only after replacing `law.txt` with a newer version of the law. Each requirement is keyed by its chapter, article and clause number, so re-running overwrites requirements in place instead of duplicating them — but requirements that were renumbered or repealed in the meantime are left behind as stale entries. Clear the index first if that matters to you.

## Using a different law

To check ads against some other advertising law, replace `law.txt` and re-run `python scraper.py` against an empty index. Nothing else needs to change: the bot never names a jurisdiction, and every prompt works in the language of the ad, so a Spanish ad checked against Spanish law gets a Spanish verdict.

The one place the law's shape is baked in is `scraper.py`, which splits the text on Russian structural headers:

```python
chapter_match = re.match(r'Глава\s+((\d\.{0,1})+)\s+(.*)', section)
article_match = re.match(r'Статья\s+((\d\.{0,1})+)\s+(.*)', section)
```

So `law.txt` must either use `Глава N` / `Статья N` headers, each on its own paragraph, or you must change those two regexes to match your law's wording — `Chapter` / `Article`, `Capítulo` / `Artículo`, and so on. Clause splitting within an article is already language-neutral: it keys on lines beginning `1.`, `2.`, and so forth.

Two caveats worth knowing before you try it:

- Retrieval quality was only ever tuned against the bundled law. A statute organised very differently (few long articles rather than many short clauses) may retrieve poorly, and `top_k=10` is not obviously the right number for it.
- A law's own article numbering ends up in the requirement IDs, so always ingest a new law into a fresh or cleared index rather than on top of another one.

## Local development

Run the bot (long polling, no public endpoint needed):

```bash
python bot.py
```

On startup it checks that all four environment variables are set, that the Pinecone index exists and has dimension 3072, and that the law has been ingested into it. Anything missing is reported as a message naming the fix, before the bot connects to Telegram.

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

Supply `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `PINECONE_API_KEY` and `PINECONE_INDEX_NAME` to the Cloud Run service as environment variables or secrets — `.env` is excluded from the build context by `.gcloudignore` (for `gcloud builds submit`) and by `.dockerignore` (for a local `docker build`), so it is never baked into the image.

## Usage

1. Start a chat with your bot on Telegram and send `/start`.
2. Send the text of the ad you want checked.
3. Answer any clarifying questions the bot asks. They are mostly yes/no; `нет` / `неприменимо` ("no" / "not applicable") are perfectly good answers.
4. The bot replies with its assessment, citing the articles and clauses it relied on.

## Examples

Two ads were used throughout development, and they are still the quickest way to see the bot work. Both are checked against the bundled Russian law. The transcripts below are real, abridged.

### A compliant ad

A genuine Russian radio ad for a car dealership:

> Бесконечно можно смотреть, как горит огонь, как течет вода, а покупать и обслуживать автомобиль — у официального дилера Toyota в Тойота Центр Тобольск Орион! Реклама. ООО Тойота Тобольск

This ad is quoted here for illustration only. Its text belongs to its rights holders — the advertiser named in it, OOO Тойота Тобольск — and "Toyota" and "Тойота Центр" are their trademarks and those of their licensors; neither is covered by this repository's license, and nothing here implies any affiliation or endorsement.

The bot asks nothing and reports compliance with Article 5 (general requirements): the advertiser is named, nothing is misleading, there are no incorrect comparisons, no calls to unlawful action, no resemblance to road signs. It notes that a complete assessment would also depend on where the ad runs.

### A non-compliant ad

A deliberately illegal ad for a fictional cryptocurrency, written to trip several articles at once:

> 🏇 GallopCoin — криптовалюта, которая всегда выигрывает!
> Ставь на скачки — получай монеты.
> ❌ Проигрышей нет — GallopCoin только растёт.
> Твоя активность = твой доход.
>
> 🌪 Скорость. Азарт. Прибыль.

Here the bot asks 6–12 questions about placement — whether the ad runs in a periodical specialising in equestrian sport, during a live broadcast of races, what share of airtime it occupies — because Article 27 permits gambling advertising only in those narrow channels. It then reports, in Russian:

- **Art. 29.1(2)** — "GallopCoin только растёт" is a forecast of price growth for a digital financial asset, and "Твоя активность = твой доход" is a promise of income. Both prohibited.
- **Art. 29.1(1)** — no issuer name, no website carrying the issue decision, no warning about the high risk of losing the funds invested.
- **Art. 27(1.2)** — the ad creates the impression that participation is a way to earn a living.
- **Art. 27** — "Проигрышей нет" creates the impression that winning is guaranteed.
- **Placement** — running on an equestrian-sport site is permitted, but does not cure the above.

A fictional product was used on purpose: the same input every time makes prompt changes comparable. Note the recurring false positive in the last bullet of the real output — see below.

## Limitations and known issues

Observed during development and not fixed:

- **The same ad does not produce the same answer twice.** Article references, the number of questions asked (anywhere from 3 to 12), and the set of violations found all vary between runs on identical input. Nothing is cached or seeded, and every step of the chain runs at `temperature=0.5`.
- **False positives on figurative reading.** The 🏇 emoji is repeatedly flagged as an "image of an animal" prohibited by Article 27 in gambling advertising. It is an emoji in a text ad, not an image.
- **The verdict is prose, not a legal report.** A practising advertising lawyer who reviewed the output judged it "an essay — substantively correct, but of no legal value," wanting instead a structured, per-requirement list with red flags expanded, everything else collapsed, and citations. The prose format is a known shortcoming, not a design choice.
- **Reply language is inconsistent in older paths.** The verdict should follow the language of the ad; early versions answered Russian ads in English.
- **Text only.** No images, audio, video, or batch upload. Real review work involves banner sets, where the point is to catch small details (for example, that a mandatory disclaimer occupies less than the required share of the frame) — out of reach for a text pipeline.
- **Retrieval is capped at `top_k=10` per pass.** With ~50 distinct requirements in the bundled law and ~400+ extracted, relevant requirements can be missed. The cap was never tuned, and certainly not for any other law.
- **Any exception becomes "Sorry, I encountered an error while processing your request."** Failures mid-chain are not distinguished or retried.
- **Accuracy was never measured.** There is no evaluation set and no tests. For comparison, the practitioners involved treated ~80% correctness as the industry norm for assistants of this kind.
- **No conversation timeout or `/cancel`.** A user who stops answering questions stays mid-chain until they send another message; the only way out is to answer the remaining questions.

## Ideas not implemented

Discussed and deliberately left out of the prototype:

- A structured report: ad category, what the ad contains, the full list of applicable requirements with red flags expanded and the rest collapsed, what to fix, and a source link per item.
- An experimental "fix it" button that rewrites the ad into compliance.
- Audio ads via Whisper, images, and video by slicing frames for analysis.
- Batch review of many creatives at once.
- Storing several editions of the law side by side and selecting by date, so an ad can be judged against the law as it stood when it ran.
- Widening the knowledge base beyond the statute to regulator guidance and court decisions, so the analysis can cite precedent — for the Russian law, FAS letters and court rulings.
- Inline buttons for the yes/no questions, so the user never has to type.
- Checking against registries of extremist organisations and foreign agents, which requires external data sources.
- Holding several jurisdictions at once, rather than one law per index. Swapping the law works; serving many of them side by side, and keeping each current, was never attempted.
- A language-neutral ingestion parser, so swapping the law needs no code change at all.

## The bundled law text

`law.txt` is a consolidated text of Russian Federal Law No. 38-FZ of 13 March 2006 "On Advertising", including amendments **up to and including No. 411-FZ of 23 November 2024**. The law has been amended since; this copy is not guaranteed to reflect the current version.

Note that this is a *consolidated* edition — the statute with amendments already merged in and marked inline as `(в ред. Федерального закона от …)`. The official publication portal [pravo.gov.ru](http://pravo.gov.ru) and [government.ru](http://government.ru/docs/all/98086/) publish the original act and each amending act separately rather than in this form, so this particular copy did not come from either; it carries the formatting of a consolidated edition of the kind produced by legal-reference databases. If that matters to you, or if you need an up-to-date edition, re-source the text yourself and replace `law.txt`, then re-run `python scraper.py`.

Official documents of state authorities, including laws, are not subject to copyright under Article 1259(6)(1) of the Civil Code of the Russian Federation, so the statutory text itself is free to redistribute. A compiler of a consolidated edition may nonetheless assert rights in the compilation (Articles 1260 and 1333-1334 of the Civil Code), which is a further reason to source the text from the official portal if you intend to rely on this repository commercially. The MIT license in [LICENSE](LICENSE) covers the code in this repository, not the text of the statute.

## Credits

Built by Renat Sarymsakov, with requirements, legal review, and test material from a practising advertising lawyer and an advertising-industry practitioner, both of whom agreed to this project being open-sourced.

## Contributing

Issues and pull requests are welcome.

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a pull request

## License

[MIT](LICENSE) © 2025-2026 Renat Sarymsakov

This covers the code and documentation written for this repository. Two things it does not cover:

- The text of the bundled statute in `law.txt` — see [The bundled law text](#the-bundled-law-text).
- The third-party ad quoted in [Examples](#examples), which belongs to its rights holders.

Dependencies keep their own licenses. All of those in `requirements.txt` are permissive (MIT, BSD, Apache-2.0) except [`python-telegram-bot`](https://github.com/python-telegram-bot/python-telegram-bot), which is **LGPLv3**. None of its code is copied into this repository — it is only imported — so MIT on the code here is compatible with it. If you redistribute a container image built from the `Dockerfile`, note that the image bundles `python-telegram-bot` itself, and LGPLv3 obligations (carrying the license notice, and allowing the library to be replaced) attach to that image.
