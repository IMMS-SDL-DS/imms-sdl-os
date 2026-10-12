"""
csv_logger.py
=============
Provides thread-safe structured CSV record output for dosing metrics.
"""

import os
import csv
import time
import logging

CSV_FILE_NAME = "dosing_output_records.csv"

CSV_HEADERS = [
    "Timestamp",
    "Target Vial",
    "Dispensed Matter",
    "Target Value",
    "Target Unit",
    "Validated Mass",
    "Mass Unit",
    "Cycle Duration (s)",
    "Execution Status",
    "Error Diagnostic",
]


def log_to_csv(
    vial: str,
    substance: str,
    target_val: float,
    target_unit: str,
    actual_val: float,
    actual_unit: str,
    duration: float,
    status: str,
    error_msg: str = "",
    filename: str = CSV_FILE_NAME,
) -> None:
    """
    Appends execution metrics to a structured CSV file.
    
    Creates headers on initial file generation if the file does not exist.
    """
    file_exists = os.path.isfile(filename)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    row_data = [
        timestamp,
        vial,
        substance,
        target_val,
        target_unit,
        actual_val if actual_val is not None else "N/A",
        actual_unit if actual_unit is not None else "N/A",
        duration if duration is not None else "N/A",
        status,
        error_msg if error_msg else "None",
    ]

    try:
        with open(filename, mode="a", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            if not file_exists:
                writer.writerow(CSV_HEADERS)
            writer.writerow(row_data)
        logging.info("CSV Logging: Records successfully committed to '%s'.", filename)
    except Exception as err:
        logging.error("Failed to write record to CSV file '%s': %s", filename, err)