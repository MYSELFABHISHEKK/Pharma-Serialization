import pytest
from app.services.serial_generator import SerialGenerator
from app.models.product import SerializationProfile

def test_generate_single_unambiguous_characters():
    profile = SerializationProfile(length=20, allow_duplicate_characters=True)
    
    # Excluded look-alikes
    excluded = {'0', '1', 'I', 'L', 'O', 'U'}
    
    for _ in range(100):
        serial = SerialGenerator.generate_single(profile)
        assert len(serial) == 20
        # No characters from the exclusion list should be in the serial
        intersection = set(serial).intersection(excluded)
        assert len(intersection) == 0

def test_generate_single_alphanumeric_requirement():
    profile = SerializationProfile(length=12, allow_duplicate_characters=True)
    
    for _ in range(50):
        serial = SerialGenerator.generate_single(profile)
        has_alpha = any(c.isalpha() for c in serial)
        has_numeric = any(c.isdigit() for c in serial)
        assert has_alpha is True
        assert has_numeric is True

def test_generate_single_no_duplicates_rule():
    profile = SerializationProfile(length=15, allow_duplicate_characters=False)
    
    for _ in range(50):
        serial = SerialGenerator.generate_single(profile)
        assert len(serial) == 15
        # Set size should equal string length if no duplicates allowed
        assert len(set(serial)) == 15

def test_generate_single_default_uses_unique_characters():
    profile = SerializationProfile(length=20)

    for _ in range(50):
        serial = SerialGenerator.generate_single(profile)
        assert len(serial) == 20
        assert len(set(serial)) == 20

def test_generate_single_keeps_unique_characters_even_if_legacy_flag_allows_duplicates():
    profile = SerializationProfile(length=20, allow_duplicate_characters=True)

    for _ in range(50):
        serial = SerialGenerator.generate_single(profile)
        assert len(serial) == 20
        assert len(set(serial)) == 20

def test_generate_batch_counts_and_uniqueness():
    profile = SerializationProfile(length=20, allow_duplicate_characters=True)
    existing_set = {"EXISTINGS1", "EXISTINGS2"}
    
    quantity = 100
    batch = SerialGenerator.generate_batch(quantity, profile, existing_set)
    
    assert len(batch) == 100
    # No values in batch should collide with existing_set
    assert len(set(batch).intersection(existing_set)) == 0
    # Check that all generated values are unique within the batch
    assert len(set(batch)) == 100

def test_generate_single_rejects_missing_required_character_type():
    profile = SerializationProfile(
        length=12,
        alphabet="ABCDEFGHJKMNPQRSTVWXYZ",
        require_alpha=True,
        require_numeric=True,
        allow_duplicate_characters=True,
    )

    with pytest.raises(ValueError, match="at least one digit"):
        SerialGenerator.generate_single(profile)

def test_generate_single_rejects_lookalike_characters():
    profile = SerializationProfile(
        length=12,
        alphabet="0123456789ABCDEFGHIJK",
        require_alpha=True,
        require_numeric=True,
        allow_duplicate_characters=False,
    )

    with pytest.raises(ValueError, match="look-alike characters"):
        SerialGenerator.generate_single(profile)

def test_generate_single_rejects_impossible_unique_length():
    profile = SerializationProfile(
        length=12,
        alphabet="ABC",
        require_alpha=True,
        require_numeric=False,
        allow_duplicate_characters=False,
    )

    with pytest.raises(ValueError, match="greater than unique character set size"):
        SerialGenerator.generate_single(profile)

def test_generate_batch_rejects_zero_quantity():
    profile = SerializationProfile(length=12)

    with pytest.raises(ValueError, match="greater than zero"):
        SerialGenerator.generate_batch(0, profile, set())
