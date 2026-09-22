# Business Requirement Document & Technical Specification: Product Serialization Tracking System

This document outlines the business requirements, prerequisites, technical architecture, and database design for a highly reliable, concurrent, and collision-free product serialization tracking system.

---

## 1. Document Overview
The purpose of this system is to generate and track unique, unambiguous, alphanumeric serial numbers for products. Each serial number is paired with a sequential, incrementing sequence number to guarantee absolute uniqueness and logical ordering.

---

## 2. Business & Functional Requirements

### 2.1 Alphanumeric Serialization Rules
To prevent human error (misreading or miskeying serial numbers printed on physical products), the generated serial numbers must adhere to the following rules:
*   **Unambiguous Character Set**: Exclude all "look-alike" characters.
    *   Exclude digit `0` and uppercase letter `O`.
    *   Exclude digit `1`, uppercase letter `I`, and letter `L` (both uppercase `L` and lowercase `l` are avoided by enforcing uppercase-only).
    *   Exclude digit `2` and uppercase letter `Z`.
    *   Exclude digit `5` and uppercase letter `S`.
    *   Exclude digit `8` and uppercase letter `B`.
*   **Resulting Safe Alphabet (25 characters)**:
    *   **Digits**: `3, 4, 6, 7, 9`
    *   **Letters**: `A, C, D, E, F, G, H, J, K, M, N, P, Q, R, T, U, V, W, X, Y`
*   **Case Sensitivity**: All serial numbers must be generated, stored, and verified in **uppercase** only.
*   **Length**: 20 characters (providing $25^{20} \approx 9.09 \times 10^{27}$ possible combinations, making random collisions statistically impossible).

### 2.2 Precise Quantity Generation
*   When a user/system requests exactly $N$ serial numbers, the system must generate and return **exactly** $N$ serial numbers.
*   No more, no less.
*   The system must support transaction-like behavior to ensure that if any part of the batch fails, the entire batch is rolled back (no partial allocations).

### 2.3 Parallel Sequence Numbering
*   Every single serial number must have a corresponding, globally unique sequence number (e.g., `1`, `2`, `3`, ..., `M`).
*   This sequence number acts as a sequential, chronological index.
*   For example:
    *   Serial number `H3K9AC...` $\rightarrow$ Sequence Number `1001`
    *   Serial number `W4Y7NX...` $\rightarrow$ Sequence Number `1002`
*   This ensures traceability and order of generation, regardless of the randomness of the serial string itself.

---

## 3. Database Design Patterns in MongoDB Atlas

MongoDB does not have a built-in `AUTO_INCREMENT` feature like traditional SQL databases. To handle sequential sequence numbers reliably, especially under high concurrency, we employ the **Counters Collection Pattern**.

### 3.1 Schema Definition

#### Collection 1: `counters`
This collection tracks the current highest sequence number used in the system.
```json
{
  "_id": "serial_sequence",
  "seq_value": 0
}
```

#### Collection 2: `serial_batches`
Tracks metadata for each bulk generation request.
```json
{
  "_id": ObjectId("65c8f..."),
  "batch_id": "uuid-v4-string",
  "requested_qty": 5000,
  "status": "COMPLETED", // PENDING, PROCESSING, COMPLETED, FAILED
  "file_url": "https://s3.amazonaws.com/.../batch-uuid.csv",
  "created_by": "system_user",
  "created_at": ISODate("2026-08-14T13:00:00Z")
}
```

#### Collection 3: `serials`
Stores individual generated serial numbers and their mapping.
```json
{
  "_id": ObjectId("65c8f..."),
  "serial_no": "A4TG79KMNDEPQRTVWXY3",
  "seq_no": 1283,
  "batch_id": "uuid-v4-string",
  "created_at": ISODate("2026-08-14T13:00:00Z")
}
```

### 3.2 Database Indexes (Critical for Performance & Uniqueness)
To guarantee data integrity at the database layer, we create the following unique indexes:
```javascript
// Enforce unique serial numbers
db.serials.createIndex({ "serial_no": 1 }, { unique: true });

// Enforce unique sequence numbers
db.serials.createIndex({ "seq_no": 1 }, { unique: true });

// Enforce compound index for querying serials by batch efficiently
db.serials.createIndex({ "batch_id": 1, "seq_no": 1 });
```

### 3.3 Atomic Sequence Range Allocation (Python Implementation)
To avoid lock contention and ensure high performance during parallel bulk generation, the system reserves a block of $N$ sequence numbers in a single atomic database call using `find_one_and_update`.

```python
from pymongo import ReturnDocument

def reserve_sequence_range(db, quantity: int) -> int:
    """
    Atomically increments the global counter by 'quantity'
    and returns the starting sequence number of the reserved range.
    """
    counter = db.counters.find_one_and_update(
        {"_id": "serial_sequence"},
        {"$inc": {"seq_value": quantity}},
        projection={"seq_value": True},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    
    end_sequence = counter["seq_value"]
    start_sequence = end_sequence - quantity + 1
    return start_sequence
```
*   **Why this is safe**: `find_one_and_update` is atomic at the document level. Even if 100 API instances request serials concurrently, MongoDB serializes the modifications to the counter document, guaranteeing that no two instances receive overlapping sequence ranges.

