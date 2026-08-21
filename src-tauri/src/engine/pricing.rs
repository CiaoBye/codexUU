use crate::models::TokenBreakdown;

#[derive(Debug, Clone, Copy)]
pub struct ModelPrice {
    pub input_per_m: f64,
    pub cached_input_per_m: f64,
    pub output_per_m: f64,
}

pub struct PricingEngine;

impl PricingEngine {
    /// Look up the official price for `model_id`.
    ///
    /// `model_id` must already be trimmed and lowercased by the caller.
    /// `calculate_cost` handles that normalization once and passes the result
    /// here, avoiding a redundant second allocation on the hot path.
    pub fn get_model_price(model_id: &str) -> Option<ModelPrice> {
        match model_id {
            // OpenAI GPT-5.6, official USD / 1M text tokens.
            "gpt-5.6" | "gpt-5.6-sol" => Some(ModelPrice {
                input_per_m: 5.0,
                cached_input_per_m: 0.5,
                output_per_m: 30.0,
            }),
            "gpt-5.6-terra" => Some(ModelPrice {
                input_per_m: 2.0,
                cached_input_per_m: 0.2,
                output_per_m: 12.0,
            }),
            "gpt-5.6-luna" => Some(ModelPrice {
                input_per_m: 0.2,
                cached_input_per_m: 0.02,
                output_per_m: 1.2,
            }),
            // OpenAI legacy identifiers retained for historical local logs.
            "gpt-4o-mini" | "gpt-4o-mini-2024-07-18" => Some(ModelPrice {
                input_per_m: 0.15,
                cached_input_per_m: 0.075,
                output_per_m: 0.60,
            }),
            "gpt-4o" | "gpt-4o-2024-05-13" | "gpt-4o-2024-08-06" | "gpt-4o-2024-11-20" => {
                Some(ModelPrice {
                    input_per_m: 2.50,
                    cached_input_per_m: 1.25,
                    output_per_m: 10.00,
                })
            }
            "gpt-4.5-preview" => Some(ModelPrice {
                input_per_m: 75.0,
                cached_input_per_m: 37.5,
                output_per_m: 150.0,
            }),
            "o1-mini" | "o1-mini-2024-09-12" => Some(ModelPrice {
                input_per_m: 1.10,
                cached_input_per_m: 0.55,
                output_per_m: 4.40,
            }),
            "o1" | "o1-2024-12-17" => Some(ModelPrice {
                input_per_m: 15.0,
                cached_input_per_m: 7.5,
                output_per_m: 60.0,
            }),
            "o3-mini" | "o3-mini-2025-01-31" => Some(ModelPrice {
                input_per_m: 1.10,
                cached_input_per_m: 0.55,
                output_per_m: 4.40,
            }),
            "gpt-4-turbo"
            | "gpt-4-turbo-2024-04-09"
            | "gpt-4-0125-preview"
            | "gpt-4-1106-preview" => Some(ModelPrice {
                input_per_m: 10.0,
                cached_input_per_m: 5.0,
                output_per_m: 30.0,
            }),
            "gpt-3.5-turbo" | "gpt-3.5-turbo-0125" => Some(ModelPrice {
                input_per_m: 0.50,
                cached_input_per_m: 0.25,
                output_per_m: 1.50,
            }),
            // Anthropic and Google identifiers observed in local exports.
            "claude-3-5-sonnet-20240620" | "claude-3-5-sonnet-20241022" => Some(ModelPrice {
                input_per_m: 3.0,
                cached_input_per_m: 0.30,
                output_per_m: 15.0,
            }),
            "claude-3-5-haiku-20241022" => Some(ModelPrice {
                input_per_m: 0.80,
                cached_input_per_m: 0.08,
                output_per_m: 4.0,
            }),
            "claude-3-opus-20240229" => Some(ModelPrice {
                input_per_m: 15.0,
                cached_input_per_m: 1.50,
                output_per_m: 75.0,
            }),
            "gemini-2.5-pro" => Some(ModelPrice {
                input_per_m: 1.25,
                cached_input_per_m: 0.125,
                output_per_m: 10.0,
            }),
            "gemini-2.5-flash" => Some(ModelPrice {
                input_per_m: 0.30,
                cached_input_per_m: 0.03,
                output_per_m: 2.50,
            }),
            // Historical official model IDs retained for existing local logs.
            "gemini-1.5-pro" => Some(ModelPrice {
                input_per_m: 1.25,
                cached_input_per_m: 0.3125,
                output_per_m: 5.0,
            }),
            "gemini-1.5-flash" => Some(ModelPrice {
                input_per_m: 0.075,
                cached_input_per_m: 0.01875,
                output_per_m: 0.30,
            }),
            // DeepSeek's official API model IDs. Gateway aliases such as
            // `deepseek-r1`/`deepseek-v3` deliberately remain unpriced.
            "deepseek-reasoner" => Some(ModelPrice {
                input_per_m: 0.55,
                cached_input_per_m: 0.14,
                output_per_m: 2.19,
            }),
            "deepseek-chat" => Some(ModelPrice {
                input_per_m: 0.14,
                cached_input_per_m: 0.014,
                output_per_m: 0.28,
            }),
            _ => None,
        }
    }

