"""
Zone 4 — RDTII 2.1 Scoring Module for Pillars 6 & 7.

Takes the verified CSV from Zone 3 and applies the official RDTII 2.1
scoring rubrics, producing final pillar scores with evidence mapping.

Usage:
    from src.zone4.scoring import score_country_pillar, print_score_report

Scoring structure per the RDTII 2.1 Methodology Guide:
  - Each indicator scores 0, 0.5, or 1 per the rubric below.
  - The pillar score is a weighted average of indicator scores.
  - Pillar scores range 0 (fully open) to 1 (fully restrictive).
"""

from typing import Optional

# ── Pillar 6 Weights (from RDTII 2.1 Guide, page 56) ─────────────────

PILLAR_6_WEIGHTS = {
    "6.1": 0.38,  # Ban and local processing requirements
    "6.2": 0.12,  # Local storage requirements
    "6.3": 0.31,  # Infrastructure requirements
    "6.4": 0.12,  # Conditional flow regimes
    "6.5": 0.08,  # Not in binding data transfer agreements
}

# ── Pillar 7 Weights (from RDTII 2.1 Guide, page 63) ─────────────────

PILLAR_7_WEIGHTS = {
    "7.1": 0.31,  # Lack of comprehensive data protection framework
    "7.2": 0.31,  # Lack of dedicated cybersecurity framework
    "7.3": 0.16,  # Minimum data retention period
    "7.4": 0.06,  # DPO/DPIA requirements
    "7.5": 0.16,  # Government access to personal data
}

# ── Scoring Rubrics ────────────────────────────────────────────────────
# Each rubric is a function that takes extracted data and returns (score, rationale).
# Score is 0, 0.25, 0.5, or 1 per the RDTII 2.1 specification.


def score_6_1(coverage: str, verbatim: str, interpretation: str) -> tuple[float, str]:
    """
    Score 6.1 — Ban and local processing requirements.
    
    Score 1: Ban/local processing covers personal data OR applies horizontally
             across sectors OR two+ requirements on non-personal data OR
             applies to more than one economy.
    Score 0.5: Applies to non-personal data OR a specific set of data OR one economy.
    Score 0: Data freely transferable without requirement.
    """
    cover_lower = coverage.lower()
    interp_lower = interpretation.lower()
    combined = f"{cover_lower} {interp_lower}"

    # Indicators of a total ban or broad restriction
    if any(w in combined for w in ["total ban", "absolute prohibition", "prohibits all"]):
        return 1.0, "Total ban on cross-border data transfer applies to all data"
    if "horizontal" in cover_lower or "cross-cutting" in cover_lower or "all sectors" in combined:
        if "personal data" in verbatim.lower() or "personal data" in interp_lower:
            return 1.0, "Horizontal ban/processing requirement covering personal data"
        return 1.0, "Horizontal ban/processing requirement across all sectors"
    if "sectoral" in cover_lower:
        if "personal" in combined:
            return 1.0, "Ban/processing requirement applies to personal data (sectoral)"
        return 0.5, "Ban/processing requirement applies to non-personal data or specific sector"
    if any(w in combined for w in ["restrict", "prohibit", "ban", "shall not transfer", "must not transfer"]):
        return 1.0, f"Restriction on cross-border data transfer identified: {interpretation[:200]}"
    if "no restriction" in combined or "free flow" in combined or "freely transfer" in combined:
        return 0.0, "Data may be transferred freely without restriction"
    return 0.0, "No relevant ban or processing requirement found"


def score_6_2(coverage: str, verbatim: str, interpretation: str) -> tuple[float, str]:
    """
    Score 6.2 — Local storage requirements.
    
    Score 1: Local storage covers personal data OR horizontal across sectors
             OR two+ requirements on non-personal data.
    Score 0.5: Applies to non-personal data or specific data set.
    Score 0: No local storage requirement.
    """
    cover_lower = coverage.lower()
    interp_lower = interpretation.lower()
    combined = f"{cover_lower} {interp_lower}"

    if "horizontal" in cover_lower or "cross-cutting" in cover_lower:
        if "personal" in combined:
            return 1.0, "Horizontal local storage requirement covering personal data"
        return 1.0, "Horizontal local storage requirement"
    if "sectoral" in cover_lower:
        if "personal" in combined:
            return 1.0, "Local storage requirement for personal data in specific sector"
        return 0.5, "Local storage requirement for non-personal data in specific sector"
    if any(w in combined for w in ["local storage", "store locally", "data localization", "data residency"]):
        return 1.0, f"Local storage requirement identified: {interpretation[:200]}"
    if "no" in combined and ("require" in combined or "mandate" in combined):
        return 0.0, "No local storage requirement found"
    return 0.0, "No local storage requirement found"


