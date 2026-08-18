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
        let id = model_id.to_lowercase();

        // Exact OpenAI Models
        if id.starts_with("gpt-4o-mini") {
            Some(ModelPrice {
                input_per_m: 0.15,
                cached_input_per_m: 0.075,
                output_per_m: 0.60,
            })
        } else if id.starts_with("gpt-4o") {
            Some(ModelPrice {
                input_per_m: 2.50,
                cached_input_per_m: 1.25,
                output_per_m: 10.00,
            })
        } else if id.starts_with("gpt-4.5") {
            Some(ModelPrice {
                input_per_m: 75.00,
                cached_input_per_m: 37.50,
                output_per_m: 150.00,
            })
        } else if id.starts_with("o1-mini") {
            Some(ModelPrice {
                input_per_m: 1.10,
                cached_input_per_m: 0.55,
                output_per_m: 4.40,
            })
        } else if id.starts_with("o1") {
            Some(ModelPrice {
                input_per_m: 15.00,
                cached_input_per_m: 7.50,
                output_per_m: 60.00,
            })
        } else if id.starts_with("o3-mini") {
            Some(ModelPrice {
                input_per_m: 1.10,
                cached_input_per_m: 0.55,
                output_per_m: 4.40,
            })
        } else if id.starts_with("gpt-4-turbo")
            || id.starts_with("gpt-4-0125")
            || id.starts_with("gpt-4-1106")
        {
            Some(ModelPrice {
                input_per_m: 10.00,
                cached_input_per_m: 5.00,
                output_per_m: 30.00,
            })
        } else if id.starts_with("gpt-3.5-turbo") {
            Some(ModelPrice {
                input_per_m: 0.50,
                cached_input_per_m: 0.25,
                output_per_m: 1.50,
            })
        // Anthropic Models
        } else if id.contains("claude-3-5-sonnet") {
            Some(ModelPrice {
                input_per_m: 3.00,
                cached_input_per_m: 0.30,
                output_per_m: 15.00,
            })
        } else if id.contains("claude-3-5-haiku") {
            Some(ModelPrice {
                input_per_m: 0.80,
                cached_input_per_m: 0.08,
                output_per_m: 4.00,
            })
        } else if id.contains("claude-3-opus") {
            Some(ModelPrice {
                input_per_m: 15.00,
                cached_input_per_m: 1.50,
                output_per_m: 75.00,
            })
        // Google Gemini Models
        } else if id.contains("gemini-2.5-pro") || id.contains("gemini-1.5-pro") {
            Some(ModelPrice {
                input_per_m: 1.25,
                cached_input_per_m: 0.3125,
                output_per_m: 5.00,
            })
        } else if id.contains("gemini-2.5-flash")
            || id.contains("gemini-3.7-flash")
            || id.contains("gemini-1.5-flash")
        {
            Some(ModelPrice {
                input_per_m: 0.075,
                cached_input_per_m: 0.01875,
                output_per_m: 0.30,
            })
        // DeepSeek Models
        } else if id.contains("deepseek-reasoner") || id.contains("deepseek-r1") {
            Some(ModelPrice {
                input_per_m: 0.55,
                cached_input_per_m: 0.14,
                output_per_m: 2.19,
            })
        } else if id.contains("deepseek-chat") || id.contains("deepseek-v3") {
            Some(ModelPrice {
                input_per_m: 0.14,
                cached_input_per_m: 0.014,
                output_per_m: 0.28,
            })
        } else {
            None
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
    }
}