    pub fn calculate_cost(model_id: &str, tokens: &TokenBreakdown) -> (f64, String) {
        // Normalize once so the hot path avoids a second allocation in
        // get_model_price.
        let id = model_id.trim().to_ascii_lowercase();
        let input_tokens = tokens.uncached_input.saturating_add(tokens.cached_input);
        let mut price = if id == "gemini-2.5-pro" && input_tokens > 200_000 {
            // Gemini 2.5 Pro Standard API prices the full request at the long
            // context tier when the prompt exceeds 200k input tokens.
            Some(ModelPrice {
                input_per_m: 2.50,
                cached_input_per_m: 0.25,
                output_per_m: 15.0,
            })
        } else {
            Self::get_model_price(&id)
        };

        if matches!(
            id.as_str(),
            "gpt-5.6" | "gpt-5.6-sol" | "gpt-5.6-terra" | "gpt-5.6-luna"
        ) && input_tokens > 272_000
        {
            // GPT-5.6 prices the full request at 2x input (including cached
            // input) and 1.5x output once the prompt exceeds 272k tokens.
            if let Some(model_price) = price.as_mut() {
                model_price.input_per_m *= 2.0;
                model_price.cached_input_per_m *= 2.0;
                model_price.output_per_m *= 1.5;
            }
        }

        if let Some(price) = price {
            let uncached_cost = (tokens.uncached_input as f64 / 1_000_000.0) * price.input_per_m;
            let cached_cost = (tokens.cached_input as f64 / 1_000_000.0) * price.cached_input_per_m;
            let output_cost = (tokens.output as f64 / 1_000_000.0) * price.output_per_m;
            let total = uncached_cost + cached_cost + output_cost;
            (total, "exact".to_string())
        } else {
            (0.0, "unpriced".to_string())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_exact_pricing_calculations() {
        let tokens = TokenBreakdown::new(1_000_000, 2_000_000, 500_000);
        let (cost, status) = PricingEngine::calculate_cost("gpt-4o", &tokens);
        assert_eq!(status, "exact");
        // 1M * 2.50 + 2M * 1.25 + 0.5M * 10.0 = 2.5 + 2.5 + 5.0 = 10.0
        assert!((cost - 10.0).abs() < 1e-6);

        let (cost_mini, status_mini) = PricingEngine::calculate_cost("o3-mini", &tokens);
        assert_eq!(status_mini, "exact");
        // 1M * 1.10 + 2M * 0.55 + 0.5M * 4.40 = 1.1 + 1.1 + 2.2 = 4.4
        assert!((cost_mini - 4.4).abs() < 1e-6);

        let (_, status_unknown) = PricingEngine::calculate_cost("custom-private-model", &tokens);
        assert_eq!(status_unknown, "unpriced");

        assert!(PricingEngine::get_model_price("gpt-4o-private-gateway").is_none());
        let (sol_cost, sol_status) = PricingEngine::calculate_cost("gpt-5.6-sol", &tokens);
        assert_eq!(sol_status, "exact");
        assert!((sol_cost - 34.5).abs() < 1e-6);
    }

    #[test]
    fn current_terra_luna_and_gemini_standard_prices_are_exact() {
        let short_context = TokenBreakdown::new(100_000, 100_000, 1_000_000);

        let (terra, terra_status) = PricingEngine::calculate_cost("gpt-5.6-terra", &short_context);
        assert_eq!(terra_status, "exact");
        assert!((terra - 12.22).abs() < 1e-6);

        let (luna, luna_status) = PricingEngine::calculate_cost("gpt-5.6-luna", &short_context);
        assert_eq!(luna_status, "exact");
        assert!((luna - 1.222).abs() < 1e-6);

        let one_m_each = TokenBreakdown::new(1_000_000, 1_000_000, 1_000_000);
        let (flash, flash_status) = PricingEngine::calculate_cost("gemini-2.5-flash", &one_m_each);
        assert_eq!(flash_status, "exact");
        assert!((flash - 2.83).abs() < 1e-6);
    }

    #[test]
    fn gpt_5_6_uses_single_request_long_context_tier() {
        let at_threshold = TokenBreakdown::new(136_000, 136_000, 1_000_000);
        let (short_cost, short_status) =
            PricingEngine::calculate_cost("gpt-5.6-sol", &at_threshold);
        assert_eq!(short_status, "exact");
        assert!((short_cost - 30.748).abs() < 1e-6);

        let above_threshold = TokenBreakdown::new(136_001, 136_000, 1_000_000);
        let (long_cost, long_status) =
            PricingEngine::calculate_cost("gpt-5.6-sol", &above_threshold);
        assert_eq!(long_status, "exact");
        assert!((long_cost - 46.49601).abs() < 1e-6);
    }

    #[test]
    fn gemini_2_5_pro_uses_single_request_input_tier() {
        let at_threshold = TokenBreakdown::new(100_000, 100_000, 1_000_000);
        let (short_cost, short_status) =
            PricingEngine::calculate_cost("gemini-2.5-pro", &at_threshold);
        assert_eq!(short_status, "exact");
        assert!((short_cost - 10.1375).abs() < 1e-6);

        let above_threshold = TokenBreakdown::new(100_001, 100_000, 1_000_000);
        let (long_cost, long_status) =
            PricingEngine::calculate_cost("gemini-2.5-pro", &above_threshold);
        assert_eq!(long_status, "exact");
        assert!((long_cost - 15.2750025).abs() < 1e-6);
    }

    #[test]
    fn gateway_aliases_are_not_reported_as_exact() {
        let tokens = TokenBreakdown::new(1_000_000, 0, 0);
        for alias in ["deepseek-r1", "deepseek-v3", "gemini-3.7-flash"] {
            let (cost, status) = PricingEngine::calculate_cost(alias, &tokens);
            assert_eq!(cost, 0.0, "{alias}");
            assert_eq!(status, "unpriced", "{alias}");
        }

        for official_id in [
            "deepseek-reasoner",
            "deepseek-chat",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
        ] {
            let (_, status) = PricingEngine::calculate_cost(official_id, &tokens);
            assert_eq!(status, "exact", "{official_id}");
        }
    }
}
