from app.data.models import TokenBreakdown, estimate_model_api_value, format_tokens, prices_for_model


def test_format_tokens_promotes_at_unit_boundary():
    assert format_tokens(999_950) == "1.0M"
    assert format_tokens(999_950_000) == "1.0B"
    assert format_tokens(-1_200) == "-1.2K"


def test_model_specific_official_price_is_used():
    tokens = TokenBreakdown(uncached_input=1_000_000, cached_input=1_000_000, output=1_000_000)
    assert estimate_model_api_value(tokens, "gpt-5.6-sol") == 35.5
    assert estimate_model_api_value(tokens, "gpt-5.6-luna") == 7.1


def test_unknown_model_is_not_assigned_an_openai_price():
    assert prices_for_model("deepseek-v4-flash") is None
    assert estimate_model_api_value(TokenBreakdown(uncached_input=1_000_000), "internal-review") is None
