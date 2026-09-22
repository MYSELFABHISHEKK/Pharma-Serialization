import argparse
from pathlib import Path

from app.services.sgtin_service import SGTINService


def validate_gtin(gtin: str) -> str:
    return SGTINService.validate_gtin(gtin)


def generate_sgtin_rows(gtin: str, quantity: int, start_sequence: int = 1) -> list[dict[str, str | int]]:
    return SGTINService.generate_rows(gtin, quantity, start_sequence)


def write_csv(rows: list[dict[str, str | int]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(SGTINService.to_csv(rows), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SGTIN CSV from GTIN and quantity.")
    parser.add_argument("--gtin", required=True, help="14-digit GTIN.")
    parser.add_argument("--qty", type=int, required=True, help="Number of SGTIN records to generate.")
    parser.add_argument("--start-sequence", type=int, default=1, help="First sequence number. Default: 1.")
    parser.add_argument("--output", default="output/sgtin_codes.csv", help="CSV output path.")
    args = parser.parse_args()

    rows = generate_sgtin_rows(args.gtin, args.qty, args.start_sequence)
    output_path = Path(args.output)
    write_csv(rows, output_path)
    print(f"Generated {len(rows)} SGTIN records: {output_path}")


if __name__ == "__main__":
    main()
