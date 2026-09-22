import argparse
import json
from app.models.product import SerializationProfile
from app.services.serial_generator import SerialGenerator


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate BT SN serial and sequence pairs.")
    parser.add_argument("--quantity", type=int, default=10, help="Number of serials to generate.")
    parser.add_argument("--start-sequence", type=int, default=1, help="First sequence number.")
    parser.add_argument("--length", type=int, default=20, help="Serial number length.")
    args = parser.parse_args()

    profile = SerializationProfile(
        length=args.length,
        require_alpha=True,
        require_numeric=True,
        allow_duplicate_characters=False,
    )
    serials = SerialGenerator.generate_batch(args.quantity, profile, existing_set=set())
    output = [
        {
            "sequence_number": args.start_sequence + index,
            "serial_number": serial,
        }
        for index, serial in enumerate(serials)
    ]
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
