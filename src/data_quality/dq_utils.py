from pyspark.sql import functions as F
from pyspark.sql import SparkSession

LOG_TABLE = "brazilian_ecommerce.prod.data_quality_log"


class DataQualityError(Exception):
    """Raised when a data quality check marked raise_on_failure=True fails."""
    pass


def ensure_log_table_exists(spark: SparkSession) -> None:
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {LOG_TABLE} (
            check_id STRING,
            run_timestamp TIMESTAMP,
            layer STRING,
            table_name STRING,
            check_name STRING,
            status STRING,
            row_count BIGINT,
            details STRING
        )
        COMMENT 'Data quality check results across bronze, staging and gold layers'
    """)


def log_check(
    spark: SparkSession,
    layer: str,
    table_name: str,
    check_name: str,
    passed: bool,
    row_count: int = None,
    details: str = None,
    raise_on_failure: bool = False,
) -> None:
    status = "PASS" if passed else "FAIL"
    log_row = spark.createDataFrame(
        [(f"{table_name}_{check_name}_{F.current_timestamp()}", layer, table_name, check_name, status, row_count, details)],
        schema="check_id STRING, layer STRING, table_name STRING, check_name STRING, status STRING, row_count BIGINT, details STRING",
    ).withColumn("run_timestamp", F.current_timestamp())

    log_row.write.mode("append").saveAsTable(LOG_TABLE)

    symbol = "✓" if passed else "✗"
    print(f"{symbol} [{layer}] {table_name} — {check_name}: {status}" + (f" ({details})" if details else ""))

    if not passed and raise_on_failure:
        raise DataQualityError(
            f"[{layer}] {table_name} — {check_name} FAILED: {details or 'no details'}"
        )


def check_not_null(spark, layer, table_name, df, column, raise_on_failure: bool = False):
    null_count = df.filter(F.col(column).isNull()).count()
    passed = null_count == 0
    log_check(spark, layer, table_name, f"not_null_{column}", passed, row_count=null_count,
               details=None if passed else f"{null_count} null rows in {column}",
               raise_on_failure=raise_on_failure)
    return passed


def check_unique(spark, layer, table_name, df, columns: list, raise_on_failure: bool = False):
    total = df.count()
    distinct = df.select(*columns).distinct().count()
    passed = total == distinct
    log_check(spark, layer, table_name, f"unique_{'_'.join(columns)}", passed, row_count=total - distinct,
               details=None if passed else f"{total - distinct} duplicate rows on {columns}",
               raise_on_failure=raise_on_failure)
    return passed


def check_row_count_above(spark, layer, table_name, df, min_rows: int, raise_on_failure: bool = False):
    count = df.count()
    passed = count >= min_rows
    log_check(spark, layer, table_name, "row_count_above_threshold", passed, row_count=count,
               details=None if passed else f"only {count} rows, expected at least {min_rows}",
               raise_on_failure=raise_on_failure)
    return passed


def check_no_orphans(spark, layer, table_name, df, fk_column, ref_df, ref_column, raise_on_failure: bool = False):
    orphans = df.join(ref_df.select(ref_column), df[fk_column] == ref_df[ref_column], "left_anti")
    orphan_count = orphans.count()
    passed = orphan_count == 0
    log_check(spark, layer, table_name, f"fk_integrity_{fk_column}", passed, row_count=orphan_count,
               details=None if passed else f"{orphan_count} rows with {fk_column} not found in reference table",
               raise_on_failure=raise_on_failure)
    return passed

def check_value_in_range(spark, layer, table_name, df, column, min_val, max_val, raise_on_failure: bool = False):
    invalid = df.filter(
        F.col(column).isNotNull() & ((F.col(column) < min_val) | (F.col(column) > max_val))
    ).count()
    passed = invalid == 0
    log_check(spark, layer, table_name, f"{column}_in_range_{min_val}_{max_val}", passed, row_count=invalid,
               details=None if passed else f"{invalid} rows with {column} outside [{min_val}, {max_val}]",
               raise_on_failure=raise_on_failure)
    return passed