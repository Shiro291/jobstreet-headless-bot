import asyncio
from typing import Optional, List
from core.job import Job, ApplicationResult
from infrastructure.browser import BrowserManager
from infrastructure.dom_mapper import JobstreetDOMMapper
from infrastructure.question_bank import QuestionBank
from infrastructure.llm_engine import LLMEngine
from utils.logger import get_logger

logger = get_logger("Solver")

class JobSolver:
    def __init__(self, browser: BrowserManager, question_bank: QuestionBank, auto_mode: bool = True, strict_mode: bool = False, exclusions: list = None, dry_run: bool = False, llm_enabled: bool = False):
        self.browser = browser
        self.question_bank = question_bank
        self.auto_mode = auto_mode
        self.strict_mode = strict_mode
        self.exclusions = exclusions or []
        self.dry_run = dry_run
        self.mapper = JobstreetDOMMapper(browser.page)
        self.llm_enabled = llm_enabled
        self.llm_engine = LLMEngine() if llm_enabled else None

    async def apply(self, job: Job, force: bool = False) -> ApplicationResult:
        logger.info(f"Applying for job: {job.title} at {job.company}")
        
        if not job.url:
            return ApplicationResult(job_id=job.id, success=False, reason="No URL provided")
            
        try:
            # Check if current page is closed, if so, open a new one
            if getattr(self.browser.page, 'is_closed', lambda: False)():
                self.browser.page = await self.browser.context.new_page()
            
            # We are using Playwright
            self.mapper.page = self.browser.page
            
            try:
                await self.browser.page.goto(job.url, timeout=30000, wait_until="domcontentloaded")
            except Exception as e:
                logger.warning(f"Navigation issue: {e}")
                
            # Wait for DOM content to settle instead of hard timeout
            try:
                await self.browser.page.wait_for_selector('div[data-automation="jobAdDetails"], a[data-automation="job-detail-apply"]', timeout=10000)
            except Exception:
                pass
            
            # Check if job was marked as external by scanner
            if getattr(job, 'is_external', False):
                return ApplicationResult(job_id=job.id, success=False, reason="External application link (Scanned)")
                
            # Strict mode: check description for exclusions
            if self.strict_mode and not force and self.exclusions:
                try:
                    desc_loc = self.browser.page.locator('div[data-automation="jobAdDetails"]')
                    if await desc_loc.count() > 0:
                        desc_text = await desc_loc.first.text_content()
                        if desc_text:
                            import re
                            desc_lower = desc_text.lower()
                            for ex in self.exclusions:
                                ex_clean = ex.strip()
                                if not ex_clean: continue
                                pattern = ex_clean if ex_clean.startswith(r"\b") else rf"\b{re.escape(ex_clean)}\b"
                                if re.search(pattern, desc_lower):
                                    reason = f"Excluded keyword '{ex_clean}' found in description"
                                    logger.warning(f"Strict Mode skipped: {job.title} - {reason}")
                                    job.skipped = True
                                    job.skipped_reason = reason
                                    return ApplicationResult(job_id=job.id, success=False, reason=reason)
                except Exception as e:
                    logger.warning(f"Failed to read job description for strict mode: {e}")
            
            # Check for external apply link (job-detail-apply-external)
            ext_btns = self.browser.page.locator('a[data-automation="job-detail-apply-external"]')
            if await ext_btns.count() > 0:
                logger.warning("Skipping external application link")
                job.is_external = True
                return ApplicationResult(job_id=job.id, success=False, reason="External application link")
                
            # Look for normal apply button
            apply_btns = self.browser.page.locator('a[data-automation="job-detail-apply"], button[data-automation="job-detail-apply"]')
            if await apply_btns.count() == 0:
                # Try fallback texts
                apply_btns = self.browser.page.locator("button:has-text('Lamaran Cepat'), button:has-text('Apply')")
                if await apply_btns.count() == 0:
                    return ApplicationResult(job_id=job.id, success=False, reason="Apply button not found (might be external or already applied)")
                    
            btn_text = await apply_btns.first.text_content()
            if btn_text and ("situs" in btn_text.lower() or "site" in btn_text.lower()):
                logger.warning("Skipping external application link (based on button text)")
                return ApplicationResult(job_id=job.id, success=False, reason="External site text in button")
                
            # Determine if it opens in a new tab, navigates the current tab, or is a same-page modal
            tag_name = await apply_btns.first.evaluate("el => el.tagName.toLowerCase()")
            if tag_name == "a":
                href = await apply_btns.first.get_attribute("href")
                target_attr = await apply_btns.first.get_attribute("target")
                
                if target_attr == "_blank":
                    logger.info("Apply link opens a new tab.")
                    async with self.browser.context.expect_page() as new_page_info:
                        await apply_btns.first.click(force=True)
                    new_page = await new_page_info.value
                    await new_page.wait_for_load_state("domcontentloaded")
                    self.browser.page = new_page
                    self.mapper.page = new_page
                else:
                    logger.info("Apply link navigates current tab.")
                    if href:
                        if href.startswith("/"):
                            href = "https://id.jobstreet.com" + href
                        await self.browser.page.goto(href, wait_until="domcontentloaded")
                    else:
                        await apply_btns.first.click(force=True)
                        await self.browser.page.wait_for_load_state("domcontentloaded")
            else:
                logger.info("Apply button is likely a same-page modal.")
                await apply_btns.first.click(force=True)
                
            unanswered = []
            
            # Wait for the modal or new page to populate
            try:
                await self.browser.page.wait_for_selector('button[data-automation="Continue"], button[data-automation="SubmitApplication"], #errorPanel', timeout=5000)
            except Exception:
                pass
            
            # Application loop
            iterations = 0
            last_url = ""
            while iterations < 15:
                current_url = self.browser.page.url
                if current_url != last_url:
                    iterations = 0
                    last_url = current_url
                    
                if iterations == 3:
                    logger.error("DUMPING HTML BECAUSE OF REPEATED LOOPS")
                    html = await self.browser.page.content()
                    with open("failed_stage.html", "w", encoding="utf-8") as f:
                        f.write(html)
                    logger.error("HTML saved to failed_stage.html")
                
                if '/apply' in current_url:
                    stage_name = current_url.split('/apply')[-1].strip('/')
                    if not stage_name: stage_name = "stage-1-resume"
                    if iterations == 0:  # Only log stage entry once
                        logger.info(f"--- Processing Stage: {stage_name.upper()} ---")
                
                current_url_lower = current_url.lower()
                
                if "jobstreet.com" not in current_url_lower and "accounts.google" not in current_url_lower:
                    logger.warning(f"Redirected to external site: {current_url_lower}. Skipping.")
                    return ApplicationResult(job_id=job.id, success=False, reason="Redirected to external site")
                
                if "login" in current_url_lower or "signin" in current_url_lower or "accounts.google" in current_url_lower:
                    try:
                        logger.warning("\n[LOGIN BLOCKED] The bot was redirected to a login page. Please log in manually on the opened browser window.")
                        await asyncio.to_thread(input, "Press Enter here after you have successfully logged in... ")
                        logger.info("Retrying application after login...")
                        return ApplicationResult(job_id=job.id, success=False, reason="RETRY_LOGIN")
                    except Exception as e:
                        return ApplicationResult(job_id=job.id, success=False, reason="Blocked by Login page (Profile session expired or not logged in)")
                
                questions = await self.mapper.extract_questions()
                for q in questions:
                    try:
                        answer = self.question_bank.get_answer(q["label"])
                        if answer:
                            await self.mapper.solve_question(q, answer)
                            logger.info(f"Answered: {q['label']} -> {answer}")
                        else:
                            unanswered.append(q["label"])
                    except Exception as e:
                        if "QuestionBankMissError" in str(type(e)):
                            if getattr(self, 'llm_enabled', False) and self.llm_engine:
                                logger.info(f"[LLM] Formulating answer for unknown question: '{q['label']}'")
                                options = q.get('options', [])
                                answer = await self.llm_engine.generate_answer(q["label"], options=options if options else None)
                                
                                logger.success(f"[LLM] Answered: '{answer}'")
                                self.question_bank.add_answer(q["label"], answer, is_bruteforce=False)
                                await self.mapper.solve_question(q, answer)
                                
                            elif getattr(self, 'brute_force_mode', False):
                                import random
                                options = q.get('options', [])
                                if options:
                                    ans_val = random.choice(options)
                                    logger.warning(f"[BRUTE FORCE] Randomly selected '{ans_val}' for '{q['label']}'")
                                else:
                                    ans_val = "-"
                                    logger.warning(f"[BRUTE FORCE] Entered fallback text '{ans_val}' for '{q['label']}'")
                                
                                self.question_bank.add_answer(q["label"], ans_val, is_bruteforce=True)
                                await self.mapper.solve_question(q, ans_val)
                            elif getattr(self, 'interactive_mode', False):
                                logger.warning(f"\n[INTERACTIVE MODE] Missing answer for: '{q['label']}'")
                                logger.info(f"Options (if any): {q.get('options', 'None')}")
                                # Prompt user
                                user_ans = await asyncio.to_thread(input, f"Enter answer for '{q['label']}': ")
                                if user_ans.strip():
                                    self.question_bank.add_answer(q["label"], user_ans.strip())
                                    await self.mapper.solve_question(q, user_ans.strip())
                                else:
                                    unanswered.append(q["label"])
                            else:
                                logger.error(f"Error solving question {q['label']} (Not in Bank): {e}")
                                unanswered.append(q["label"])
                        else:
                            logger.error(f"Error solving question {q['label']}: {e}")
                            unanswered.append(q["label"])
                
                if unanswered:
                    logger.warning(f"Missing answers for: {unanswered}. Aborting to avoid wrong submission.")
                    return ApplicationResult(job_id=job.id, success=False, reason="Missing answers", unanswered_questions=unanswered)
                    
                submit = self.browser.page.locator('button[data-automation="SubmitApplication"]').first
                if not await submit.count():
                    import re
                    submit = self.browser.page.get_by_role("button", name=re.compile(r"^(Kirim lamaran|Kirim|Submit application|Submit)$", re.IGNORECASE)).first

                nxt = self.browser.page.locator('button[data-automation="Continue"], button[data-automation="ReviewApplication"]').first
                if not await nxt.count():
                    import re
                    nxt = self.browser.page.get_by_role("button", name=re.compile(r"^(Lanjut|Lanjutkan|Next|Review application|Tinjau lamaran|Simpan dan lanjut|Save and continue|Review|Simpan|Save)$", re.IGNORECASE)).first

                try:
                    await submit.or_(nxt).wait_for(state="attached", timeout=3000)
                except Exception:
                    pass
                    
                async def safe_click(locator, retries=3, timeout=3000):
                    for i in range(retries):
                        try:
                            await locator.wait_for(state="visible", timeout=timeout)
                            await locator.click(timeout=timeout)
                            return True
                        except Exception as e:
                            try:
                                await locator.evaluate("el => el.click()")
                                return True
                            except Exception: pass
                            import asyncio
                            await asyncio.sleep(1)
                    return False

                is_submit = await submit.is_visible()
                if is_submit:
                    if self.dry_run:
                        logger.success(f"Dry run mode: Reached final submission step. Aborting application.")
                        return ApplicationResult(job_id=job.id, success=True)
                    else:
                        try:
                            logger.info("Clicking submit and waiting...")
                            await safe_click(submit)
                            try:
                                await self.browser.page.wait_for_url("**/apply/success*", timeout=4000)
                                return ApplicationResult(job_id=job.id, success=True)
                            except Exception:
                                logger.error(f"Validation Error: Final URL = {self.browser.page.url}")
                                return ApplicationResult(job_id=job.id, success=False, reason="Validation failed post-submit")
                        except Exception as e:
                            logger.warning(f"Submit error: {e}")
                            return ApplicationResult(job_id=job.id, success=False, reason=f"Submit error: {e}")

                is_nxt = await nxt.is_visible()
                if is_nxt:
                    is_disabled = await nxt.is_disabled()
                    if is_disabled:
                        logger.error("Lanjut button is disabled — a required field was missed!")
                        return ApplicationResult(job_id=job.id, success=False, reason="Lanjut button disabled")
                    
                    logger.info("Clicking Lanjut/Next...")
                    old_url = self.browser.page.url
                    await safe_click(nxt)
                    
                    try:
                        # Zero-Sleep dynamic wait: wait until URL changes OR error panel appears OR it is a final success page
                        await self.browser.page.wait_for_function(f'''() => {{
                            return window.location.href !== "{old_url}" || 
                                   document.querySelector("#errorPanel") !== null ||
                                   document.querySelector('button[data-automation="SubmitApplication"]') !== null
                        }}''', timeout=5000)
                    except Exception:
                        pass
                        
                    # Check for validation errors
                    error_panel = self.browser.page.locator('#errorPanel')
                    if await error_panel.count() > 0:
                        error_items = await error_panel.locator('ul li').all()
                        error_texts = []
                        for item in error_items:
                            text = await item.inner_text()
                            clean_text = text.split(' - ')[0].strip()
                            error_texts.append(clean_text)
                            
                        if error_texts:
                            unmapped_qs = ", ".join(error_texts)
                            logger.error(f"Validation error blocking progress! Unmapped/unanswered questions: {unmapped_qs}")
                            return ApplicationResult(job_id=job.id, success=False, reason=f"Validation error on unmapped questions: {unmapped_qs}")
                        else:
                            logger.error("Validation error panel found, but could not extract question texts.")
                            return ApplicationResult(job_id=job.id, success=False, reason="Validation error (unknown questions)")
                    
                    iterations += 1
                    continue
                    
                logger.warning(f"No Lanjut/Kirim on {current_url.split('/')[-1]}")
                iterations += 1
                await asyncio.sleep(0.5)
                
            return ApplicationResult(job_id=job.id, success=False, reason="Application loop timed out (max 15 steps)")
            
        except Exception as e:
            logger.error(f"Application failed: {e}")
            return ApplicationResult(job_id=job.id, success=False, reason=str(e))
