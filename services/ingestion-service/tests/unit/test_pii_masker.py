from common.sanitization.pii_masker import mask_pii


def test_mask_pii_redacts_sensitive_values() -> None:
    raw = "user@example.com failed from 10.0.0.5 with api_key=secret123 Bearer abc.def.ghi"
    masked = mask_pii(raw)

    assert "user@example.com" not in masked
    assert "10.0.0.5" not in masked
    assert "secret123" not in masked
    assert "[STRIPPED_EMAIL]" in masked
    assert "[STRIPPED_IP]" in masked
