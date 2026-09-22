# BT SN Portal Logic Setup

Use these steps to test the backend serialization logic before UI/menu work.

## 1. Create and activate a virtual environment

```powershell
cd "C:\Users\KIIT\OneDrive\Desktop\Serial Tracking"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If `py -3.11` is not available, install Python 3.11 first, then rerun the commands.

## 2. Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 3. Run tests

```powershell
$env:PYTHONPATH="."
python -m pytest
```

To test only serial generation:

```powershell
$env:PYTHONPATH="."
python -m pytest tests\test_serial_generator.py
```

## 4. Run standalone SGTIN CSV utility

This does not need MongoDB. It takes only GTIN and quantity, then creates a CSV.

```powershell
$env:PYTHONPATH="."
python scripts\generate_sgtin_csv.py --gtin 08901234567890 --qty 5 --output output\sgtin_codes.csv
```

Expected result:

- Exactly 5 records.
- CSV columns: `Sequence`, `GTIN`, `Serial Number`, `SGTIN`.
- Every row has the same input GTIN.
- Every row has one 20-character `Serial Number`.
- `SGTIN` is generated as `GTIN + Serial Number`.
- Each `SGTIN` is unique for that GTIN.
- Sequence numbers are continuous: `1, 2, 3, 4, 5`.
- Serial numbers use no look-alike characters: `0`, `1`, `I`, `L`, `O`, `U`.
- Every serial number contains both letters and numbers.
- Characters inside each serial number are unique.

You can still run the JSON demo if needed:

```powershell
$env:PYTHONPATH="."
python scripts\demo_serial_generation.py --quantity 5 --start-sequence 1 --length 20
```

## 5. Start the API

```powershell
$env:PYTHONPATH="."
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Open:

```text
http://127.0.0.1:8001
```

In the portal, use **SGTIN CSV Generation**:

```text
GTIN: 08901234567890
Quantity: 5
Start sequence: 1
```

Click **Generate CSV**. The browser downloads a CSV with:

```text
Sequence, GTIN, Serial Number, SGTIN
```

Portal-generated SGTIN rows are stored so future portal generations can keep serial numbers unique for the same GTIN.

## 6. Sample data for generation

Product:

```text
Product identifier: ATOR-20
Product name: Atorvastatin Calcium 20mg Tablets
GTIN: 08901072000534
Serial length: 20
Character repeats: Allowed
```

Batch:

```text
Product: ATOR-20
Batch/Lot number: LOT2026-A
Expiry date: 31/12/2029
Quantity: 5
Idempotency key: use auto-generated value
```

## Serial generation rules implemented

- Uses cryptographically secure randomness with `secrets`.
- Uses an unambiguous alphabet that excludes confusing characters like `0`, `1`, `I`, `L`, `O`, and `U`.
- Uses 20-character alphanumeric serial numbers for SGTIN CSV generation.
- Enforces unique characters inside each serial number.
- Enforces alpha and numeric character requirements.
- Rejects impossible profiles before generation starts.
- Prevents duplicates inside the generated batch.
- Checks database collisions before storing serials.
- Reserves a product-specific sequence range for each generated batch.
- Pairs each serial number with one sequence number from the reserved sequence range.
- Generates CSV output from only GTIN and quantity.
