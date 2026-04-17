"""Anomaly screening logic."""

from __future__ import annotations

import re
from collections import Counter
from itertools import combinations

from model_forensics.schemas import ExecutionRecord, RedFlag, TargetAnalysis
from model_forensics.utils import ratio_containing, ratio_matching, safe_mean


MODEL_NAME_REGEX = (
    r"(?:claude[- ]\d[\w.\-]*|gpt[- ]\d[\w.\-]*|gemini[- ][\w.\-]*|"
    r"llama[- ]\d[\w.\-]*|mistral[\w.\-]*|kimi[\w.\-]*|command[\w.\-]*)"
)
MODEL_NAME_PATTERN = re.compile(MODEL_NAME_REGEX, re.IGNORECASE)
SELF_IDENTIFICATION_PATTERNS = [
    re.compile(
        rf"\b(?:i am|i'm|as an?)\s+(?:an?\s+)?(?P<claim>{MODEL_NAME_REGEX})\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:my|the)\s+(?:exact\s+)?model(?:\s+name|\s+identifier)?\s+is\s+(?P<claim>{MODEL_NAME_REGEX})\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:true|real)\s+model(?:\s+name)?\s+is\s+(?P<claim>{MODEL_NAME_REGEX})\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bdeveloped by\s+[^.!?\n]+?\s+and\s+(?:my\s+)?model(?:\s+name)?\s+is\s+(?P<claim>{MODEL_NAME_REGEX})\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^\s*(?P<claim>{MODEL_NAME_REGEX})\s*[.!]?\s*$",
        re.IGNORECASE,
    ),
]
KNOWLEDGE_CUTOFF_PATTERN = re.compile(
    r"(?:cutoff|knowledge|training)[\s\w]*(?:is|was|in|until|through|up to)?\s*"
    r"((?:january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+\d{4}|\d{4}[-/]\d{2}(?:[-/]\d{2})?)",
    re.IGNORECASE,
)
PROXY_PATTERN = re.compile(
    r"proxy|relay|intermediary|managed\s+server|forwarding|middleware",
    re.IGNORECASE,
)


def analyze_anomalies(records: list[ExecutionRecord]) -> dict[str, object]:
    """Build anomaly findings for one target."""
    fingerprint = build_behavior_fingerprint(records)
    identity_claims = extract_identity_claims(records)
    knowledge_cutoffs = extract_knowledge_cutoffs(records)
    api_model_names = extract_api_model_names(records)
    proxy_indicators = extract_proxy_indicators(records)
    red_flags = collect_red_flags(
        records,
        identity_claims,
        knowledge_cutoffs,
        api_model_names,
        proxy_indicators,
        fingerprint,
    )
    verdict = determine_verdict(red_flags)
    return {
        "behavior_fingerprint": fingerprint,
        "identity_claims": identity_claims,
        "knowledge_cutoffs": knowledge_cutoffs,
        "api_model_names": api_model_names,
        "proxy_indicators": proxy_indicators,
        "red_flags": red_flags,
        "verdict": verdict,
    }


def build_behavior_fingerprint(records: list[ExecutionRecord]) -> dict[str, object]:
    """Build a style-oriented behavior fingerprint."""
    valid_texts = [record.response_text for record in records if record.response_text and not record.error_message]
    latencies = [record.latency_ms for record in records if record.latency_ms is not None]
    tokens = [record.total_tokens for record in records if record.total_tokens is not None]

    if not valid_texts:
        return {"error": "No valid responses"}

    lengths = [len(text) for text in valid_texts]
    word_counts = [len(text.split()) for text in valid_texts]
    all_words = re.findall(r"\b[a-zA-Z]+\b", " ".join(valid_texts).lower())
    unique_ratio = round(len(set(all_words)) / max(len(all_words), 1), 4)

    return {
        "style": {
            "avg_char_length": safe_mean(lengths),
            "avg_word_count": safe_mean(word_counts),
            "min_length": min(lengths),
            "max_length": max(lengths),
            "uses_markdown": ratio_matching(valid_texts, r"[#*`\-\|]"),
            "uses_bullet_lists": ratio_matching(valid_texts, r"^[\s]*[-*•]", re.MULTILINE),
            "uses_numbered_lists": ratio_matching(valid_texts, r"^[\s]*\d+[.)]\s", re.MULTILINE),
            "uses_code_blocks": ratio_matching(valid_texts, r"```"),
        },
        "vocabulary": {
            "unique_ratio": unique_ratio,
            "hedging_ratio": ratio_containing(
                valid_texts,
                ["perhaps", "maybe", "might", "could be", "it's possible", "arguably"],
            ),
            "confidence_ratio": ratio_containing(
                valid_texts,
                ["certainly", "definitely", "absolutely", "clearly", "obviously"],
            ),
        },
        "structure": {
            "avg_paragraph_count": safe_mean([text.count("\n\n") + 1 for text in valid_texts]),
            "avg_line_count": safe_mean([text.count("\n") + 1 for text in valid_texts]),
            "starts_with_greeting_ratio": ratio_matching(
                valid_texts,
                r"^(Hi|Hello|Hey|Sure|Of course|Great|Certainly)",
            ),
            "ends_with_offer_ratio": ratio_matching(
                valid_texts,
                r"(let me know|feel free|happy to help|hope this helps|any questions)\s*[.!?]?\s*$",
                re.IGNORECASE,
            ),
        },
        "metadata": {
            "avg_latency_ms": safe_mean([latency for latency in latencies if latency is not None]),
            "avg_tokens": safe_mean([token for token in tokens if token is not None]),
            "total_results": len(valid_texts),
            "error_count": sum(1 for record in records if record.error_message),
        },
    }


