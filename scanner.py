from typing import AsyncGenerator
from scrapling import Fetcher
from core.job import Job
from utils.logger import get_logger
import asyncio
import re

logger = get_logger("Scanner")

class JobScanner:
    def __init__(self, browser=None, tracker=None):
        self.browser = browser # Keep signature for compatibility
        self.tracker = tracker
        # Do not initialize fetcher here, we'll do it in the thread to avoid Playwright loop issues
        self.fetcher = None

    async def scan(self, keyword: str, location: str = "", limit: float = 10, exclusions: list = None) -> AsyncGenerator[Job, None]:
        # Clean up keyword and location for URL
        url_keyword = keyword.replace(" ", "-").lower()
        if location:
            url_location = location.replace(" ", "-").lower()
            base_url = f"https://id.jobstreet.com/id/{url_keyword}-jobs/in-{url_location}"
        else:
            base_url = f"https://id.jobstreet.com/id/{url_keyword}-jobs"
            
        seen_ids = set()
        page_num = 1
        yielded_count = 0
        
        while yielded_count < limit:
            url = f"{base_url}?page={page_num}" if page_num > 1 else base_url
            logger.info(f"Scanning for jobs at {url} using Scrapling")
            
            try:
                def fetch_url(target_url):
                    if not self.fetcher:
                        self.fetcher = Fetcher()
                    return self.fetcher.get(target_url)
                
                page = await asyncio.to_thread(fetch_url, url)
                
                # Verify that Jobstreet didn't redirect us to the global feed
                final_url = page.url.split('?')[0].rstrip('/')
                if final_url.endswith("/jobs") and keyword:
                    logger.error(f"Jobstreet rejected the search parameters and redirected to the default feed.")
                    logger.error(f"Please verify your keyword '{keyword}' and location '{location}' are spelled correctly.")
                    logger.error(f"Target URL: {url} -> Redirected to: {page.url}")
                    break
                    
            except Exception as e:
                logger.error(f"Failed to fetch page {page_num}: {e}")
                break
                
            cards = page.css('article[data-automation="normalJob"]')
            
            if not cards:
                logger.warning(f"No job cards found on page {page_num}.")
                break
                
            logger.info(f"Found {len(cards)} job cards on page {page_num}")
            
            new_cards_this_page = 0
            new_jobs_this_page = []
            
            for card in cards:
                titles = card.css('a[data-automation="jobTitle"]')
                companies = card.css('a[data-automation="jobCompany"]')
                locs = card.css('a[data-automation="jobLocation"]')
                
                title_elem = titles[0] if titles else None
                company_elem = companies[0] if companies else None
                loc_elem = locs[0] if locs else None
                
                title = title_elem.text.strip() if title_elem else ""
                card_url = "https://id.jobstreet.com" + title_elem.attrib.get('href', '') if title_elem else ""
                company = company_elem.text.strip() if company_elem else ""
                location_val = loc_elem.text.strip() if loc_elem else ""
                
                job_id = card_url.split("/")[-1].split("?")[0] if card_url else f"unknown-{len(seen_ids)}"
                if job_id in seen_ids and job_id != "unknown-0":
                    continue
                seen_ids.add(job_id)
                
                # Check DB Tracker
                if self.tracker and self.tracker.is_processed(job_id):
                    logger.debug(f"Skipping {job_id} - already in history DB.")
                    continue
                    
                new_cards_this_page += 1
                
                # Pre-check basic exclusions based on title/company
                skip = False
                skip_reason = ""
                if exclusions:
                    for ex in exclusions:
                        if ex.lower() in title.lower() or ex.lower() in company.lower():
                            skip = True
                            skip_reason = f"Excluded keyword '{ex}' found in title/company"
                            break
                            
                # Save basic skips instantly and avoid fetching detail
                if skip:
                    if self.tracker:
                        self.tracker.record(job_id, title, company, "SKIPPED", skip_reason, "Skipped before full desc load")
                    logger.info(f"Pre-skipped {job_id}: {skip_reason}")
                    continue
                        
                new_jobs_this_page.append(Job(
                    id=job_id,
                    title=title,
                    company=company,
                    location=location_val,
                    url=card_url,
                    apply_url=card_url
                ))
                
            # Background fetch job details
            async def fetch_job_details(job: Job):
                try:
                    def _fetch():
                        if not self.fetcher:
                            self.fetcher = Fetcher()
                        return self.fetcher.get(job.url)
                    
                    detail_page = await asyncio.to_thread(_fetch)
                    
                    # Extract description
                    desc_elems = detail_page.css('div[data-automation="jobAdDetails"]')
                    if desc_elems:
                        job.description = ' '.join(desc_elems[0].xpath('.//text()').getall()).strip()
                    
                    # Extract salary if not already found
                    if not job.salary:
                        sal_elems = detail_page.css('[data-automation="job-detail-salary"]')
                        if sal_elems:
                            job.salary = sal_elems[0].text
                            
                    # Check for external apply button
                    ext_btns = detail_page.css('a[data-automation="job-detail-apply-external"]')
                    if ext_btns:
                        job.is_external = True
                        job.skipped = True
                        job.skipped_reason = "External application link"
                    
                    # Some external links use standard apply buttons but say "Lamar di situs"
                    apply_btns = detail_page.css('a[data-automation="job-detail-apply"]')
                    if not apply_btns:
                        # Fallback for generic buttons
                        all_btns = detail_page.css('button')
                        apply_btns = [b for b in all_btns if "lamaran cepat" in b.text.lower() or "apply" in b.text.lower()]
                        
                    if apply_btns:
                        btn_text = apply_btns[0].text.lower()
                        if "situs" in btn_text or "site" in btn_text:
                            job.is_external = True
                            job.skipped = True
                            job.skipped_reason = "External site text in apply button"
                            
                    # Keyword drift prevention
                    if not job.skipped and keyword:
                        k_low = keyword.strip().lower()
                        t_low = job.title.lower()
                        
                        if "guru" in k_low:
                            valid_words = ["guru", "teacher", "tutor", "pengajar", "lecturer", "educator", "pendidik", "instructor", "fasilitator"]
                            if not any(w in t_low for w in valid_words):
                                job.skipped = True
                                job.skipped_reason = f"drifted missing {k_low} (no valid synonym)"
                        else:
                            words = k_low.split()
                            if not any(w in t_low for w in words):
                                job.skipped = True
                                job.skipped_reason = f"drifted missing {k_low}"

                    # Check strict exclusions against full description and title
                    if exclusions and not job.skipped:
                        text_to_check = f"{job.title} {job.description}".lower()
                        for ex in exclusions:
                            ex_clean = ex.strip()
                            if not ex_clean:
                                continue
                            # Use regex word boundaries so 'sales' doesn't match 'salesforce'
                            pattern = ex_clean if ex_clean.startswith(r"\b") else rf"\b{re.escape(ex_clean)}\b"
                            if re.search(pattern, text_to_check):
                                job.skipped = True
                                job.skipped_reason = f"Excluded keyword '{ex_clean}' found"
                                break
                                
                except Exception as e:
                    logger.debug(f"Failed to fetch details for {job.id}: {e}")

            if new_jobs_this_page:
                logger.info(f"Fast-fetching descriptions for {len(new_jobs_this_page)} jobs concurrently...")
                await asyncio.gather(*(fetch_job_details(j) for j in new_jobs_this_page))
                
                # Yield jobs one by one and save skipped ones to DB permanently
                for j in new_jobs_this_page:
                    if yielded_count >= limit:
                        break
                        
                    if j.skipped:
                        logger.warning(f"Skip ({j.skipped_reason}): {j.title}")
                        if self.tracker:
                            self.tracker.record(j.id, j.title, j.company, "SKIPPED", j.skipped_reason, j.description or "Failed to load desc")
                        continue
                        
                    yield j
                    yielded_count += 1
                
            if new_cards_this_page == 0:
                logger.warning(f"No more new job cards found on page {page_num}. Ending scan.")
                break
                
            page_num += 1
            
        logger.success(f"Successfully scraped and yielded {yielded_count} jobs.")
