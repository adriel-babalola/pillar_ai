"""
Extraction prompts and indicator definitions for RDTII Pillars 6 & 7.
"""

PILLAR_6_INDICATORS = {
    "6.1": {
        "name": "Ban and local processing requirements",
        "question": "Does this law impose a ban on cross-border data transfer and/or require local processing?",
        "keywords": [
            "prohibit", "must not transfer", "local processing",
            "cross-border", "transfer personal data", "shall not transfer",
            "outside", "overseas transfer",
        ],
        "extraction_instructions": (
            "Look for provisions that: (1) Prohibit or restrict the transfer of "
            "personal data to other countries; (2) Require that personal data be "
            "processed or stored locally. Distinguish between a total ban (score 1) "
            "and a conditional regime (score 0.5)."
        ),
    },
    "6.2": {
        "name": "Local storage requirements",
        "question": "Does this law require local storage of data?",
        "keywords": [
            "local storage", "store data locally", "data shall be stored",
            "data localization", "records kept in", "data residency",
        ],
        "extraction_instructions": (
            "Look for provisions that require data to be stored within the country's "
            "territory. This includes requirements that copies of data must be kept "
            "locally, or that databases must be maintained within the jurisdiction."
        ),
    },
    "6.3": {
        "name": "Infrastructure requirements",
        "question": "Does this law require local infrastructure (servers/data centres)?",
        "keywords": [
            "server located", "local server", "data centre",
            "computing facility", "infrastructure requirement",
        ],
        "extraction_instructions": (
            "Look for provisions that require organisations to use or maintain "
            "computing infrastructure (servers, data centres, computing facilities) "
            "located within the country."
        ),
    },
    "6.4": {
        "name": "Conditional flow regimes",
        "question": "Does this law establish a conditional flow regime for cross-border data transfers?",
        "keywords": [
            "consent", "adequacy decision", "contractual safeguards",
            "binding corporate rules", "data transfer exception",
            "comparable protection", "transfer conditions",
        ],
        "extraction_instructions": (
            "Look for provisions that allow cross-border data transfers subject to "
            "conditions such as: consent, adequacy decisions, contractual safeguards, "
            "binding corporate rules, or other prescribed requirements."
        ),
    },
    "6.5": {
        "name": "Binding data transfer agreements",
        "question": "Is this a binding data transfer agreement (e.g., CPTPP, RCEP, DEPA)?",
        "keywords": [
            "CPTPP", "RCEP", "DEPA", "digital economy agreement",
            "free trade agreement", "cross-border data flow",
        ],
        "extraction_instructions": (
            "Look for provisions in international trade agreements that address "
            "cross-border data flows, data localization, or digital trade. "
            "These are typically treaties or executive agreements, not domestic legislation."
        ),
    },
}