def compare_target_fingerprints(
    target_fingerprints: dict[str, dict[str, object]],
    target_records: dict[str, list[ExecutionRecord]] | None = None,
) -> list[dict[str, object]]:
    """Compare behavior fingerprints across targets."""
    names = list(target_fingerprints.keys())
    comparisons: list[dict[str, object]] = []
    for index, left_name in enumerate(names):
        for right_name in names[index + 1 :]:
            score = _fingerprint_similarity(target_fingerprints[left_name], target_fingerprints[right_name])
            verdict = "SAME_MODEL" if score >= 0.85 else "INCONCLUSIVE" if score > 0.5 else "DIFFERENT_MODELS"
            shared_phrases: list[str] = []
            if target_records is not None:
                shared_phrases = _find_shared_phrases(
                    target_records.get(left_name, []),
                    target_records.get(right_name, []),
                )
            comparisons.append(
                {
                    "target_a": left_name,
                    "target_b": right_name,
                    "similarity_score": round(score, 4),
                    "verdict": verdict,
                    "shared_phrases": shared_phrases[:10],
                }
            )
    return comparisons


def extract_identity_claims(records: list[ExecutionRecord]) -> list[str]:
    """Extract self-reported model names from identity responses."""
    claims: set[str] = set()
    for record in records:
        if record.category != "identity" or not record.response_text:
            continue
        claims.update(_extract_claims_from_text(record.response_text))
    return sorted(claims)


def extract_knowledge_cutoffs(records: list[ExecutionRecord]) -> list[str]:
    """Extract cutoff dates from response text."""
    cutoffs: list[str] = []
    for record in records:
        if not record.response_text:
            continue
        matches = KNOWLEDGE_CUTOFF_PATTERN.findall(record.response_text)
        cutoffs.extend(match.strip() for match in matches)
    return cutoffs


def extract_api_model_names(records: list[ExecutionRecord]) -> list[str]:
    """Extract model names returned by the API metadata."""
    names: set[str] = set()
    for record in records:
        if not record.raw_model_name:
            continue
        normalized = _normalize_model_name(record.raw_model_name)
        if normalized:
            names.add(normalized)
    return sorted(names)


def extract_proxy_indicators(records: list[ExecutionRecord]) -> list[str]:
    """Extract proxy-related phrases that appear in responses."""
    indicators: set[str] = set()
    for record in records:
        if not record.response_text:
            continue
        indicators.update(match.group(0).lower() for match in PROXY_PATTERN.finditer(record.response_text))
    return sorted(indicators)


