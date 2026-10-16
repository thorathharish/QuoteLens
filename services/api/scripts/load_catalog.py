"""Validate the catalog seed and load it into BigQuery (idempotent: WRITE_TRUNCATE).

    uv run python scripts/load_catalog.py --dry-run                 # validate only, no GCP
    uv run python scripts/load_catalog.py --project my-project      # load into <project>.catalog

Load jobs are free on BigQuery (streaming inserts are not), which keeps this inside the
free tier. `offers_cache` is day-partitioned on `fetched_at`; queries must filter on it.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from app.catalog.rows import CatalogComponent, CatalogCrossRef, CatalogOffer

REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_DIR = REPO_ROOT / "data" / "catalog_seed"
SCHEMA_DIR = REPO_ROOT / "infra" / "bq" / "schemas"

TABLES: dict[str, tuple[str, type[BaseModel]]] = {
    "components": ("components.jsonl", CatalogComponent),
    "offers_cache": ("offers.jsonl", CatalogOffer),
    "crossrefs": ("crossrefs.jsonl", CatalogCrossRef),
}


def read_rows(file_name: str, model: type[BaseModel]) -> list[dict[str, Any]]:
    """Validate every line and return BigQuery-ready JSON rows."""
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    path = SEED_DIR / file_name
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = model.model_validate_json(line)
        except ValidationError as exc:
            errors.append(f"{file_name}:{line_no}: {exc.errors()[0]['msg']}")
            continue
        data = row.model_dump(mode="json")
        if "params" in data:
            data["params"] = json.dumps(data["params"], sort_keys=True)  # BigQuery JSON column
        rows.append(data)
    if errors:
        raise ValueError("Invalid seed rows:\n" + "\n".join(errors))
    return rows


def load(project: str, dataset: str, location: str) -> None:
    from google.cloud import bigquery

    client = bigquery.Client(project=project, location=location)
    for table, (file_name, model) in TABLES.items():
        rows = read_rows(file_name, model)
        schema = client.schema_from_json(str(SCHEMA_DIR / f"{table}.json"))
        config = bigquery.LoadJobConfig(
            schema=schema,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        )
        if table == "offers_cache":
            config.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY, field="fetched_at"
            )
            config.clustering_fields = ["mpn_norm"]
        job = client.load_table_from_json(rows, f"{project}.{dataset}.{table}", job_config=config)
        job.result()
        print(f"loaded {len(rows):>4} rows into {project}.{dataset}.{table}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", help="GCP project id (required unless --dry-run)")
    parser.add_argument("--dataset", default="catalog")
    parser.add_argument("--location", default="us-central1")
    parser.add_argument("--dry-run", action="store_true", help="validate only")
    args = parser.parse_args()

    for table, (file_name, model) in TABLES.items():
        print(f"valid {len(read_rows(file_name, model)):>4} rows for {table}")
    if args.dry_run:
        return 0
    if not args.project:
        parser.error("--project is required unless --dry-run")
    load(args.project, args.dataset, args.location)
    return 0


if __name__ == "__main__":
    sys.exit(main())
