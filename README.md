# Jobstreet Headless Bot

An autonomous, stateful CLI bot that automatically searches, qualifies, and applies to jobs on Jobstreet using stealth browser automation and LLM-powered dynamic question answering.

Built as a "plug-and-play" solution, the bot runs locally, handles its own persistent state (to avoid double applications), and actively evades bot detection mechanisms.

## Key Features
- **LLM Auto-Answer**: Uses OpenAI (`gpt-4o`) to dynamically answer new/unknown employer questions based on your resume.
- **Idempotency**: Uses an SQLite database (`bot_state.db`) to track all successful/failed applications. It will never apply to the same job twice.
- **Stealth Automation**: Fully bypasses anti-bot measures by utilizing Playwright along with advanced stealth patterns.
- **Interactive CLI**: Powered by `questionary` for an easy, terminal-based user interface.

## Quick Setup (Plug and Play)

1. **Install Requirements**
   Ensure you have Python 3.9+ installed.
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Environment Variables**
   Rename `.env.example` to `.env` and add your OpenAI API key (used for auto-answering questions).
   ```env
   OPENAI_API_KEY=sk-your-openai-key
   ```

3. **Provide Your Context**
   Create a file named `job_desc.txt` in the root directory and paste your resume/CV text inside it. The AI will use this file as its knowledge base when answering employer questions.

4. **Initial Login Setup**
   Run the setup mode to log into your Jobstreet account manually. The session cookies will be saved securely so you never have to log in again.
   ```bash
   python bot.py --setup-login
   ```
   *(A browser window will open. Log in, then press Enter in your terminal when done).*

5. **Run the Bot**
   ```bash
   python bot.py
   ```
   Follow the interactive prompts to define your search keyword, location, and limits!

## Architecture & Skills
This project was structured using the following design patterns:
- **`playwright-skill`**: For robust DOM parsing and headless interaction.
- **`workflow-automation`**: For the SQLite idempotency tracking layer (Zero-Fault Pipeline).
- **`backend` & `python-pro`**: Clean separation of concerns (Core Models, Infrastructure, Application logic).

## Credits & Acknowledgements
- **Scrapling**: Huge credit to [darvincisec/scrapling](https://github.com/darvincisec/scrapling) for the foundational stealth scraping architecture. This project builds upon those evasion techniques.
- **Playwright**: For the browser automation engine.