def collect_red_flags(
    records: list[ExecutionRecord],
    identity_claims: list[str],
    knowledge_cutoffs: list[str],
    api_model_names: list[str],
    proxy_indicators: list[str],
    fingerprint: dict[str, object],
) -> list[RedFlag]:
    """Collect structured anomaly findings."""
    flags: list[RedFlag] = []
    requested_name = records[0].claimed_model.lower() if records else ""
    mismatches = [claim for claim in identity_claims if not _names_match(requested_name, claim)]
    if mismatches:
        flags.append(
            RedFlag(
                severity="HIGH",
                category="identity",
                description=f"Target self-identifies differently from claimed model '{records[0].claimed_model}'",
                evidence=", ".join(mismatches[:5]),
            )
        )

    if api_model_names and len(api_model_names) > 1:
        flags.append(
            RedFlag(
                severity="HIGH",
                category="metadata",
                description="API returned inconsistent raw model names across responses",
                evidence=", ".join(api_model_names[:5]),
            )
        )

    if api_model_names and all(not _names_match(requested_name, api_name) for api_name in api_model_names):
        flags.append(
            RedFlag(
                severity="HIGH",
                category="metadata",
                description=f"API metadata model name differs from claimed model '{records[0].claimed_model}'",
                evidence=", ".join(api_model_names[:5]),
            )
        )

    unique_cutoffs = sorted(set(knowledge_cutoffs))
    if len(unique_cutoffs) > 1:
        flags.append(
            RedFlag(
                severity="HIGH",
                category="consistency",
                description="Knowledge cutoff claims are inconsistent across responses",
                evidence=", ".join(unique_cutoffs),
            )
        )

    avg_latency = _safe_nested_float(fingerprint, "metadata", "avg_latency_ms")
    total_results = _safe_nested_float(fingerprint, "metadata", "total_results")
    if avg_latency is not None and avg_latency > 10_000:
        flags.append(
            RedFlag(
                severity="MEDIUM",
                category="latency",
                description=f"Average latency is unusually high at {avg_latency:.0f}ms",
                evidence=f"Computed across {int(total_results or 0)} responses",
            )
        )

    if proxy_indicators:
        flags.append(
            RedFlag(
                severity="LOW",
                category="proxy",
                description="Responses mention proxy or intermediary behavior",
                evidence=", ".join(proxy_indicators[:5]),
            )
        )

    return _sort_flags(flags)


def determine_verdict(flags: list[RedFlag]) -> str:
    """Determine the anomaly verdict."""
    high_flags = sum(1 for flag in flags if flag.severity == "HIGH")
    medium_flags = sum(1 for flag in flags if flag.severity == "MEDIUM")
    if high_flags >= 2:
        return "FRAUD_DETECTED"
    if high_flags == 1 and medium_flags >= 1:
        return "FRAUD_DETECTED"
    if high_flags == 0 and medium_flags == 0:
        return "LEGITIMATE"
    return "INCONCLUSIVE"


def collect_run_red_flags(
    analyses: list[TargetAnalysis],
    comparisons: list[dict[str, object]],
) -> list[RedFlag]:
    """Aggregate target-level and cross-target flags into a run-level view."""
    flags = [flag for analysis in analyses for flag in analysis.red_flags]
    for comparison in comparisons:
        if comparison.get("verdict") != "SAME_MODEL":
            continue
        flags.append(
            RedFlag(
                severity="HIGH",
                category="similarity",
                description=(
                    f"Targets '{comparison['target_a']}' and '{comparison['target_b']}' "
                    "appear to be the same underlying model"
                ),
                evidence=(
                    f"similarity={comparison['similarity_score']:.2%}, "
                    f"shared_phrases={len(comparison.get('shared_phrases', []))}"
                ),
            )
        )
    return _sort_flags(flags)


def build_run_summary(
    run_name: str,
    analyses: list[TargetAnalysis],
    red_flags: list[RedFlag],
    verdict: str,
) -> str:
    """Build a human-readable run summary."""
    lines = [f"Deep Analysis — Verdict: {verdict}", ""]
    lines.append(f"Run: {run_name}")
    lines.append(f"Targets analyzed: {len(analyses)}")
    lines.append(f"Red flags detected: {len(red_flags)}")
    lines.append("")
    for analysis in analyses:
        lines.append(f"• {analysis.target_name}")
        lines.append(f"  Claimed model: {analysis.claimed_model}")
        lines.append(f"  Target verdict: {analysis.anomaly_verdict}")
        latency = _safe_nested_float(analysis.behavior_fingerprint, "metadata", "avg_latency_ms")
        total_results = _safe_nested_float(analysis.behavior_fingerprint, "metadata", "total_results")
        if latency is not None:
            lines.append(f"  Avg latency: {latency:.0f}ms")
        if total_results is not None:
            lines.append(f"  Responses analyzed: {int(total_results)}")
        if analysis.api_model_names:
            lines.append(f"  API model names: {', '.join(analysis.api_model_names[:3])}")
        if analysis.identity_claims:
            lines.append(f"  Identity claims: {', '.join(analysis.identity_claims[:3])}")
        if analysis.knowledge_cutoffs:
            lines.append(f"  Knowledge cutoffs: {', '.join(sorted(set(analysis.knowledge_cutoffs))[:3])}")
        if analysis.matches:
            top_match = analysis.matches[0]
            lines.append(f"  Top reference match: {top_match.model_name} ({top_match.final_score:.2%})")
    if red_flags:
        lines.append("")
        lines.append("Red Flags:")
        for flag in red_flags:
            lines.append(f"  [{flag.severity}] {flag.category}: {flag.description}")
    return "\n".join(lines)