---

## 4. Technical Architecture Stack

The system is designed as a cloud-native, microservices-ready API leveraging AWS services and Python.

### 4.1 Cloud Infrastructure Components (AWS)
*   **Networking (VPC)**:
    *   Isolated VPC with 2 Public Subnets (hosting ALB and NAT Gateways) and 2 Private Subnets (hosting Fargate APIs and Workers).
*   **Compute (ECS Fargate)**:
    *   No EC2 instances to manage. Container scaling is handled automatically.
    *   **API Task**: Serves API endpoints (FastAPI).
    *   **Worker Task**: Consumes SQS jobs to process large batch generations.
*   **Load Balancing (ALB)**:
    *   Distributes traffic across ECS API containers. Handles SSL termination (ACM).
*   **Queueing (SQS)**:
    *   Decouples API response times from database insertion.
    *   If a request is received for 100,000 serials, the API validates the request, pushes an execution message to SQS, and returns `202 Accepted`. This prevents HTTP timeouts.
*   **Storage (S3)**:
    *   Stores generated serial numbers as downloadable CSV/JSON files.
    *   FastAPI generates a presigned URL (valid for e.g. 15 minutes) for clients to securely download the batch file directly from S3.
*   **Secrets Manager**:
    *   Secures MongoDB connection strings, API tokens, and AWS access keys.
*   **Monitoring (CloudWatch)**:
    *   Unified dashboard tracking API latency, SQS queue depth, error rates, and container stdout logs.

---

## 5. Prerequisites & Project Setup

### 5.1 Local Development Prerequisites
Before starting, ensure the following are installed:
1.  **Python 3.12+**
2.  **Docker Desktop** (for containerized local database/testing)
3.  **AWS CLI** (configured with access to your AWS sandbox account)
4.  **MongoDB Compass** (optional, for visual DB verification)

### 5.2 Project Directory Structure
```text
serial-tracking-system/
│
├── .github/
│   └── workflows/
│       └── ci-cd.yml          # GitHub Actions pipeline
│
├── app/
│   ├── __init__.py
│   ├── main.py                # FastAPI entry point
│   ├── config.py              # Settings & Secret Manager loader
│   ├── database.py            # MongoDB connection & index initialization
│   │
│   ├── models/
│   │   ├── batch.py           # Pydantic schemas for batch requests
│   │   └── serial.py          # Pydantic schemas for serial responses
│   │
│   ├── services/
│   │   ├── generator.py       # Serial generation algorithm
│   │   ├── queue_service.py   # SQS client wrapper
│   │   └── s3_service.py      # S3 file upload & presigned URL generator
│   │
│   └── worker.py              # SQS Consumer (Background processing task)
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py            # Pytest fixtures & mock DB setups
│   ├── test_generator.py      # Tests for look-alike characters and uniqueness
│   └── test_api.py            # API endpoint integration tests
│
├── Dockerfile                 # Multi-stage production build
├── docker-compose.yml         # Local stack (FastAPI + Mongo + LocalStack)
├── requirements.txt           # Python dependencies
└── README.md                  # Development guide
```

---

## 6. Implementation Specifications (Code Snippets)

### 6.1 Generation Algorithm (`app/services/generator.py`)
```python
import secrets
from typing import List, Set

# Excluded: 0, O, 1, I, L, 2, Z, 5, S, 8, B
UNAMBIGUOUS_ALPHABET = "34679ACDEFGHJKMNPQRTUVWXY"

def generate_unambiguous_serial(length: int = 20) -> str:
    """Generates a secure, random serial using only unambiguous characters."""
    return "".join(secrets.choice(UNAMBIGUOUS_ALPHABET) for _ in range(length))

def generate_serial_batch(quantity: int, existing_serials: Set[str], length: int = 20) -> List[str]:
    """
    Generates a set of unique serials of size 'quantity'.
    Checks against in-memory batch and existing DB serials to guarantee no duplicates.
    """
    new_serials: Set[str] = set()
    
    while len(new_serials) < quantity:
        candidate = generate_unambiguous_serial(length)
        # Avoid local duplicates or database-wide duplicates
        if candidate not in new_serials and candidate not in existing_serials:
            new_serials.add(candidate)
            
    return list(new_serials)
```

---

## 7. Verification Plan & Testing

### 7.1 Automated Tests (`pytest`)
We will verify functional correctness using `pytest` and `mongomock` (or a dockerized MongoDB instance).

*   **Test Case 1: Unambiguous Character Verification**
    *   Verify that no serial contains `0, O, 1, I, L, 2, Z, 5, S, 8, B`.
*   **Test Case 2: Exact Count Verification**
    *   Assert that requesting 500 serials returns exactly 500 serials.
*   **Test Case 3: Parallel Sequences**
    *   Assert that every serial is mapped to a contiguous, ascending block of integers.
*   **Test Case 4: Scale & Collision Performance**
    *   Assert that generating a large batch does not cause overlaps or duplicates.

### 7.2 Manual Verification
1.  **Swagger UI API Testing**: Access `/docs` of FastAPI, send requests with different volumes of serialization.
2.  **Concurrency Testing**: Use a tool like `locust` or `wrk` to simulate concurrent calls to `/generate` and check for duplicate errors in MongoDB logs.
