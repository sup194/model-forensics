"""Typer CLI entrypoint."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections import defaultdict
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table

from model_forensics.analyzers import (
    analyze_anomalies,
    annotate_matching_records,
    build_heuristic_fingerprint,
    build_run_summary,
    collect_feature_counts,
    compare_record_sets,
    compare_target_fingerprints,
    collect_run_red_flags,
    determine_verdict,
    score_reference_candidates,
)
from model_forensics.catalog import anomaly_cases, matching_cases
from model_forensics.config import (
    DEFAULT_DB_PATH,
    DEFAULT_MAX_CONCURRENT_CASES,
    DEFAULT_PROMPT_CATALOG_VERSION,
    load_local_env,
    resolve_secret,
)
from model_forensics.embedding import OpenAIEmbeddingClient
from model_forensics.execution.runner import run_cases, run_cases_for_targets
from model_forensics.reports import write_report_bundle
from model_forensics.schemas import (
    ComparisonResult,
    EmbeddingRecord,
    ExecutionRecord,
    ModelTarget,
    ProfileRecord,
    RunConfig,
    RunReport,
    TargetAnalysis,
)
from model_forensics.storage import SQLiteStore


console = Console()
app = typer.Typer(no_args_is_help=True, help="LLM anomaly screening and model matching CLI.")
refs_app = typer.Typer(no_args_is_help=True, help="Manage local reference models.")
runs_app = typer.Typer(no_args_is_help=True, help="Inspect stored run history.")
app.add_typer(refs_app, name="refs")
app.add_typer(runs_app, name="runs")


@app.command()
def inspect(
    config_path: Path = typer.Argument(..., exists=True, readable=True),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
    out: Path | None = typer.Option(None, "--out", help="Directory to write report artifacts."),
    top_k: int = typer.Option(5, "--top-k", min=1, max=20),
    matching: bool = typer.Option(True, "--matching/--no-matching", help="Enable reference matching."),
    embeddings: bool = typer.Option(False, "--embeddings", help="Enable semantic matching."),
    alpha: float = typer.Option(0.5, "--alpha", min=0.0, max=1.0),
    anomaly_categories: str | None = typer.Option(
        None,
        "--anomaly-categories",
        help="Comma-separated anomaly categories to run. Default is all.",
    ),
    matching_categories: str | None = typer.Option(
        None,
        "--matching-categories",
        help="Comma-separated matching categories to run. Default is all.",
    ),
    max_concurrent: int = typer.Option(
        DEFAULT_MAX_CONCURRENT_CASES,
        "--max-concurrent",
        min=1,
        max=20,
        help="Maximum concurrent prompt cases per target.",
    ),
) -> None:
    """Inspect one or more targets and write a combined report."""
    config = _load_run_config(config_path)
    store = SQLiteStore(db)
    report = asyncio.run(
        _inspect_async(
            config,
            store,
            top_k=top_k,
            matching=matching,
            embeddings=embeddings,
            alpha=alpha,
            anomaly_categories=_parse_categories(anomaly_categories),
            matching_categories=_parse_categories(matching_categories),
            max_concurrent=max_concurrent,
        )
    )
    store.save_run(report)
    if out is not None:
        write_report_bundle(report, out)
    _print_inspect_summary(report)


@app.command()
def profile(
    config_path: Path = typer.Argument(..., exists=True, readable=True),
    save_as: str = typer.Option(..., "--save-as", help="Reference model name."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
    runs: int = typer.Option(3, "--runs", min=1, max=20),
    embeddings: bool = typer.Option(False, "--embeddings", help="Store response embeddings."),
    matching_categories: str | None = typer.Option(
        None,
        "--matching-categories",
        help="Comma-separated matching categories to profile. Default is all.",
    ),
    max_concurrent: int = typer.Option(
        DEFAULT_MAX_CONCURRENT_CASES,
        "--max-concurrent",
        min=1,
        max=20,
        help="Maximum concurrent prompt cases per target.",
    ),
) -> None:
    """Profile a known model and save it as a reference."""
    config = _load_run_config(config_path)
    if len(config.targets) != 1:
        raise typer.BadParameter("profile expects exactly one target in the config file")
    store = SQLiteStore(db)
    target = config.targets[0]
    profile_record, embedding_records = asyncio.run(
        _profile_async(
            target,
            save_as=save_as,
            runs=runs,
            embeddings=embeddings,
            matching_categories=_parse_categories(matching_categories),
            max_concurrent=max_concurrent,
        )
    )
    store.save_reference(profile_record, embedding_records)
    console.print(f"[green]Saved reference[/green] {save_as} to {db}")


@app.command()
def compare(
    run_id_a: str = typer.Argument(..., help="First stored run ID."),
    run_id_b: str = typer.Argument(..., help="Second stored run ID."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
    target_a: str | None = typer.Option(None, "--target-a", help="Target name within the first run."),
    target_b: str | None = typer.Option(None, "--target-b", help="Target name within the second run."),
) -> None:
    """Compare two stored runs using shared behavioral dimensions."""
    store = SQLiteStore(db)
    stored_a = store.get_run(run_id_a)
    stored_b = store.get_run(run_id_b)
    if stored_a is None:
        raise typer.BadParameter(f"Run '{run_id_a}' was not found in {db}")
    if stored_b is None:
        raise typer.BadParameter(f"Run '{run_id_b}' was not found in {db}")

    report_a = RunReport.model_validate(stored_a.report)
    report_b = RunReport.model_validate(stored_b.report)

    selected_target_a = _select_target_name(report_a, target_a)
    selected_target_b = _select_target_name(report_b, target_b)
    records_a = _records_for_target(report_a.prompt_results, selected_target_a)
    records_b = _records_for_target(report_b.prompt_results, selected_target_b)

    comparison = compare_record_sets(
        run_id_a=report_a.run_id,
        run_id_b=report_b.run_id,
        target_a=selected_target_a,
        target_b=selected_target_b,
        records_a=records_a,
        records_b=records_b,
    )
    _print_comparison_summary(comparison)


@refs_app.command("list")
def refs_list(
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """List locally stored reference models."""
    store = SQLiteStore(db)
    references = store.list_references()
    embedding_counts = store.get_reference_embedding_counts()
    table = Table(title="Reference Models")
    table.add_column("Model")
    table.add_column("Provider")
    table.add_column("Protocol")
    table.add_column("Features")
    table.add_column("Embeddings")
    table.add_column("Created")
    for reference in references:
        table.add_row(
            reference.model_name,
            reference.provider,
            reference.protocol,
            str(len(reference.fingerprint)),
            str(embedding_counts.get(reference.model_name, 0)),
            reference.created_at.isoformat(timespec="seconds"),
        )
    console.print(table)


@refs_app.command("show")
def refs_show(
    model_name: str = typer.Argument(..., help="Reference model name."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Show one locally stored reference model."""
    store = SQLiteStore(db)
    reference = store.get_reference(model_name)
    if reference is None:
        raise typer.BadParameter(f"Reference '{model_name}' was not found in {db}")

    console.print(f"[bold]{reference.model_name}[/bold]")
    console.print(f"provider: {reference.provider}")
    console.print(f"protocol: {reference.protocol}")
    console.print(f"catalog: {reference.prompt_catalog_version}")
    console.print(f"created: {reference.created_at.isoformat(timespec='seconds')}")
    console.print(f"embeddings: {store.get_reference_embedding_count(model_name)}")
    console.print("metadata:")
    for key, value in reference.metadata.items():
        console.print(f"  - {key}: {value}")
    console.print("fingerprint:")
    for key, value in sorted(reference.fingerprint.items()):
        console.print(f"  - {key}: {value:.4f}")


