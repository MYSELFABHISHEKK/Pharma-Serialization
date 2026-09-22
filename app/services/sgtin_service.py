import csv
import io
import re
from typing import List, Dict

from app.models.product import SerializationProfile
from app.services.serial_generator import SerialGenerator


class SGTINService:
    @staticmethod
    def validate_gtin(gtin: str) -> str:
        cleaned = gtin.strip()
        if not re.fullmatch(r"\d{14}", cleaned):
            raise ValueError("GTIN must be exactly 14 numeric digits.")
        return cleaned

    @staticmethod
    def generate_rows(
        gtin: str,
        quantity: int,
        start_sequence: int = 1,
        length: int = 20,
        alphabet: str = "23456789ABCDEFGHJKMNPQRSTVWXYZ",
        require_alpha: bool = True,
        require_numeric: bool = True
    ) -> List[Dict[str, str | int]]:
        if quantity < 1:
            raise ValueError("Quantity must be greater than zero.")
        if start_sequence < 1:
            raise ValueError("Start sequence must be greater than zero.")

        validated_gtin = SGTINService.validate_gtin(gtin)
        allow_duplicates = (length > len(set(alphabet)))
        profile = SerializationProfile(
            length=length,
            alphabet=alphabet,
            require_alpha=require_alpha,
            require_numeric=require_numeric,
            allow_duplicate_characters=allow_duplicates,
        )
        serial_numbers = SerialGenerator.generate_batch(quantity, profile, existing_set=set())

        return SGTINService.build_rows(validated_gtin, serial_numbers, start_sequence)

    @staticmethod
    def generate_rows_excluding_serials(
        gtin: str,
        quantity: int,
        existing_serials: set[str],
        start_sequence: int = 1,
        length: int = 20,
        alphabet: str = "23456789ABCDEFGHJKMNPQRSTVWXYZ",
        require_alpha: bool = True,
        require_numeric: bool = True
    ) -> List[Dict[str, str | int]]:
        if quantity < 1:
            raise ValueError("Quantity must be greater than zero.")
        if start_sequence < 1:
            raise ValueError("Start sequence must be greater than zero.")

        validated_gtin = SGTINService.validate_gtin(gtin)
        allow_duplicates = (length > len(set(alphabet)))
        profile = SerializationProfile(
            length=length,
            alphabet=alphabet,
            require_alpha=require_alpha,
            require_numeric=require_numeric,
            allow_duplicate_characters=allow_duplicates,
        )
        serial_numbers = SerialGenerator.generate_batch(quantity, profile, existing_set=existing_serials)

        return SGTINService.build_rows(validated_gtin, serial_numbers, start_sequence)

    @staticmethod
    def build_rows(gtin: str, serial_numbers: List[str], start_sequence: int) -> List[Dict[str, str | int]]:
        return [
            {
                "Sequence": start_sequence + index,
                "GTIN": gtin,
                "Serial Number": serial_number,
                "SGTIN": f"{gtin}{serial_number}",
            }
            for index, serial_number in enumerate(serial_numbers)
        ]

    @staticmethod
    def to_csv(rows: List[Dict[str, str | int]]) -> str:
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["Sequence", "GTIN", "Serial Number", "SGTIN"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()
