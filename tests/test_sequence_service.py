import pytest
from app.services.sequence_service import SequenceService

def test_sequence_reservation_initial(db_session):
    product_id = "ATOR-20"
    qty = 50
    
    start, end = SequenceService.reserve_range(db_session, product_id, qty)
    
    assert start == 1
    assert end == 50
    assert (end - start + 1) == qty

def test_sequence_reservation_subsequent(db_session):
    product_id = "REMD-100"
    
    # First reservation
    start1, end1 = SequenceService.reserve_range(db_session, product_id, 100)
    assert start1 == 1
    assert end1 == 100
    
    # Second reservation on the same scope
    start2, end2 = SequenceService.reserve_range(db_session, product_id, 250)
    assert start2 == 101
    assert end2 == 350
    assert (end2 - start2 + 1) == 250

def test_multiple_products_isolated_sequences(db_session):
    prod_a = "PROD-A"
    prod_b = "PROD-B"
    
    # Reserving for Prod A
    start_a, end_a = SequenceService.reserve_range(db_session, prod_a, 10)
    # Reserving for Prod B (should start at 1, completely isolated)
    start_b, end_b = SequenceService.reserve_range(db_session, prod_b, 10)
    
    assert start_a == 1
    assert end_a == 10
    
    assert start_b == 1
    assert end_b == 10
