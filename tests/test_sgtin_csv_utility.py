import csv

import pytest

from scripts.generate_sgtin_csv import generate_sgtin_rows, validate_gtin, write_csv


def test_generate_sgtin_rows_from_gtin_and_quantity():
    rows = generate_sgtin_rows("08901234567890", 5)

    assert len(rows) == 5
    assert [row["Sequence"] for row in rows] == [1, 2, 3, 4, 5]

    sgtins = set()
    for row in rows:
        serial_number = row["Serial Number"]
        assert row["GTIN"] == "08901234567890"
        assert len(serial_number) == 20
        assert len(set(serial_number)) == 20
        assert not set(serial_number).intersection({"0", "1", "I", "L", "O", "U"})
        assert any(char.isalpha() for char in serial_number)
        assert any(char.isdigit() for char in serial_number)
        assert row["SGTIN"] == f"{row['GTIN']}{serial_number}"
        sgtins.add(row["SGTIN"])

    assert len(sgtins) == 5


def test_generate_sgtin_rows_supports_custom_start_sequence():
    rows = generate_sgtin_rows("08901234567890", 3, start_sequence=501)

    assert [row["Sequence"] for row in rows] == [501, 502, 503]


def test_validate_gtin_rejects_invalid_values():
    with pytest.raises(ValueError, match="14 numeric digits"):
        validate_gtin("8901234567890")

    with pytest.raises(ValueError, match="14 numeric digits"):
        validate_gtin("0890123456789A")


def test_write_csv_outputs_expected_columns(tmp_path):
    rows = generate_sgtin_rows("08901234567890", 2)
    output_path = tmp_path / "sgtin.csv"

    write_csv(rows, output_path)

    with output_path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        csv_rows = list(reader)

    assert reader.fieldnames == ["Sequence", "GTIN", "Serial Number", "SGTIN"]
    assert len(csv_rows) == 2
