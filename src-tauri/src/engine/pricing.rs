use crate::models::TokenBreakdown;

#[derive(Debug, Clone, Copy)]
pub struct ModelPrice {
    pub input_per_m: f64,
    pub cached_input_per_m: f64,
    pub output_per_m: f64,
}

pub struct PricingEngine;

impl PricingEngine {
    pub fn get_model_price(model_id: &str) -> Option<ModelPrice> {
        let id = model_id.trim().to_ascii_lowercase();

        // Exact catalog only: gateway aliases and private model names stay
        // unpriced until an explicit price is added for that exact identifier.
        match id.as_str() {
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
            "gemini-2.5-pro" | "gemini-1.5-pro" => Some(ModelPrice {
                input_per_m: 1.25,
                cached_input_per_m: 0.3125,
                output_per_m: 5.0,
            }),
            "gemini-2.5-flash" | "gemini-3.7-flash" | "gemini-1.5-flash" => Some(ModelPrice {
                input_per_m: 0.075,
                cached_input_per_m: 0.01875,
                output_per_m: 0.30,
            }),
            // DeepSeek identifiers observed in gateway logs.
            "deepseek-reasoner" | "deepseek-r1" => Some(ModelPrice {
                input_per_m: 0.55,
                cached_input_per_m: 0.14,
                output_per_m: 2.19,
            }),
            "deepseek-chat" | "deepseek-v3" => Some(ModelPrice {
                input_per_m: 0.14,
                cached_input_per_m: 0.014,
                output_per_m: 0.28,
            }),
            _ => None,
        }
    }

    pub fn calculate_cost(model_id: &str, tokens: &TokenBreakdown) -> (f64, String) {
        if let Some(price) = Self::get_model_price(model_id) {
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
        assert!((sol_cost - 21.0).abs() < 1e-6);
    }
}