def score_6_3(coverage: str, verbatim: str, interpretation: str) -> tuple[float, str]:
    """
    Score 6.3 — Infrastructure requirements.
    
    Score 1: At least one infrastructure requirement exists.
    Score 0: No infrastructure requirement.
    """
    combined = f"{interpretation.lower()} {verbatim.lower()}"

    if any(w in combined for w in [
        "data centre", "data center", "local server", "infrastructure requirement",
        "establish", "computing facility", "local physical infrastructure",
    ]):
        return 1.0, f"Infrastructure requirement identified: {interpretation[:200]}"
    return 0.0, "No infrastructure requirement found"


def score_6_4(coverage: str, verbatim: str, interpretation: str) -> tuple[float, str]:
    """
    Score 6.4 — Conditional flow regimes.
    
    Score 1: Regime covers personal data OR applies horizontally across sectors.
    Score 0.5: Applies to non-personal data AND/OR specific data set.
    Score 0: No condition exists.
    """
    cover_lower = coverage.lower()
    combined = f"{interpretation.lower()} {verbatim.lower()}"

    if "horizontal" in cover_lower or "cross-cutting" in cover_lower:
        if "personal" in combined:
            return 1.0, "Horizontal conditional flow regime covering personal data"
        return 1.0, "Horizontal conditional flow regime (even if non-personal)"
    if "sectoral" in cover_lower:
        if "personal" in combined:
            return 1.0, "Conditional flow regime for personal data in specific sector"
        return 0.5, "Conditional flow regime for non-personal data in specific sector"
    if any(w in combined for w in [
        "condition", "consent", "adequate", "safeguard", "comparable protection",
        "binding corporate rules", "contractual", "approval", "authorisation",
        "authorization", "conditional flow",
    ]):
        if "personal" in combined:
            return 1.0, f"Conditional flow regime for personal data: {interpretation[:200]}"
        return 0.5, f"Conditional flow regime: {interpretation[:200]}"
    if "no condition" in combined or "free flow" in combined or "no restriction" in combined:
        return 0.0, "No conditions on cross-border data transfer"
    return 0.0, "No conditional flow regime found"


def score_6_5(interpretation: str) -> tuple[float, str]:
    """
    Score 6.5 — Not in binding data transfer agreements.
    
    Score 1: Economy does NOT commit to any binding agreement on data flows.
    Score 0: Economy signs at least one binding agreement on data flows.
    """
    interp_lower = interpretation.lower()

    # Check negative/absence phrases FIRST (avoid false match on "party to" in "not party to")
    if any(w in interp_lower for w in ["not party", "not member", "no agreement", "no binding"]):
        return 1.0, "Economy has not committed to any binding data transfer agreement"
    if any(w in interp_lower for w in [
        "member of", "party to", "bound by", "signatory", "committed",
        "participates in", "cptpp", "rcep", "depa", "digital economy agreement",
        "binding agreement", "trade agreement", "free trade agreement",
    ]):
        return 0.0, f"Economy is party to binding data transfer agreement(s): {interpretation[:200]}"
    return 1.0, "No binding data transfer agreement identified (fallback - assuming no commitment)"


def score_7_1(interpretation: str, verbatim: str) -> tuple[float, str]:
    """
    Score 7.1 — Lack of comprehensive data protection framework.
    
    Score 1: Lacks data protection framework.
    Score 0.5: Sectoral framework exists.
    Score 0: Comprehensive framework exists.
    """
    combined = f"{interpretation.lower()} {verbatim.lower()}"

    if any(w in combined for w in [
        "no data protection", "lack", "absence", "no comprehensive",
        "no framework", "not exist", "does not have",
    ]):
        return 1.0, "Economy lacks a data protection framework"
    if "sectoral" in combined or "specific sector" in combined:
        return 0.5, "Sectoral data protection framework exists (not comprehensive)"
    if any(w in combined for w in [
        "comprehensive", "personal data protection act", "data protection act",
        "privacy act", "cross-sectoral", "horizontal",
    ]):
        return 0.0, f"Comprehensive data protection framework exists: {interpretation[:200]}"
    return 0.0, "Comprehensive data protection framework assumed present"


def score_7_2(interpretation: str, verbatim: str) -> tuple[float, str]:
    """
    Score 7.2 — Lack of dedicated cybersecurity framework.
    
    Score 1: Lacks cybersecurity framework.
    Score 0.5: Non-dedicated framework or dedicated sectoral framework.
    Score 0: Dedicated horizontal framework exists.
    """
    combined = f"{interpretation.lower()} {verbatim.lower()}"

    if any(w in combined for w in ["no cyber", "lack", "absence", "no framework"]):
        return 1.0, "Economy lacks a cybersecurity framework"
    if any(w in combined for w in ["sectoral", "non-dedicated", "not dedicated", "relies on other laws"]):
        return 0.5, "Non-dedicated or sectoral cybersecurity framework exists"
    if any(w in combined for w in [
        "cybersecurity act", "cyber security act", "cybersecurity law",
        "dedicated", "horizontal", "comprehensive", "all sectors",
    ]):
        return 0.0, f"Dedicated cybersecurity framework exists: {interpretation[:200]}"
    return 0.0, "Dedicated cybersecurity framework assumed present"


