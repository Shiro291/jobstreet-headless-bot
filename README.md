# Headless Jobstreet Automation Bot

An asynchronous, fault-tolerant Python/Playwright automation suite designed to navigate dynamic DOM structures, parse complex job application states, and execute headless submissions at scale. 

## Features
- **Deterministic State Tracking:** Parses single-page application (SPA) state changes without relying on fragile hard-coded sleep timers.
- **Async DOM Parsing:** Utilizes Scrapling and asyncio to rapidly extract required form fields and map them to localized data stores.
- **LLM Qualification Engine:** Injects unknown application questions into a local/cloud LLM to determine the mathematically optimal multiple-choice response based on pre-defined resume embeddings.
- **Session Persistence:** Maintains authenticated browser contexts to bypass repeated anti-bot challenges and CAPTCHA walls.

## Setup Instructions (Plug & Play)

### 1. Requirements
- Python 3.10+
- Playwright (`pip install playwright` & `playwright install`)
- A valid `database.db` SQLite schema (included in `schema/`)

### 2. Installation
```bash
git clone https://github.com/Shiro291/jobstreet-headless-bot.git
cd jobstreet-headless-bot
pip install -r requirements.txt
```

### 3. Configuration
Copy the example environment file and insert your configuration:
```bash
cp .env.example .env
```
Ensure you have your Jobstreet session cookies or credentials defined. **Never commit your `.env` file.**

### 4. Execution
To run the automated application solver:
```bash
python solver.py --headless --target "Python Backend Developer"
```

## Architecture
This project demonstrates advanced headless architecture. It does not rely on simple Selenium clicks. It intercepts XHR requests, parses underlying React component states, and uses AI to map semantic questions to deterministic answers. 

*Designed and maintained by Fathan Faqih Ali.*