def _fingerprint_similarity(left: dict[str, object], right: dict[str, object]) -> float:
    if "error" in left or "error" in right:
        return 0.5
    candidates = [
        _compare_numeric(left, right, "style", "avg_word_count"),
        _compare_numeric(left, right, "style", "uses_markdown"),
        _compare_numeric(left, right, "style", "uses_bullet_lists"),
        _compare_numeric(left, right, "vocabulary", "unique_ratio"),
        _compare_numeric(left, right, "vocabulary", "hedging_ratio"),
        _compare_numeric(left, right, "vocabulary", "confidence_ratio"),
        _compare_numeric(left, right, "structure", "avg_paragraph_count"),
        _compare_numeric(left, right, "structure", "starts_with_greeting_ratio"),
    ]
    valid = [candidate for candidate in candidates if candidate is not None]
    if not valid:
        return 0.5
    return sum(valid) / len(valid)


def _compare_numeric(
    left: dict[str, object],
    right: dict[str, object],
    section: str,
    key: str,
) -> float | None:
    value_left = _safe_nested_float(left, section, key)
    value_right = _safe_nested_float(right, section, key)
    if value_left is None or value_right is None:
        return None
    max_value = max(abs(value_left), abs(value_right), 0.001)
    return 1.0 - abs(value_left - value_right) / max_value


def _safe_nested_float(payload: dict[str, object], section: str, key: str) -> float | None:
    section_payload = payload.get(section)
    if not isinstance(section_payload, dict):
        return None
    value = section_payload.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _extract_claims_from_text(text: str) -> set[str]:
    normalized_text = " ".join(text.split())
    claims: set[str] = set()
    for pattern in SELF_IDENTIFICATION_PATTERNS:
        for match in pattern.finditer(normalized_text):
            claim = _normalize_model_name(match.group("claim"))
            if claim:
                claims.add(claim)
    if claims:
        return claims

    first_sentence = re.split(r"(?<=[.!?])\s+", normalized_text, maxsplit=1)[0]
    if len(first_sentence) <= 80:
        matches = MODEL_NAME_PATTERN.findall(first_sentence)
        if len(matches) == 1:
            claim = _normalize_model_name(matches[0])
            if claim:
                claims.add(claim)
    return claims


def _normalize_model_name(value: str) -> str:
    cleaned = value.strip().strip("`'\".,:;()[]{}")
    cleaned = re.sub(r"\s+", "-", cleaned.lower())
    return cleaned


def _names_match(requested: str, claimed: str) -> bool:
    normalized_requested = _strip_snapshot_suffix(_normalize_model_name(requested))
    normalized_claimed = _strip_snapshot_suffix(_normalize_model_name(claimed))
    return normalized_requested == normalized_claimed


def _strip_snapshot_suffix(value: str) -> str:
    parts = value.split("-")
    while parts and re.fullmatch(r"\d{4,8}", parts[-1]):
        parts.pop()
    return "-".join(parts)


def _find_shared_phrases(
    left_records: list[ExecutionRecord],
    right_records: list[ExecutionRecord],
) -> list[str]:
    left_phrases = _common_phrases(left_records)
    right_phrases = _common_phrases(right_records)
    shared = [phrase for phrase in left_phrases if phrase in right_phrases]
    shared.sort(key=lambda phrase: (-min(left_phrases[phrase], right_phrases[phrase]), phrase))
    return shared


def _common_phrases(records: list[ExecutionRecord]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for record in records:
        if not record.response_text:
            continue
        normalized = re.sub(r"\s+", " ", record.response_text.lower())
        words = re.findall(r"[a-z0-9']+", normalized)
        for window_size in (3, 4):
            for index in range(len(words) - window_size + 1):
                phrase = " ".join(words[index : index + window_size])
                if len(phrase) >= 18:
                    counter[phrase] += 1
    return counter


def _sort_flags(flags: list[RedFlag]) -> list[RedFlag]:
    return sorted(flags, key=lambda flag: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(flag.severity, 3))
