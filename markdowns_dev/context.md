```markdown
# Pillar AI — Project Context for AI Coding Assistant

> **Version:** 1.0 | **Date:** June 2026  
> **Purpose:** This document provides complete, factual, and resource‑checked context for any AI coding assistant (e.g., Cursor, Copilot) to understand the UN ESCAP Hackathon project, the RDTII framework, and our multi‑agent pipeline – with a focus on **Instance 2 (Extraction & Mapping)**.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [The Problem: RDTII Data Collection](#2-the-problem-rdtii-data-collection)
3. [RDTII Framework (Pillars 6 & 7)](#3-rdtii-framework-pillars-6--7)
4. [Our Solution: Multi‑Agent Pipeline](#4-our-solution-multiagent-pipeline)
5. [Instance 1 – Source Discovery (Zone 1)](#5-instance-1--source-discovery-zone-1)
6. [Instance 2 – Extraction & Structured Mapping (Zone 2)](#6-instance-2--extraction--structured-mapping-zone-2)
   - [6.1 Input & Output](#61-input--output)
   - [6.2 Workflow](#62-workflow)
   - [6.3 Extraction Prompt Design](#63-extraction-prompt-design)
   - [6.4 Field Mapping & CSV Format](#64-field-mapping--csv-format)
   - [6.5 Success Criteria](#65-success-criteria)
7. [Instance 3 – Blind Citation Verification (Quality Gate)](#7-instance-3--blind-citation-verification-quality-gate)
8. [Technical Stack & Setup](#8-technical-stack--setup)
9. [Current Status & Next Steps](#9-current-status--next-steps)
10. [Key Resource Documents](#10-key-resource-documents)

---

## 1. Project Overview

**Team:** Pillar AI  
- **Adriel Babalola** – Technical Lead (Mechatronics Engineering, FUT Minna)  
- **Anna Onimisi Ometere** – Policy Lead (Law, ABU Zaria)

**Event:** UN ESCAP Global Hackathon on AI for Digital Trade Regulatory Analysis  
**Status:** Shortlisted (44/100+ teams)  
**Timeline:** June 2026 (mentorship & build) → August 2026 (prototype showcase) → October 2026 (final pitch in Bangkok)

**Goal:** Build an **open‑source AI pipeline** that automates the data collection process for the **Regional Digital Trade Integration Index (RDTII)** , starting with **Pillars 6 and 7** for **Singapore, Malaysia, and Australia**.

**Key requirement:** All outputs must be evidence‑based, verifiable, and human‑reviewable. **No hallucinations** – every claim must be backed by a primary source.

---

## 2. The Problem: RDTII Data Collection

The **RDTII** is a database (maintained by UN ESCAP) that scores countries on how open or restrictive their digital trade regulations are, across **12 policy pillars**.  
- Score range: **0** (open, trade‑friendly) to **1** (restrictive, high compliance burden).  
- Example: Singapore ~0.2; heavily localised country ~0.75+.

Currently, the database is built **entirely manually**:
- Researchers read hundreds of legal documents per country.
- They extract specific clauses, answer indicator questions, and cite sources.
- This process takes **months per update cycle**, is expensive, and does not scale to all 190+ countries.

**Our focus:** Automate the process for **Pillar 6 (Cross‑Border Data Policies)** and **Pillar 7 (Domestic Data Protection and Privacy)** , which together account for **~50% of the digital governance cluster** and are the most labour‑intensive.

---

## 3. RDTII Framework (Pillars 6 & 7)

### Pillar 6 – Cross‑Border Data Policies  
*Objective: Can data move across borders, under what restrictions, and at what cost?*

| Indicator | Weight | Question |
|-----------|--------|----------|
| **6.1** | 38% | Ban on transfer and/or local processing requirement |
| **6.2** | 12% | Local storage requirement |
| **6.3** | 31% | Infrastructure requirement (local servers/data centres) |
| **6.4** | 12% | Conditional flow regime (consent, adequacy, safeguards) |
| **6.5** | 8% | Not in binding data transfer agreement (e.g., CPTPP, RCEP, DEPA) |

### Pillar 7 – Domestic Data Protection & Privacy  
*Objective: How is data governed internally, and what domestic obligations apply?*

| Indicator | Weight | Question |
|-----------|--------|----------|
| **7.1** | 31% | Lack of comprehensive data protection framework |
| **7.2** | 31% | Lack of dedicated cybersecurity framework |
| **7.3** | 16% | Minimum data retention period |
| **7.4** | 16% | DPO or DPIA requirements |
| **7.5** | 6% | Government access to personal data |

**Scoring:** Each indicator scores 0, 0.5, or 1 per the official RDTII 2.1 rubrics. The pillar score is the weighted average.

---

## 4. Our Solution: Multi‑Agent Pipeline

We use a **LangGraph‑orchestrated hierarchical multi‑agent pipeline** with three main stages (plus a blind verification step).

```
User Input (Country, Pillar)
        ↓
  ┌─────────────────┐
  │ Orchestrator    │ (LangGraph) – dispatches parallel agents
  └────────┬────────┘
           │
    ┌──────┴──────┐
    │             │
 Pillar 6    Pillar 7
 Agent         Agent
    │             │
    ▼             ▼
 ┌─────────────────────────────────────┐
 │         INSTANCE 1 (Zone 1)         │
 │  Discovery: Firecrawl search + URL  │
 │  filtering → candidate JSON         │
 └─────────────────────────────────────┘
           │
           ▼
 ┌─────────────────────────────────────┐
 │         INSTANCE 2 (Zone 2)         │
 │  Extraction: Scrape full text →     │
 │  LLM (Gemini) extracts operative    │
 │  clauses → structured CSV           │
 └─────────────────────────────────────┘
           │
           ▼
 ┌─────────────────────────────────────┐
 │      INSTANCE 3 (Blind Verification)│
 │  Independent re‑fetch & verify      │
 │  each citation                      │
 └─────────────────────────────────────┘
           │
           ▼
     CSV Export (RDTII‑compatible)
