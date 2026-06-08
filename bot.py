import argparse
import asyncio
import math
import os
from dotenv import load_dotenv

load_dotenv()

from infrastructure.browser import BrowserManager
from application.scanner import JobScanner
from application.solver import JobSolver
from infrastructure.question_bank import QuestionBank
from infrastructure.tracker import JobTracker
from utils.logger import get_logger

logger = get_logger("Main")

async def run_bot(keyword: str, location: str = "", dry_run: bool = False, limit: float = 10, exclusions: list = None, setup_login: bool = False, auto_mode: bool = True, strict_mode: bool = False, test_mode: bool = False, interactive_mode: bool = False, brute_force: bool = False):
    logger.info("Initializing Jobstreet Bot V2...")
    
    browser = BrowserManager()
    
    qb_path = "question_bank_test.json" if test_mode else None
    question_bank = QuestionBank(custom_path=qb_path)
    
    tracker_path = "bot_state_test.db" if test_mode else "bot_state.db"
    tracker = JobTracker(db_path=tracker_path)
    
    await browser.start()
    
    # LLM Auto-Answer Configuration
    llm_enabled = False
    if os.getenv("OPENAI_API_KEY"):
        llm_enabled = True
        logger.info("LLM Auto-Answer mode ACTIVATED (OpenAI key found).")
    else:
        logger.warning("OPENAI_API_KEY not found in .env. LLM Auto-Answer DISABLED.")

    if setup_login:
        logger.info("Setup login mode activated. Navigating to Jobstreet...")
        await browser.page.goto("https://id.jobstreet.com/")
        try:
            await asyncio.to_thread(input, "\n[LOGIN REQUIRED] Please log in on the browser window. Press Enter here when you are done...")
            logger.success("Login step complete. Your profile is saved. You can now run the bot normally.")
        except Exception as e:
            logger.error(f"Error during login setup: {e}")
        finally:
            await browser.stop()
        return

    scanner = JobScanner(browser, tracker=tracker)
    manual_mode = not auto_mode
    solver = JobSolver(
        browser, 
        question_bank,
        auto_mode=not manual_mode,
        strict_mode=strict_mode,
        exclusions=exclusions,
        dry_run=dry_run,
        llm_enabled=llm_enabled
    )
    solver.interactive_mode = interactive_mode
    solver.brute_force_mode = brute_force
    
    successful_jobs = []
    skipped_jobs = []
    
    try:
        async for job in scanner.scan(keyword, location=location, limit=limit, exclusions=exclusions):
            result = await solver.apply(job)
            
            if result.reason == "RETRY_LOGIN":
                result = await solver.apply(job)
                
            if result.success:
                logger.success(f"Application successful for {job.title}")
                successful_jobs.append(job)
                tracker.record(job.id, job.title, job.company, "APPLIED", "Success", getattr(job, 'description', ''))
            else:
                logger.error(f"Application failed/skipped for {job.title}. Reason: {result.reason}")
                tracker.record(job.id, job.title, job.company, "FAILED/SKIPPED", result.reason, getattr(job, 'description', ''))
                if job.skipped or "Excluded" in result.reason:
                    skipped_jobs.append(job)
                    
            # Add delay to avoid rate limiting
            await asyncio.sleep(3)
            
        # End of session review
        if skipped_jobs and not dry_run:
            print("\n--- End of Session Review ---")
            print(f"{len(successful_jobs)} Successful Applications.")
            print(f"{len(skipped_jobs)} Skipped Jobs:")
            for idx, sj in enumerate(skipped_jobs, start=1):
                print(f"[{idx}] {sj.title} @ {sj.company} | Reason: {sj.skipped_reason or 'Skipped'}")
                print(f"    Link: {sj.url}")
                
            print("\nYou can force apply to specific skipped jobs.")
            override_input = await asyncio.to_thread(input, "Enter job indexes to force apply (e.g. '1,3,4-7') or press Enter to skip: ")
            
            if override_input.strip():
                # Parse indices
                to_apply = set()
                for part in override_input.split(','):
                    part = part.strip()
                    if '-' in part:
                        try:
                            start, end = map(int, part.split('-'))
                            to_apply.update(range(start, end + 1))
                        except ValueError:
                            pass
                    elif part.isdigit():
                        to_apply.add(int(part))
                
                valid_jobs = [sj for idx, sj in enumerate(skipped_jobs, start=1) if idx in to_apply]
                for job in valid_jobs:
                    logger.info(f"Force applying to: {job.title}")
                    result = await solver.apply(job, force=True)
                    if result.success:
                        logger.success(f"Force application successful for {job.title}")
                        successful_jobs.append(job)
                    else:
                        logger.error(f"Force application failed for {job.title}: {result.reason}")
                        
        # Write final log
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open("session_log.txt", "a", encoding="utf-8") as f:
            f.write(f"\n--- SESSION LOG [{timestamp}] ---\nKeyword: {keyword}\n")
            f.write(f"Successful: {len(successful_jobs)}\n")
            for j in successful_jobs:
                f.write(f"SUCCESS: {j.title} @ {j.company} | {j.url}\n")
            f.write("\n")
            for j in skipped_jobs:
                f.write(f"SKIPPED: {j.title} @ {j.company} | {j.url} | Reason: {j.skipped_reason}\n")
            f.write("--------------------------------\n")
            
    except KeyboardInterrupt:
        logger.warning("Bot interrupted by user.")
    except Exception as e:
        logger.exception(f"Fatal error encountered: {e}")
    finally:
        await browser.stop()
        