PILLAR_7_INDICATORS = {
    "7.1": {
        "name": "Lack of comprehensive data protection framework",
        "question": "Does this law provide a comprehensive data protection framework?",
        "keywords": [
            "data protection", "personal data", "privacy act",
            "data protection framework", "personal information",
        ],
        "extraction_instructions": (
            "Look for provisions that establish a comprehensive framework for "
            "protecting personal data. These typically include: data subject rights, "
            "consent requirements, data breach notification, enforcement mechanisms, "
            "and rules on collection/use/disclosure of personal data."
        ),
    },
    "7.2": {
        "name": "Lack of dedicated cybersecurity framework",
        "question": "Does this law provide a dedicated cybersecurity framework?",
        "keywords": [
            "cybersecurity", "cyber security", "information security",
            "computer misuse", "cybercrime",
        ],
        "extraction_instructions": (
            "Look for provisions that establish a cybersecurity framework, including: "
            "security measures requirements, incident reporting, critical information "
            "infrastructure protection, or computer misuse offences."
        ),
    },
    "7.3": {
        "name": "Minimum data retention period",
        "question": "Does this law impose a minimum data retention period?",
        "keywords": [
            "retain for", "retention period", "keep records",
            "data retention", "shall retain",
        ],
        "extraction_instructions": (
            "Look for provisions that require organisations to retain personal data "
            "or records for a minimum specified period. Note the exact duration "
            "(e.g., '2 years', '5 years') and the type of data covered."
        ),
    },
    "7.4": {
        "name": "DPO/DPIA requirements",
        "question": "Does this law require a Data Protection Officer (DPO) or Data Protection Impact Assessment (DPIA)?",
        "keywords": [
            "Data Protection Officer", "DPO",
            "Data Protection Impact Assessment", "DPIA",
            "privacy impact assessment",
        ],
        "extraction_instructions": (
            "Look for provisions requiring: appointment of a Data Protection Officer "
            "or similar role; conduct of Data Protection Impact Assessments "
            "for high-risk processing."
        ),
    },
    "7.5": {
        "name": "Government access to personal data",
        "question": "Does this law grant government access to personal data?",
        "keywords": [
            "government access", "lawful access", "surveillance powers",
            "police access", "national security access", "disclosure to",
        ],
        "extraction_instructions": (
            "Look for provisions that allow government authorities to access personal "
            "data held by organisations. This includes: lawful interception, "
            "surveillance powers, police/regulator access to records, or "
            "national security exceptions to data protection."
        ),
    },
}

PREFILTER_PROMPT = """You are a legal research assistant. Given a candidate document for an RDTII indicator, determine if the document is likely to contain a relevant legal provision.

Indicator {indicator_id}: {indicator_question}

Document Title: {title}
Document Snippet: {snippet}

Ignore formatting noise (URL wrappers, truncated text). Focus on the title and readable content.

Is this document likely to contain a legal provision, regulation, or obligation directly relevant to this indicator?

Respond with valid JSON only:
{{"relevant": true, "confidence": "high"}}
or
{{"relevant": false, "confidence": "low"}}

Confidence levels: "high" (clearly relevant), "medium" (possibly relevant), "low" (unlikely relevant)."""

EXTRACTION_PROMPT_TEMPLATE = """You are an expert legal researcher specialising in digital trade and data protection law. You are analysing a legal document from Singapore.

Your task is to answer the following RDTII (Regional Digital Trade Integration Index) indicator question:

**Indicator {indicator_id}**: {indicator_question}

{extraction_instructions}

Carefully read the full legal text below. Extract the following fields in **valid JSON only**:

- "operative_clause": The exact, verbatim provision(s) that answer the indicator question. Quote the text precisely. If multiple provisions are relevant, choose the most directly applicable one. If none exists, set to null.
- "section_reference": The specific section, article, or regulation number (e.g., "Section 26(1)", "Article 4", "Part III"). If none, set to null.
- "act_title": The full official title of the legal instrument (e.g., "Personal Data Protection Act 2012"). Do NOT include section numbers here.
- "coverage": "Cross-cutting" if the law applies to all sectors/organisations; otherwise "Sectoral" followed by the specific sector (e.g., "Sectoral: Financial").
- "timeframe": The date the law came into force and, if amended, the latest amendment date. Format: "Since Month Year; Last amended Month Year". If the dates are not in the text, set to "Not specified in text".
- "interpretation": A concise legal interpretation (2-3 sentences) explaining why this provision matches the indicator. Include the policy effect (e.g., "This is a conditional flow regime requiring comparable protection, not a total ban.").

Important rules:
1. The operative clause MUST be verbatim — copy the exact wording from the text.
2. If the document does NOT contain any relevant provision, return: {{"operative_clause": null, "section_reference": null, "act_title": null, "coverage": null, "timeframe": null, "interpretation": null}}
3. Return ONLY the JSON object, no other text, no markdown fences.

--- BEGIN LEGAL TEXT ---
{scraped_text}
--- END LEGAL TEXT ---"""
