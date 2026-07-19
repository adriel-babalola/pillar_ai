import logging
import re
from urllib.parse import quote

from src.zone2.config import log

LAWS_SG_URLS = {
    "PDPA2012": "https://laws.sg/legislation/personal-data-protection-act-2012",
    "CA2018": "https://laws.sg/legislation/cybersecurity-act-2018",
    "CMA1993": "https://laws.sg/legislation/computer-misuse-act-1993",
    "CPC2010": "https://laws.sg/legislation/criminal-procedure-code-2010",
    "PSGA2018": "https://laws.sg/legislation/public-sector-governance-act-2018",
}

LAWS_SG_PDF_URLS = {
    "PDPA2012": "https://arturio-pdfs.cancode.codes/sg/259.pdf",
    "CA2018": "https://arturio-pdfs.cancode.codes/sg/33.pdf",
    "CMA1993": "https://arturio-pdfs.cancode.codes/sg/19.pdf",
    "CPC2010": "https://arturio-pdfs.cancode.codes/sg/45.pdf",
    "PSGA2018": "https://arturio-pdfs.cancode.codes/sg/256.pdf",
}

SSO_TO_LAWS_SG = {
    "https://sso.agc.gov.sg/Act/PDPA2012": "https://laws.sg/legislation/personal-data-protection-act-2012",
    "https://sso.agc.gov.sg/Act/CA2018": "https://laws.sg/legislation/cybersecurity-act-2018",
    "https://sso.agc.gov.sg/Act/CMA1993": "https://laws.sg/legislation/computer-misuse-act-1993",
    "https://sso.agc.gov.sg/Act/CPC2010": "https://laws.sg/legislation/criminal-procedure-code-2010",
    "https://sso.agc.gov.sg/Act/PSGA2018": "https://laws.sg/legislation/public-sector-governance-act-2018",
}


def laws_sg_url_for_act(act_short: str) -> str | None:
    return LAWS_SG_URLS.get(act_short)


def laws_sg_pdf_for_act(act_short: str) -> str | None:
    return LAWS_SG_PDF_URLS.get(act_short)


def sso_to_laws_sg(sso_url: str) -> str | None:
    for sso_prefix, lsg_url in SSO_TO_LAWS_SG.items():
        if sso_url.startswith(sso_prefix):
            return lsg_url
    return None


def is_laws_sg_url(url: str) -> bool:
    return "laws.sg" in url


def get_laws_sg_alternates(url: str) -> list[str]:
    alts = []
    for sso_prefix, lsg_url in SSO_TO_LAWS_SG.items():
        if sso_prefix in url:
            if lsg_url not in alts:
                alts.append(lsg_url)
            for act_short, pdf_url in LAWS_SG_PDF_URLS.items():
                if sso_prefix.endswith(act_short):
                    if pdf_url not in alts:
                        alts.append(pdf_url)
    if "laws.sg/legislation/" in url:
        m = re.search(r'/legislation/([^/?#]+)', url)
        if m:
            for act_short, lsg_url in LAWS_SG_URLS.items():
                if lsg_url == url:
                    pdf_url = LAWS_SG_PDF_URLS.get(act_short)
                    if pdf_url:
                        alts.append(pdf_url)
    return alts