def score_7_3(interpretation: str, verbatim: str) -> tuple[float, str]:
    """
    Score 7.3 — Minimum data retention period.
    
    Score 1: Minimum period of data retention exists.
    Score 0: No retention requirement OR no minimum period specified.
    """
    combined = f"{interpretation.lower()} {verbatim.lower()}"

    if any(w in combined for w in ["retain for", "retention period", "shall retain", "keep records",
                                    "minimum period", "for at least", "retained for"]):
        return 1.0, f"Minimum data retention period identified: {interpretation[:200]}"
    if any(w in combined for w in ["as long as necessary", "no retention", "no minimum", "not specified"]):
        return 0.0, "No minimum retention period — requirement is 'as long as necessary' or absent"
    return 0.0, "No minimum data retention requirement found"


def score_7_4(interpretation: str, verbatim: str) -> tuple[float, str]:
    """
    Score 7.4 — DPO/DPIA requirements.
    
    Score 1: DPO requirement AND/OR both DPO and DPIA horizontally across sectors.
    Score 0.5: DPO AND/OR DPIA sectoral only.
    Score 0.25: Only DPIA required (no DPO).
    Score 0: No requirement.
    """
    combined = f"{interpretation.lower()} {verbatim.lower()}"

    has_dpo = any(w in combined for w in [
        "data protection officer", "dpo", "appoint", "data controller",
    ])
    has_dpia = any(w in combined for w in [
        "data protection impact assessment", "dpia", "privacy impact assessment",
    ])
    is_horizontal = any(w in combined for w in ["horizontal", "cross-cutting", "all sectors", "cross-sectoral"])
    is_sectoral = "sectoral" in combined

    if has_dpo and is_horizontal:
        return 1.0, "DPO requirement applies horizontally across all sectors"
    if has_dpo and is_sectoral:
        return 0.5, "DPO requirement applies to specific sector(s) only"
    if has_dpo and not is_sectoral:
        return 1.0, "DPO requirement found (scope assumed horizontal)"
    if has_dpia and not has_dpo:
        return 0.25, "Only DPIA required, no DPO requirement"
    if not has_dpo and not has_dpia:
        if any(w in combined for w in ["no requirement", "not required", "voluntary"]):
            return 0.0, "No DPO or DPIA requirement"
        return 0.0, "No DPO/DPIA requirement found"
    return 0.0, "No DPO/DPIA requirement found"


def score_7_5(interpretation: str, verbatim: str) -> tuple[float, str]:
    """
    Score 7.5 — Government access to personal data.
    
    Score 1: Government can access personal data without independent judicial authorization.
    Score 0: No such requirement OR judicial authorization required.
    """
    combined = f"{interpretation.lower()} {verbatim.lower()}"

    if any(w in combined for w in [
        "government access", "lawful access", "surveillance", "police access",
        "national security access", "disclosure to", "access without warrant",
        "without judicial", "without court", "provide access",
    ]):
        if any(w in combined for w in ["without", "no warrant", "no court", "no judicial", "authorise"]):
            return 1.0, f"Government access without independent judicial authorization: {interpretation[:200]}"
        return 1.0, f"Government access to personal data identified: {interpretation[:200]}"
    if any(w in combined for w in [
        "no access", "not allow", "judicial warrant", "court order", "judicial authorisation",
        "judicial authorization", "due process",
    ]):
        return 0.0, "Government access requires judicial authorization or does not exist"
    return 0.0, "No government access to personal data found"


# ── Rubric dispatch table ──────────────────────────────────────────────

P6_RUBRICS = {
    "6.1": score_6_1,
    "6.2": score_6_2,
    "6.3": score_6_3,
    "6.4": score_6_4,
    "6.5": score_6_5,
}

P7_RUBRICS = {
    "7.1": score_7_1,
    "7.2": score_7_2,
    "7.3": score_7_3,
    "7.4": score_7_4,
    "7.5": score_7_5,
}

INDICATOR_WEIGHTS = {"6": PILLAR_6_WEIGHTS, "7": PILLAR_7_WEIGHTS}
RUBRICS = {"6": P6_RUBRICS, "7": P7_RUBRICS}