@refs_app.command("delete")
def refs_delete(
    model_name: str = typer.Argument(..., help="Reference model name."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Delete one locally stored reference model."""
    store = SQLiteStore(db)
    deleted = store.delete_reference(model_name)
    if not deleted:
        raise typer.BadParameter(f"Reference '{model_name}' was not found in {db}")
    console.print(f"[green]Deleted reference[/green] {model_name}")


@runs_app.command("list")
def runs_list(
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """List stored inspect runs."""
    store = SQLiteStore(db)
    runs = store.list_runs()
    table = Table(title="Stored Runs")
    table.add_column("Run ID")
    table.add_column("Name")
    table.add_column("Verdict")
    table.add_column("Targets")
    table.add_column("Created")
    for stored_run in runs:
        report = RunReport.model_validate(stored_run.report)
        table.add_row(
            stored_run.run_id,
            stored_run.name,
            report.verdict,
            str(len(report.analyses)),
            stored_run.created_at.isoformat(timespec="seconds"),
        )
    console.print(table)


@runs_app.command("show")
def runs_show(
    run_id: str = typer.Argument(..., help="Stored run ID."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Show one stored run and its analyses."""
    store = SQLiteStore(db)
    stored_run = store.get_run(run_id)
    if stored_run is None:
        raise typer.BadParameter(f"Run '{run_id}' was not found in {db}")
    report = RunReport.model_validate(stored_run.report)

    console.print(f"[bold]{report.name}[/bold]")
    console.print(f"run_id: {report.run_id}")
    console.print(f"created: {report.created_at.isoformat(timespec='seconds')}")
    console.print(f"verdict: {report.verdict}")
    console.print(f"matching_enabled: {report.matching_enabled}")
    console.print(f"reference_profiles: {report.reference_profile_count}")
    if report.summary:
        console.print("summary:")
        for line in report.summary.splitlines():
            console.print(f"  {line}" if line else "")
    if report.red_flags:
        console.print("red_flags:")
        for flag in report.red_flags:
            console.print(f"  - [{flag.severity}] {flag.category}: {flag.description}")
    for analysis in report.analyses:
        console.print("")
        console.print(f"[bold]{analysis.target_name}[/bold]")
        console.print(f"  claimed_model: {analysis.claimed_model}")
        console.print(f"  anomaly_verdict: {analysis.anomaly_verdict}")
        console.print(f"  matching_status: {analysis.matching_status}")
        console.print(f"  matching_mode: {analysis.matching_mode}")
        if analysis.api_model_names:
            console.print(f"  api_model_names: {', '.join(analysis.api_model_names)}")
        if analysis.identity_claims:
            console.print(f"  identity_claims: {', '.join(analysis.identity_claims)}")
        if analysis.knowledge_cutoffs:
            console.print(f"  knowledge_cutoffs: {', '.join(analysis.knowledge_cutoffs)}")
        if analysis.matching_status == "matched":
            console.print(f"  live_embedding_count: {analysis.live_embedding_count}")
            console.print(
                f"  reference_models_with_embeddings: {analysis.reference_models_with_embeddings}"
            )
        if analysis.matches:
            top_match = analysis.matches[0]
            console.print(
                f"  top_match: {top_match.model_name} ({top_match.final_score:.2%})"
            )
    if report.cross_target_comparisons:
        console.print("")
        console.print("cross_target_comparisons:")
        for comparison in report.cross_target_comparisons:
            console.print(
                "  - "
                f"{comparison['target_a']} vs {comparison['target_b']}: "
                f"{comparison['similarity_score']:.2%} ({comparison['verdict']})"
            )


def main() -> None:
    """CLI entrypoint."""
    app()


async def _inspect_async(
    config: RunConfig,
    store: SQLiteStore,
    *,
    top_k: int,
    matching: bool,
    embeddings: bool,
    alpha: float,
    anomaly_categories: set[str] | None,
    matching_categories: set[str] | None,
    max_concurrent: int,
) -> RunReport:
    run_id = str(uuid.uuid4())
    with console.status("Running anomaly cases..."):
        anomaly_results = await run_cases_for_targets(
            config.targets,
            anomaly_cases(anomaly_categories),
            max_concurrent_cases=max_concurrent,
        )
    matching_results: list[ExecutionRecord] = []
    if matching:
        with console.status("Running matching cases..."):
            matching_results = await run_cases_for_targets(
                config.targets,
                matching_cases(matching_categories),
                max_concurrent_cases=max_concurrent,
            )
        matching_results = annotate_matching_records(matching_results)

    analyses: list[TargetAnalysis] = []
    grouped_anomaly = _group_records(anomaly_results)
    grouped_matching = _group_records(matching_results)

    references = store.list_references() if matching else []
    reference_embeddings = store.load_reference_embeddings() if matching and embeddings else {}
    embedding_client = _create_embedding_client(embeddings) if matching else None
    try:
        target_fingerprints: dict[str, dict[str, object]] = {}
        for target in config.targets:
            anomaly_data = analyze_anomalies(grouped_anomaly[target.name])
            target_matching_records = grouped_matching.get(target.name, [])
            heuristic_fingerprint = (
                build_heuristic_fingerprint(target_matching_records) if matching else {}
            )
            heuristic_feature_counts = (
                collect_feature_counts(target_matching_records) if matching else {}
            )
            live_embeddings: list[list[float]] = []
            if embedding_client is not None:
                live_embeddings = await _embed_records(embedding_client, target_matching_records)
            reference_models_with_embeddings = sum(
                1 for reference in references if reference_embeddings.get(reference.model_name)
            )
            matches = (
                score_reference_candidates(
                    live_fingerprint=heuristic_fingerprint,
                    live_embeddings=live_embeddings,
                    references=references,
                    reference_embeddings=reference_embeddings,
                    alpha=alpha,
                    top_k=top_k,
                )
                if matching and references
                else []
            )
            matching_status = "disabled"
            matching_mode = "disabled"
            if matching:
                matching_status = "matched" if references else "no_references"
                if not references:
                    matching_mode = "no_references"
                elif any(match.semantic_score is not None for match in matches):
                    matching_mode = "hybrid"
                else:
                    matching_mode = "heuristic_only"
            target_fingerprints[target.name] = anomaly_data["behavior_fingerprint"]
            analyses.append(
                TargetAnalysis(
                    target_name=target.name,
                    claimed_model=target.claimed_model,
                    anomaly_verdict=anomaly_data["verdict"],
                    matching_status=matching_status,
                    matching_mode=matching_mode,
                    red_flags=anomaly_data["red_flags"],
                    behavior_fingerprint=anomaly_data["behavior_fingerprint"],
                    heuristic_fingerprint=heuristic_fingerprint,
                    heuristic_feature_counts=heuristic_feature_counts,
                    identity_claims=anomaly_data["identity_claims"],
                    knowledge_cutoffs=anomaly_data["knowledge_cutoffs"],
                    api_model_names=anomaly_data["api_model_names"],
                    proxy_indicators=anomaly_data["proxy_indicators"],
                    live_embedding_count=len(live_embeddings),
                    reference_models_with_embeddings=reference_models_with_embeddings,
                    matches=matches,
                )
            )
    finally:
        if embedding_client is not None:
            await embedding_client.close()

    comparisons = compare_target_fingerprints(target_fingerprints, grouped_anomaly)
    run_red_flags = collect_run_red_flags(analyses, comparisons)
    run_verdict = determine_verdict(run_red_flags)
    run_summary = build_run_summary(config.name, analyses, run_red_flags, run_verdict)
    return RunReport(
        run_id=run_id,
        name=config.name,
        config=config,
        matching_enabled=matching,
        reference_profile_count=len(references),
        verdict=run_verdict,
        red_flags=run_red_flags,
        summary=run_summary,
        analyses=analyses,
        cross_target_comparisons=comparisons,
        prompt_results=[*anomaly_results, *matching_results],
    )


async def _profile_async(
    target: ModelTarget,
    *,
    save_as: str,
    runs: int,
    embeddings: bool,
    matching_categories: set[str] | None,
    max_concurrent: int,
) -> tuple[ProfileRecord, list[EmbeddingRecord]]:
    fingerprints: list[dict[str, float]] = []
    all_records: list = []

    for _ in range(runs):
        records = await run_cases(
            target,
            matching_cases(matching_categories),
            max_concurrent_cases=max_concurrent,
        )
        records = annotate_matching_records(records)
        fingerprints.append(build_heuristic_fingerprint(records))
        all_records.extend(records)

    averaged = _average_fingerprints(fingerprints)
    embedding_client = _create_embedding_client(embeddings)
    embedding_records: list[EmbeddingRecord] = []
    try:
        if embedding_client is not None:
            for record in all_records:
                if not record.response_text or record.error_message:
                    continue
                embedding = await embedding_client.embed_text(record.response_text)
                if embedding is None:
                    continue
                embedding_records.append(
                    EmbeddingRecord(
                        model_name=save_as,
                        case_id=record.case_id,
                        category=record.category,
                        prompt_text="\n".join(record.turns),
                        response_text=record.response_text,
                        embedding=embedding,
                    )
                )
    finally:
        if embedding_client is not None:
            await embedding_client.close()

    profile_record = ProfileRecord(
        model_name=save_as,
        provider=target.provider,
        protocol=target.protocol,
        fingerprint=averaged,
        prompt_catalog_version=DEFAULT_PROMPT_CATALOG_VERSION,
        metadata={
            "claimed_model": target.claimed_model,
            "runs": runs,
            "source_target": target.name,
        },
    )
    return profile_record, embedding_records


def _load_run_config(path: Path) -> RunConfig:
    load_local_env(path.parent)
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    config = RunConfig.model_validate(raw)
    resolved_targets = []
    for target in config.targets:
        secret = resolve_secret(target.api_key, target.api_key_env)
        if not secret:
            raise typer.BadParameter(
                f"Target '{target.name}' is missing an api_key or api_key_env secret"
            )
        resolved_targets.append(target.model_copy(update={"api_key": secret}))
    return config.model_copy(update={"targets": resolved_targets})


def _average_fingerprints(fingerprints: list[dict[str, float]]) -> dict[str, float]:
    values_by_key: dict[str, list[float]] = defaultdict(list)
    for fingerprint in fingerprints:
        for key, value in fingerprint.items():
            values_by_key[key].append(value)
    return {
        key: round(sum(values) / len(values), 4)
        for key, values in values_by_key.items()
        if values
    }


def _group_records(records: list) -> dict[str, list]:
    grouped: dict[str, list] = defaultdict(list)
    for record in records:
        grouped[record.target_name].append(record)
    return grouped


def _records_for_target(records: list[ExecutionRecord], target_name: str) -> list[ExecutionRecord]:
    return [record for record in records if record.target_name == target_name]


def _select_target_name(report: RunReport, requested_name: str | None) -> str:
    available_targets = [analysis.target_name for analysis in report.analyses]
    if not available_targets:
        raise typer.BadParameter(f"Run '{report.run_id}' does not contain any target analyses")
    if requested_name is None:
        return available_targets[0]
    if requested_name not in available_targets:
        available = ", ".join(available_targets)
        raise typer.BadParameter(
            f"Target '{requested_name}' was not found in run '{report.run_id}'. Available targets: {available}"
        )
    return requested_name


async def _embed_records(
    embedding_client: OpenAIEmbeddingClient,
    records: list,
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for record in records:
        if not record.response_text or record.error_message:
            continue
        embedding = await embedding_client.embed_text(record.response_text)
        if embedding is not None:
            vectors.append(embedding)
    return vectors


def _create_embedding_client(enabled: bool) -> OpenAIEmbeddingClient | None:
    if not enabled:
        return None
    openai_api_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_api_key:
        raise typer.BadParameter("OPENAI_API_KEY is required when --embeddings is enabled")
    return OpenAIEmbeddingClient(openai_api_key)


def _parse_categories(raw: str | None) -> set[str] | None:
    if raw is None:
        return None
    categories = {item.strip() for item in raw.split(",") if item.strip()}
    return categories or None


def _print_inspect_summary(report: RunReport) -> None:
    console.print(f"[bold]Overall verdict:[/bold] {report.verdict}")
    if report.red_flags:
        console.print(f"[bold]Run-level red flags:[/bold] {len(report.red_flags)}")
    summary = Table(title=f"Run Summary: {report.name}")
    summary.add_column("Target")
    summary.add_column("Claimed")
    summary.add_column("Anomaly Verdict")
    summary.add_column("Matching")
    summary.add_column("Top Match")
    summary.add_column("Top Score")
    for analysis in report.analyses:
        top_match = analysis.matches[0] if analysis.matches else None
        summary.add_row(
            analysis.target_name,
            analysis.claimed_model,
            analysis.anomaly_verdict,
            analysis.matching_status,
            top_match.model_name if top_match is not None else "-",
            f"{top_match.final_score:.2%}" if top_match is not None else "-",
        )
    console.print(summary)


def _print_comparison_summary(comparison: ComparisonResult) -> None:
    table = Table(title="Run Comparison")
    table.add_column("Run A")
    table.add_column("Run B")
    table.add_column("Target A")
    table.add_column("Target B")
    table.add_column("Overall")
    table.add_column("Verdict")
    table.add_row(
        comparison.run_id_a,
        comparison.run_id_b,
        comparison.target_a,
        comparison.target_b,
        f"{comparison.overall_similarity:.2%}",
        comparison.verdict,
    )
    console.print(table)

    detail_table = Table(title="Dimension Scores")
    detail_table.add_column("Dimension")
    detail_table.add_column("Score")
    for dimension, score in comparison.dimensions.items():
        detail_table.add_row(dimension, f"{score:.2%}")
    console.print(detail_table)
