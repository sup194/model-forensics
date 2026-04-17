"""Report rendering helpers."""

from __future__ import annotations

from pathlib import Path

import orjson

from model_forensics.schemas import RunReport


def write_report_bundle(report: RunReport, output_dir: Path) -> None:
    """Write JSON and Markdown report artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "summary.json"
    evidence_path = output_dir / "evidence.json"
    markdown_path = output_dir / "report.md"

    summary_payload = {
        "run_id": report.run_id,
        "name": report.name,
        "created_at": report.created_at.isoformat(),
        "matching_enabled": report.matching_enabled,
        "reference_profile_count": report.reference_profile_count,
        "verdict": report.verdict,
        "red_flags": [flag.model_dump(mode="json") for flag in report.red_flags],
        "summary": report.summary,
        "analyses": [analysis.model_dump(mode="json") for analysis in report.analyses],
        "cross_target_comparisons": report.cross_target_comparisons,
    }
    summary_path.write_bytes(orjson.dumps(summary_payload, option=orjson.OPT_INDENT_2))
    evidence_path.write_bytes(
        orjson.dumps(
            [record.model_dump(mode="json") for record in report.prompt_results],
            option=orjson.OPT_INDENT_2,
        )
    )
    markdown_path.write_text(render_markdown_report(report), encoding="utf-8")


def render_markdown_report(report: RunReport) -> str:
    """Render a human-readable Markdown report."""
    lines = [f"# {report.name}", "", f"Run ID: `{report.run_id}`", ""]
    lines.append(f"- Overall verdict: `{report.verdict}`")
    lines.append(f"- Matching enabled: `{report.matching_enabled}`")
    lines.append(f"- Reference profiles available: `{report.reference_profile_count}`")
    lines.append("")
    if report.red_flags:
        lines.append("## Run-Level Red Flags")
        lines.append("")
        for flag in report.red_flags:
            lines.append(
                f"- [{flag.severity}] {flag.category}: {flag.description}"
                + (f" (`{flag.evidence}`)" if flag.evidence else "")
            )
        lines.append("")
    for analysis in report.analyses:
        lines.append(f"## {analysis.target_name}")
        lines.append("")
        lines.append(f"- Claimed model: `{analysis.claimed_model}`")
        lines.append(f"- Anomaly verdict: `{analysis.anomaly_verdict}`")
        lines.append(f"- Matching status: `{analysis.matching_status}`")
        lines.append(f"- Matching mode: `{analysis.matching_mode}`")
        if analysis.api_model_names:
            lines.append(f"- API model names: `{', '.join(analysis.api_model_names)}`")
        if analysis.identity_claims:
            lines.append(f"- Identity claims: `{', '.join(analysis.identity_claims)}`")
        if analysis.knowledge_cutoffs:
            lines.append(f"- Knowledge cutoffs: `{', '.join(analysis.knowledge_cutoffs)}`")
        observed_features = [
            key
            for key, counts in analysis.heuristic_feature_counts.items()
            if counts.get("true", 0) or counts.get("false", 0)
        ]
        if observed_features:
            lines.append(f"- Heuristic features observed: `{', '.join(observed_features)}`")
        if analysis.matches:
            top_match = analysis.matches[0]
            lines.append(
                f"- Top reference match: `{top_match.model_name}` ({top_match.final_score:.2%})"
            )
            lines.append(f"- Live embeddings used: `{analysis.live_embedding_count}`")
            lines.append(
                f"- Reference models with embeddings: `{analysis.reference_models_with_embeddings}`"
            )
        elif analysis.matching_status == "no_references":
            lines.append("- Top reference match: none (`no reference profiles available`)")
        elif analysis.matching_status == "disabled":
            lines.append("- Top reference match: none (`matching disabled`)")
        lines.append("")
        if analysis.red_flags:
            lines.append("### Red Flags")
            lines.append("")
            for flag in analysis.red_flags:
                lines.append(
                    f"- [{flag.severity}] {flag.category}: {flag.description}"
                    + (f" (`{flag.evidence}`)" if flag.evidence else "")
                )
            lines.append("")
        if analysis.matches:
            lines.append("### Reference Matches")
            lines.append("")
            for match in analysis.matches:
                semantic = (
                    f", semantic={match.semantic_score:.2%}"
                    if match.semantic_score is not None
                    else ""
                )
                lines.append(
                    f"- `{match.model_name}` final={match.final_score:.2%}, "
                    f"heuristic={match.heuristic_score:.2%}{semantic}"
                )
            lines.append("")
    if report.cross_target_comparisons:
        lines.append("## Cross-Target Comparisons")
        lines.append("")
        for comparison in report.cross_target_comparisons:
            lines.append(
                f"- `{comparison['target_a']}` vs `{comparison['target_b']}`: "
                f"{comparison['similarity_score']:.2%} ({comparison['verdict']})"
                + (
                    f" shared_phrases={len(comparison.get('shared_phrases', []))}"
                    if comparison.get("shared_phrases")
                    else ""
                )
            )
    return "\n".join(lines).strip() + "\n"
