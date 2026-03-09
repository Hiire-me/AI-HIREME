 System Architecture
Frontend (HTML + CSS + Vanilla JS)

Dashboard — live job feed, match scores, application status board
Resume Builder / Uploader — drag-drop PDF/DOCX parser + skill extractor
Preference Wizard — role, salary, location, remote/hybrid, culture filters
Auto-Apply Controls — on/off toggle, approval queue (semi-auto mode), blacklist companies
Application Tracker — Kanban board: Scraped → Matched → Applied → Interview → Offer
Analytics Panel — match rate, response rate, best-performing resume sections

Backend (Python)

FastAPI or Flask as REST API
Resume Parser — pdfminer, python-docx, spaCy NER to extract skills, experience, education
Job Scraper Engine — async scraping with httpx + BeautifulSoup / Playwright
ML Matching Engine — cosine similarity via sentence-transformers or OpenAI embeddings
Auto-Apply Bot — Playwright to fill forms on Greenhouse/Lever
Scheduler — APScheduler or Celery + Redis for background jobs
Database — PostgreSQL (jobs, applications, users) + Redis (queue/cache)


🔍 Job Scraping Strategy
SourceMethodNotesGreenhouseboards.greenhouse.io/{company}/jobs JSON APIClean, structured JSON — easiestLeverjobs.lever.co/{company} + /v0/postings/{company}REST API availableWorkdayPlaywright headless browserJS-heavy, needs browser automationLinkedInRSS feeds + careful scrapingRate-limit sensitiveIndeed / GlassdoorRSS feeds or unofficial APIsTerms of service cautionRemoteOK, WeWorkRemotelyOpen JSON/RSS APIsDeveloper-friendlyCompany career pagesCustom scrapers per domainUse Playwright
Smart Scraping:

Rotate user agents & proxies
Respect robots.txt and rate limits
Deduplicate via URL hash + title/company fingerprint
Schedule scraping every 2–4 hours
Store raw HTML for re-parsing if schema changes


🤖 Intelligent Matching Engine
Resume → NLP Parse → Skill Vector
Job Description → NLP Parse → Skill Vector
Cosine Similarity Score → 0.0 to 1.0
Matching factors:

Hard skills match (Python, React, etc.) — weighted highest
Soft skills match
Years of experience alignment
Education requirements
Location/remote preference
Salary range overlap
Company culture keywords (from user preferences)
Seniority level alignment

Threshold system:

> 0.85 → Auto-apply immediately
0.70–0.85 → Add to approval queue
< 0.70 → Skip / archive


⚡ Auto-Apply Bot Flow
1. Scrape job posting
2. Score match against resume
3. If above threshold → trigger apply bot
4. Playwright opens Greenhouse/Lever form
5. AI fills fields (name, email, links, cover letter)
6. Cover letter generated via LLM (GPT/Claude) — job-specific
7. Human-in-the-loop CAPTCHA fallback
8. Submit → log to DB → update dashboard
Cover Letter Generation:

Use LLM API with prompt: Resume + Job Description → personalized 150-word letter
Cache per job category to reduce API costs
Tone selector: formal / conversational / enthusiastic


🖥️ Frontend Pages
1. Landing Page

Hero: "Your AI job agent, working 24/7"
Live counter: "2,847 jobs applied this week"
How it works (3 steps)

2. Onboarding Flow

Step 1: Upload resume (PDF/DOCX)
Step 2: Review extracted skills (editable chips)
Step 3: Set job preferences
Step 4: Set auto-apply threshold & rules

3. Main Dashboard

Live Feed — real-time incoming matched jobs (WebSocket)
Match Score badge — color coded (green/yellow/red)
Application Pipeline — Kanban drag-drop
Notifications — "3 new 90%+ matches found"

4. Resume Manager

Visual resume editor
A/B test multiple resume versions
See which resume version gets more matches

5. Settings & Rules Engine

Company blacklist / whitelist
Keyword blockers ("unpaid", "intern", "on-site only")
Daily apply limit (avoid spam flagging)
"Stealth mode" — apply only to companies not yet in your network


🔐 Auth & User System

JWT auth with refresh tokens
OAuth (Google/GitHub login)
Free tier: 10 auto-applies/day
Pro tier: unlimited + cover letter AI + analytics


🧩 Tech Stack Summary
LayerTechnologyFrontendHTML5, CSS3 (custom properties + grid), Vanilla JS (ES modules)Backend APIPython + FastAPIScraperPlaywright + BeautifulSoup + httpxNLP/MatchingspaCy + sentence-transformersCover Letter AIOpenAI / Anthropic APIDatabasePostgreSQL + RedisTask QueueCelery + RedisAuthJWT + bcryptHostingVercel (frontend) + Railway/Render (backend)'
