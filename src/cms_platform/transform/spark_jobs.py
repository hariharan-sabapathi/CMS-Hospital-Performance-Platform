"""
spark_jobs.py

PySpark ingestion + standardization for the CMS IQR "Emergency Department"
slice. Consolidates repo 4's original `pipelines/ingest_raw_cms_data.py`
and `pipelines/standardize_ed_data.py` into one module under the merged
platform's package layout — same logic, same two-stage design (raw ->
landing -> standardized), now driven by cms_platform.common.settings
instead of a standalone config.py.

Not run in CI: the true raw IQR export (all conditions, all measures) is
too large to commit to source control, so this job's inputs aren't
available in a fresh clone. Its output — hospital_standardized.csv and
ed_throughput_standardized.csv — is committed to data/standardized/ and
picked up from there by the config-driven loader (ingest/loader.py, source
config config/sources/cms_iqr.yml).

Usage (with the real raw file in place):
    python -m cms_platform.transform.spark_jobs ingest
    python -m cms_platform.transform.spark_jobs standardize
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from cms_platform.common.settings import get_dir, is_local

LOGGER = logging.getLogger(__name__)

ED_CONDITION_NAME = "Emergency Department"

HOSPITAL_REFERENCE_COLUMNS = [
    "Facility ID",
    "Facility Name",
    "Address",
    "City/Town",
    "State",
    "ZIP Code",
    "County/Parish",
    "Telephone Number",
]

ED_MEASURE_COLUMNS = [
    "Facility ID",
    "Condition",
    "Measure ID",
    "Measure Name",
    "Score",
    "Sample",
    "Footnote",
    "Start Date",
    "End Date",
]

# Measures that report a numeric time-based score (minutes). All other ED
# measures (e.g. EDV = volume category, OP_22 = % left before seen) keep
# Score as a categorical/percentage string.
NUMERIC_MINUTE_MEASURES = {"OP_18a", "OP_18b", "OP_18c", "OP_18d"}


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
    )


def get_spark_session(app_name: str) -> SparkSession:
    return (
        SparkSession.builder.appName(app_name)
        .master("local[*]")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )


def write_extract(df: DataFrame, output_path: str, single_file: bool = True) -> None:
    write = (df.coalesce(1) if single_file else df).write.mode("overwrite").option("header", True)

    if not is_local():
        write.csv(output_path)
        LOGGER.info("Wrote extract to %s", output_path)
        return

    local_output_path = Path(output_path)
    tmp_dir = local_output_path.with_suffix(".tmp_dir")
    write.csv(str(tmp_dir))

    part_file = next(tmp_dir.glob("part-*.csv"))
    local_output_path.parent.mkdir(parents=True, exist_ok=True)
    part_file.replace(local_output_path)

    for leftover in tmp_dir.glob("*"):
        leftover.unlink()
    tmp_dir.rmdir()
    LOGGER.info("Wrote extract to %s", local_output_path)


def _validate(df: DataFrame, key_columns: list[str], name: str, check_duplicates: bool = False) -> None:
    row_count = df.count()
    if row_count == 0:
        raise ValueError(f"Validation failed: '{name}' extract is empty.")

    for key in key_columns:
        null_count = df.filter(F.col(key).isNull()).count()
        if null_count > 0:
            raise ValueError(
                f"Validation failed: '{name}' extract has {null_count} null values in key column '{key}'."
            )

    if check_duplicates:
        duplicate_count = df.groupBy(*key_columns).count().filter(F.col("count") > 1).count()
        if duplicate_count > 0:
            raise ValueError(
                f"Validation failed: '{name}' extract has {duplicate_count} "
                f"duplicate key combinations across {key_columns}."
            )

    LOGGER.info("Validation passed for '%s' extract (%d rows).", name, row_count)


# --- Stage 1: raw -> landing ------------------------------------------------


def read_raw_extract(spark: SparkSession, input_path: str) -> DataFrame:
    if is_local() and not Path(input_path).exists():
        raise FileNotFoundError(f"Raw source file not found: {input_path}")

    LOGGER.info("Reading raw CMS extract from %s", input_path)
    df = (
        spark.read.option("header", True)
        .option("inferSchema", False)
        .option("multiLine", True)
        .option("escape", '"')
        .csv(input_path)
    )
    LOGGER.info("Raw extract loaded: %d rows, %d columns", df.count(), len(df.columns))
    return df


def run_ingest(input_path: str | None = None, output_dir: str | None = None) -> None:
    """Filter the raw multi-condition IQR export to ED and split into two landing extracts."""
    input_path = input_path or f"{get_dir('raw')}/Timely_and_Effective_Care-Hospital_SOURCE.csv"
    output_dir = output_dir or str(get_dir("raw"))

    spark = get_spark_session("cms_ingest_raw")
    try:
        raw_df = read_raw_extract(spark, input_path)
        ed_df = raw_df.filter(F.col("Condition") == ED_CONDITION_NAME)
        LOGGER.info("Filtered to Condition == '%s': %d rows", ED_CONDITION_NAME, ed_df.count())

        hospital_reference = ed_df.select(*HOSPITAL_REFERENCE_COLUMNS).dropDuplicates(["Facility ID"])
        ed_measures = ed_df.select(*ED_MEASURE_COLUMNS)

        _validate(hospital_reference, ["Facility ID"], "cms_hospital_reference")
        _validate(ed_measures, ["Facility ID", "Measure ID"], "cms_ed_throughput_extract")

        write_extract(hospital_reference, f"{output_dir}/cms_hospital_reference.csv")
        write_extract(ed_measures, f"{output_dir}/cms_ed_throughput_extract.csv")
        LOGGER.info("Ingestion pipeline completed successfully.")
    finally:
        spark.stop()


# --- Stage 2: landing -> standardized ---------------------------------------


def standardize_hospital_reference(hospital_df: DataFrame) -> DataFrame:
    return (
        hospital_df.dropDuplicates(["Facility ID"])
        .withColumn("Facility Name", F.trim(F.col("Facility Name")))
        .withColumn("State", F.upper(F.trim(F.col("State"))))
        .withColumn("ZIP Code", F.lpad(F.trim(F.col("ZIP Code")), 5, "0"))
        .na.fill({"County/Parish": "UNKNOWN", "Telephone Number": "UNKNOWN"})
        .select(
            F.lpad(F.trim(F.col("Facility ID")), 6, "0").alias("facility_id"),
            F.col("Facility Name").alias("facility_name"),
            F.col("Address").alias("address"),
            F.col("City/Town").alias("city"),
            F.col("State").alias("state"),
            F.col("ZIP Code").alias("zip_code"),
            F.col("County/Parish").alias("county"),
            F.col("Telephone Number").alias("telephone_number"),
        )
    )


def standardize_ed_measures(measure_df: DataFrame) -> DataFrame:
    return (
        measure_df.dropDuplicates(["Facility ID", "Measure ID", "Start Date", "End Date"])
        .withColumn(
            "score_numeric",
            F.when(
                F.col("Measure ID").isin(list(NUMERIC_MINUTE_MEASURES))
                & (~F.col("Score").isin("Not Available", "N/A", ""))
                & F.col("Score").isNotNull(),
                F.col("Score").cast("double"),
            ).otherwise(F.lit(None).cast("double")),
        )
        .withColumn(
            "score_available",
            ~F.col("Score").isin("Not Available", "N/A", "") & F.col("Score").isNotNull(),
        )
        .withColumn("start_date", F.to_date("Start Date", "MM/dd/yyyy"))
        .withColumn("end_date", F.to_date("End Date", "MM/dd/yyyy"))
        .select(
            F.lpad(F.trim(F.col("Facility ID")), 6, "0").alias("facility_id"),
            F.col("Measure ID").alias("measure_id"),
            F.col("Measure Name").alias("measure_name"),
            F.col("start_date"),
            F.col("end_date"),
            F.col("score_numeric"),
            F.col("Score").alias("score_raw"),
            F.col("score_available"),
            F.col("Sample").alias("sample_size"),
            F.col("Footnote").alias("footnote"),
        )
    )


def run_standardize(input_dir: str | None = None, output_dir: str | None = None) -> None:
    """Standardize the landing extracts and write data/standardized/*.csv."""
    input_dir = input_dir or str(get_dir("raw"))
    output_dir = output_dir or str(get_dir("standardized"))

    spark = get_spark_session("cms_standardize_ed_data")
    try:
        hospital_path = f"{input_dir}/cms_hospital_reference.csv"
        measure_path = f"{input_dir}/cms_ed_throughput_extract.csv"
        if is_local():
            for path in (hospital_path, measure_path):
                if not Path(path).exists():
                    raise FileNotFoundError(f"Expected landing extract not found: {path}. Run 'ingest' first.")

        hospital_df = spark.read.option("header", True).csv(hospital_path)
        measure_df = spark.read.option("header", True).csv(measure_path)

        hospital_standardized = standardize_hospital_reference(hospital_df)
        ed_measures_standardized = standardize_ed_measures(measure_df)

        _validate(hospital_standardized, ["facility_id"], "hospital_standardized", check_duplicates=True)
        _validate(
            ed_measures_standardized,
            ["facility_id", "measure_id", "start_date", "end_date"],
            "ed_throughput_standardized",
            check_duplicates=True,
        )

        write_extract(hospital_standardized, f"{output_dir}/hospital_standardized.csv")
        write_extract(ed_measures_standardized, f"{output_dir}/ed_throughput_standardized.csv")
        LOGGER.info("Standardization pipeline completed successfully.")
    finally:
        spark.stop()


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="CMS IQR PySpark ingestion and standardization jobs.")
    parser.add_argument("stage", choices=["ingest", "standardize"])
    parser.add_argument("--input", type=str, default=None)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    if args.stage == "ingest":
        run_ingest(args.input, args.output)
    else:
        run_standardize(args.input, args.output)


if __name__ == "__main__":
    main()