if __name__ == "__main__":
    import questionary
    
    parser = argparse.ArgumentParser(description="Jobstreet Automated Bot V2")
    parser.add_argument("keyword", nargs="?", default="", help="Job search keyword")
    parser.add_argument("--interactive", action="store_true", help="Force interactive mode")
    parser.add_argument("--setup-login", action="store_true", help="Open browser to Jobstreet to manually log in")
    parser.add_argument("--limit", type=float, default=10, help="Maximum number of jobs to apply to")
    parser.add_argument("--dry-run", action="store_true", help="Run without applying")
    parser.add_argument("--strict-mode", action="store_true", help="Enable strict exclusion scanning")
    parser.add_argument("--exclude", type=str, default="", help="Comma separated exclusions")
    parser.add_argument("--location", type=str, default="", help="Job location")
    
    parser.add_argument("--brute-force", action="store_true", help="Auto-answer randomly for unknown questions")
    parser.add_argument("--test-mode", action="store_true", help="Use test DB and test QuestionBank")
    
    args = parser.parse_args()
    
    if args.setup_login:
        asyncio.run(run_bot("", setup_login=True))
    elif args.keyword:
        exclusions = [x.strip() for x in args.exclude.split(",")] if args.exclude else []
        asyncio.run(run_bot(
            keyword=args.keyword, 
            location=args.location,
            dry_run=args.dry_run, 
            limit=args.limit, 
            exclusions=exclusions,
            strict_mode=args.strict_mode,
            test_mode=args.test_mode,
            interactive_mode=args.interactive,
            brute_force=args.brute_force
        ))
    else:
        print("\n--- Jobstreet Auto-Apply Bot ---")
        keyword = questionary.text("Job Keyword (e.g., Python Developer):").ask()
        location = questionary.text("Location (e.g., Jakarta, leave empty for anywhere):").ask()
        limit_str = questionary.text("How many jobs to apply to? (Leave empty for ALL):").ask()
        exclusions_raw = questionary.text("Keywords to exclude (comma separated, leave empty if none):").ask()
        strict_mode = questionary.confirm("Enable Strict Mode? (Scans full job descriptions for exclusions)").ask()
        brute_force = questionary.confirm("Enable Brute Force Mode? (Randomly answers unknown questions)").ask()
        
        mode = questionary.select(
            "Select Bot Mode:",
            choices=[
                "Auto Mode (Uses Question Bank, prompts when unknown)",
                "Dry Run (Only scans, no apply)"
            ]
        ).ask()
        
        dry_run = "Dry Run" in mode
        auto_mode = True # The user corrected this: Auto mode always prompts on unknown.
        interactive_mode = True
        test_mode = questionary.confirm("Enable Test Mode? (Uses isolated DB and Question Bank)").ask()
        
        if not limit_str.strip():
            limit_val = math.inf
        else:
            try:
                limit_val = float(limit_str)
            except ValueError:
                limit_val = 10.0
            
        exclusions = [x.strip() for x in exclusions_raw.split(",")] if exclusions_raw else []
        
        asyncio.run(run_bot(
            keyword=keyword,
            location=location,
            dry_run=dry_run,
            limit=limit_val,
            exclusions=exclusions,
            setup_login=False,
            auto_mode=auto_mode,
            strict_mode=strict_mode,
            test_mode=test_mode,
            interactive_mode=interactive_mode,
            brute_force=brute_force
        ))