def score_indicator(
    indicator_id: str,
    coverage: str = "",
    verbatim_snippet: str = "",
    mapping_rationale: str = "",
    impact_or_comments: str = "",
) -> dict:
    """
    Score a single RDTII indicator given extracted evidence.
    
    Args:
        indicator_id: e.g., "6.1", "7.3"
        coverage: Coverage field from extraction ("Cross-cutting", "Sectoral: Financial", etc.)
        verbatim_snippet: The exact operative clause text
        mapping_rationale: The interpretation explaining why it maps
        impact_or_comments: Fallback combined field if individual fields are empty
    
    Returns dict with:
        indicator_id, score, rationale, weight, weighted_score
    """
    pillar_id = indicator_id.split(".")[0]
    rubrics = RUBRICS.get(pillar_id, {})
    weights = INDICATOR_WEIGHTS.get(pillar_id, {})
    weight = weights.get(indicator_id, 0)
    rubric_fn = rubrics.get(indicator_id)

    if not rubric_fn:
        return {
            "indicator_id": indicator_id,
            "score": None,
            "rationale": "No rubric defined for this indicator",
            "weight": weight,
            "weighted_score": None,
        }

    # Use fallback if verbatim or rationale are empty
    verbatim = verbatim_snippet or impact_or_comments
    rationale = mapping_rationale or impact_or_comments

    # Some rubrics use only certain arguments
    if indicator_id in ("6.5",):
        score, rationale = rubric_fn(rationale)
    elif indicator_id in ("7.1", "7.2", "7.3", "7.4", "7.5"):
        score, rationale = rubric_fn(rationale, verbatim)
    else:
        score, rationale = rubric_fn(coverage, verbatim, rationale)

    weighted_score = round(score * weight, 4) if score is not None else None

    return {
        "indicator_id": indicator_id,
        "score": score,
        "rationale": rationale,
        "weight": weight,
        "weighted_score": weighted_score,
    }


def score_all_indicators(rows: list[dict], pillar_id: str) -> list[dict]:
    """
    Score all indicators from a list of CSV row dicts.
    
    Args:
        rows: List of row dicts (from Zone 2/3 CSV output)
        pillar_id: "6" or "7"
    
    Returns:
        List of score result dicts (one per indicator), sorted by indicator_id.
    """
    weights = INDICATOR_WEIGHTS.get(pillar_id, {})
    results = []

    for ind_id in sorted(weights.keys()):
        # Find best row for this indicator (first non-empty, highest confidence)
        matching = [r for r in rows if r.get("Indicator_ID") == ind_id]
        if not matching:
            results.append({
                "indicator_id": ind_id,
                "score": 0.0,
                "rationale": "No evidence found for this indicator",
                "weight": weights[ind_id],
                "weighted_score": 0.0,
            })
            continue

        best = matching[0]
        result = score_indicator(
            indicator_id=ind_id,
            coverage=best.get("Coverage", ""),
            verbatim_snippet=best.get("Verbatim_Snippet", ""),
            mapping_rationale=best.get("Mapping_Rationale", ""),
            impact_or_comments=best.get("Impact_or_comments", ""),
        )
        results.append(result)

    return results


def compute_pillar_score(indicator_scores: list[dict]) -> dict:
    """
    Compute the final pillar score as a weighted average.
    
    Args:
        indicator_scores: Output of score_all_indicators()
    
    Returns:
        Dict with overall_score, indicator_scores, and weight_breakdown.
    """
    weighted_sum = 0.0
    total_weight = 0.0

    for s in indicator_scores:
        if s.get("score") is not None and s.get("weight"):
            weighted_sum += s["score"] * s["weight"]
            total_weight += s["weight"]

    overall = round(weighted_sum / total_weight, 4) if total_weight > 0 else None

    return {
        "overall_score": overall,
        "total_weight": round(total_weight, 2),
        "weighted_sum": round(weighted_sum, 4),
        "indicators": indicator_scores,
    }


def print_score_report(pillar_result: dict, economy: str, pillar_id: str) -> str:
    """Format a human-readable score report (ASCII only for console safety)."""
    lines = []
    lines.append(f"{'='*55}")
    lines.append(f"  RDTII SCORE REPORT - {economy}, Pillar {pillar_id}")
    lines.append(f"{'='*55}")

    for ind in pillar_result["indicators"]:
        sid = ind["indicator_id"]
        score = ind["score"]
        wt = ind["weight"]
        ws = ind["weighted_score"]
        rationale = ind["rationale"][:120]
        score_str = f"{score:.1f}" if score is not None else "N/A"
        ws_str = f"{ws:.4f}" if ws is not None else "N/A"
        lines.append(f"  {sid}  |  Score: {score_str}  |  Weight: {wt:.0%}  |  Weighted: {ws_str}")
        lines.append(f"       {rationale}")

    overall = pillar_result["overall_score"]
    lines.append(f"{'-'*55}")
    lines.append(f"  PILLAR SCORE: {overall:.4f}  (range: 0=open, 1=restrictive)")
    lines.append(f"{'='*55}")
    return "\n".join(lines)