```

---

## 5. Instance 1 – Source Discovery (Zone 1)

**What it does:**  
- Takes a country and pillar (e.g., “Singapore, Pillar 6”).  
- Uses **Firecrawl** search with indicator‑specific queries to find official legal documents.  
- Filters results to **primary sources only** (official government domains: `.gov.sg`, `sso.agc.gov.sg`, `pdpc.gov.sg`, etc.).  
- Excludes secondary sources (news, law firm blogs, Wikipedia).  
- Outputs a JSON file with candidate URLs, titles, and snippets per indicator.

**Output Example:** `zone1_singapore_pillar6.json`  
```json
{
  "6.1": [
    {
      "indicator": "6.1",
      "title": "Personal Data Protection Act 2012",
      "url": "https://sso.agc.gov.sg/Act/PDPA2012",
      "snippet": "An Act to govern the collection, use and disclosure...",
      "query_used": "site:sso.agc.gov.sg Personal Data Protection Act transfer"
    }
  ],
  "6.2": [...]
}
```

**Guardrails:**  
- Only `.gov.sg` (or equivalent for other countries) are accepted.  
- Must check that the document is “in force” (by URL pattern or metadata).  
- No hardcoded URLs – all discovery is dynamic.

**Success Criteria:**  
- Precision > 0.80 (primary sources only).  
- Recall > 0.75 (finds known relevant laws).  
- All returned URLs are live and accessible.

---

## 6. Instance 2 – Extraction & Structured Mapping (Zone 2)

This stage **consumes the JSON from Instance 1**, scrapes the full text of each candidate URL, and uses an LLM to extract the exact legal provisions that answer the RDTII indicator questions. The output is a structured CSV that matches the hackathon’s required format.

### 6.1 Input & Output

**Input:**  
- `zone1_singapore_pillar6.json` (or similar) – the candidates per indicator.

**Output:**  
- A CSV file with the following columns (exactly as per the “Format Requirements” PDF):

| Column Name | Description |
|-------------|-------------|
| **Pillar_ID** | e.g., “6” |
| **Indicator_ID** | e.g., “6.1” |
| **Act_and_or_practice** | Official title of the law (e.g., “Personal Data Protection Act 2012”). **Do not** include section numbers here. |
| **Coverage** | “Cross‑cutting” (horizontal) OR “Sectoral” (specify sector, e.g., “Financial”). |
| **Impact_or_comments** | The exact operative clause (verbatim) + a concise legal interpretation of why it matches the indicator. Format: `"[Section X]: [verbatim clause] Interpretation: ..."` |
| **Timeframe** | Date the law came into force; if amended, date of latest amendment. Format: `"Since Month Year; Last amended Month Year"` |
| **References** | The official URL (one per row). |

### 6.2 Workflow

1. **Load & Rank Candidates**  
   - For each indicator, take the top 3–5 candidate URLs (based on relevance score, domain, title keywords). This saves tokens and time.

2. **Scrape Full Text**  
   - Use **Firecrawl** to scrape each URL. The response includes markdown, HTML, or plain text. Firecrawl handles PDFs automatically.

3. **Call the LLM for Extraction**  
   - Use **Gemini 2.5 Flash** (free tier, 1M context) or a cheap OpenRouter model (Mixtral, Llama 3).  
   - Provide the scraped text and a **structured extraction prompt** (see below).  
   - The prompt forces the LLM to return **only JSON** with the required fields.

4. **Parse & Validate**  
   - Check if the LLM returned a valid JSON with all required fields.  
   - If the operative clause is empty or null, skip this candidate.  
   - If the answer is “not found”, mark the row as “No specific provision found” (but still include the law as a reference).

5. **Assemble the CSV Row**  
   - Map the LLM’s output to the columns exactly as per the format.  
   - Append to a list of rows.

6. **Write CSV**  
   - Use `csv.DictWriter` to output the final file.

### 6.3 Extraction Prompt Design

The prompt must be **indicator‑specific** because each indicator asks a different question. Below is a template for **6.1** – adapt for each indicator.

```
You are a legal expert. You are given the full text of a Singapore law.
Your task is to answer the following RDTII indicator question:

**Indicator 6.1**: Does this law impose a ban on cross‑border data transfer and/or require local processing?

Carefully read the text. Look for provisions that:
- Prohibit or restrict transfer of personal data to other countries.
- Require that personal data be processed or stored locally.

Extract the following fields in **valid JSON**:
{
  "operative_clause": "the exact, verbatim provision(s) that answer the question. If multiple, choose the most relevant one. If none, return null.",
  "section_reference": "the specific section/article number (e.g., 'Section 26(1)')",
  "coverage": "Cross-cutting if it applies to all organisations; otherwise specify the sector (e.g., 'Financial')",
  "timeframe": "date the law entered into force and last amendment. Format: 'Since Month Year; Last amended Month Year'",
  "interpretation": "a brief legal interpretation explaining why this provision matches the indicator (e.g., 'This is a conditional flow regime, not a total ban.')"
}

If no relevant provision exists, return {"operative_clause": null} for all fields.
Return ONLY the JSON, no extra text.

Law text:
{scraped_text}
```

**Important:** The prompt forces the LLM to return the **exact operative clause** – not a summary – to ensure evidence‑based outputs.

### 6.4 Field Mapping & CSV Format

**Example output row for Singapore 6.1:**

| Pillar_ID | Indicator_ID | Act_and_or_practice | Coverage | Impact_or_comments | Timeframe | References |
|-----------|--------------|---------------------|----------|--------------------|-----------|------------|
| 6 | 6.1 | Personal Data Protection Act 2012 | Cross‑cutting | Section 26(1): "An organisation must not transfer any personal data to a country or territory outside Singapore except in accordance with requirements prescribed under this Act to ensure a standard of protection comparable to the protection under this Act." Interpretation: This is a conditional flow regime, not a ban. | Since 2 January 2013; Revised 2020; Last amended 1 February 2021. | https://sso.agc.gov.sg/Act/PDPA2012 |

### 6.5 Success Criteria

- **Field Accuracy > 90%** – manually verify 10 random rows against the original legal text.
- **Correct Indicator Mapping** – e.g., 6.1 must not be confused with 6.4 (conditional flow).
- **Operative clause is verbatim** – no paraphrasing.
- **Timeframe is correct** – matches the law’s official commencement and amendment dates.
- **Coverage logic correct** – national law = Cross‑cutting; sectoral regulation = Sectoral + sector name.

---

## 7. Instance 3 – Blind Citation Verification (Quality Gate)

> *Brief mention – this is the critical anti‑hallucination step.*

**What it does:**  
- Receives **only** the citation (URL + section reference) from Instance 2.  
- **Does not** see the scorer’s reasoning or extracted text.  
- Independently re‑fetches the document via Firecrawl, navigates to the cited section, and reads the actual text.  
- Compares the actual text to the claimed operative clause.  
- **Verdict:** PASS (text matches), FAIL (mismatch), or NEEDS REVIEW (ambiguous).  
- If FAIL, the pipeline retries up to 3 times; if still failing, it flags the row for mandatory human review.

**Why this is essential:** It catches hallucinations like wrong section numbers (e.g., citing Section 24(1) when the operative clause is in 24(3)) – a common error that conventional review misses.

---

## 8. Technical Stack & Setup

| Component | Tool / Service | Purpose |
|-----------|---------------|---------|
| **Orchestration** | LangGraph 1.0 | Stateful multi‑agent pipeline with retries and human‑in‑the‑loop. |
| **Document Discovery** | Firecrawl (Search + Scrape) | Find and extract full text from official legal portals. |
| **Extraction LLM** | Gemini 2.5 Flash (primary) | Reads long statutes (1M context) and extracts clauses. Free tier. |
| **Alternative LLM** | OpenRouter (Mixtral, Llama 3) | Fallback or if Gemini unavailable. Very low cost. |
| **Scoring** | Claude Sonnet 4.5 (temp=0) | Deterministic scoring (0, 0.5, 1) based on rubrics. (Used in Instance 3/aggregator) |
| **Blind Verifier** | Claude Sonnet 4.5 (separate instance) | Independent re‑fetch and verification. |
| **Queue / State** | Upstash Redis | Job queue for async processing. |
| **Storage** | MongoDB | Raw documents and metadata. |
| **Output** | CSV | Final export in RDTII‑compatible format. |
| **Environment** | `.env` | Contains `FIRECRAWL_API_KEY`, `GEMINI_API_KEY`, etc. |
| **Dependencies** | `firecrawl-py`, `python-dotenv`, `google-generativeai`, `csv`, `json` | Standard Python packages. |

**Cost Considerations:**  
- Gemini 2.5 Flash is **free** (1500 requests/day) – sufficient for our prototype.  
- Firecrawl has a free tier (limited credits) – we use sparingly.  
- OpenRouter free models have rate limits, but we can add `time.sleep()` between requests.  
- Total cost for the entire prototype run (Singapore, Pillar 6 & 7) is expected to be under $5.

---

## 9. Current Status & Next Steps

- **Completed:** Architecture design, Instance 1 script (discovery), Assignment 1 & 2 submissions, shortlisting.
- **In progress:** Building Instance 2 script (extraction & mapping).
- **Upcoming:**  
  - Integrate Instance 2 with Instance 1 JSON.  
  - Test extraction on Singapore Pillar 6.  
  - Implement blind verification (Instance 3).  
  - Expand to Malaysia and Australia.  
  - Prepare for August prototype showcase.

---

## 10. Key Resource Documents

These documents are the **authoritative sources** for project decisions:

| Document | Content |
|----------|---------|
| **RDTII 2.1 Methodology Guide** | Full rubric, indicator definitions, scoring rules. |
| **RDTII 2.1 Framework Overview** | 12 pillars, weights, coverage logic. |
| **RDTII Extraction & Hands‑on Practice** (Juntong H.) | Zone 1 & 2 step‑by‑step, common pitfalls, quiz examples. |
| **Format Requirements for RDTII Data Collection** | Exact CSV column definitions and formatting rules. |
| **UN ESCAP Knowledge Workshop** (Henry Gao) | Legal structure, operative verbs, reading statutes. |
| **AI‑Assisted Legal Document Processing** (Qian Xiao) | LLM flaws, noise audits, blind verification. |
| **Engineering AI Across Borders** (Varanyu S.) | Real‑world success criteria, system design principles. |

---

## For the AI Coding Assistant: Your Task

> You are now equipped with the full project context. Your job is to help implement **Instance 2** – the extraction and mapping stage – as described in Section 6.  
> The script should:
> 1. Read the JSON from Instance 1.
> 2. For each indicator, rank candidates and select top 3.
> 3. Scrape each URL using Firecrawl.
> 4. Send the text to Gemini 2.5 Flash with the appropriate extraction prompt.
> 5. Parse the JSON response, map to CSV columns, and write the final CSV.
> 6. Handle errors gracefully (retry, skip, log).
>
> The output CSV must be directly importable into the RDTII database format.

All code should be well‑commented, use environment variables for API keys, and follow PEP8.

---
*End of context. Good luck!*
```