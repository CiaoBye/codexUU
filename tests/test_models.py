from app.data.models import TokenBreakdown, estimate_model_api_value, format_tokens, prices_for_model


def test_format_tokens_promotes_at_unit_boundary():
    assert format_tokens(999_950) == "1.0M"
    assert format_tokens(999_950_000) == "1.0B"
    assert format_tokens(-1_200) == "-1.2K"


def test_model_specific_official_price_is_used():
    tokens = TokenBreakdown(uncached_input=1_000_000, cached_input=1_000_000, output=1_000_000)
    assert estimate_model_api_value(tokens, "gpt-5.6-sol") == 35.5
    assert estimate_model_api_value(tokens, "gpt-5.6-luna") == 7.1


def test_official_third_party_prices_require_exact_model_ids():
    assert prices_for_model("deepseek-v4-flash") == {
        "uncached_input": 0.14,
        "cached_input": 0.0028,
        "output": 0.28,
    }
    assert prices_for_model("mimo-v2.5-pro") == {
        "uncached_input": 0.435,
        "cached_input": 0.0036,
        "output": 0.87,
    }
    assert prices_for_model("deepseek-v4-flash-private") is None
    assert estimate_model_api_value(TokenBreakdown(uncached_input=1_000_000), "internal-review") is None
