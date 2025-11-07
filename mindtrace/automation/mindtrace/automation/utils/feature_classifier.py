from typing import Any, Callable, Dict

from .feature_models import Feature, FeatureConfig


class FeatureClassifier:
    """Apply classification rules to features based on configuration.

    Supports pluggable rule types that can be registered and applied
    to features without modifying core logic.

    Example config with classification rules:
        {
            "feature_1": {
                "bbox": [100, 100, 200, 200],
                "expected_count": 1,
                "label": "defect",
                "params": {"class_id": 0},
                "classification_rules": [
                    {
                        "type": "length_threshold",
                        "min_length_px": 50,
                        "fail_label": "TooShort"
                    }
                ]
            }
        }
    """

    def __init__(self):
        """Initialize the classifier with built-in rule types."""
        self._rule_handlers: Dict[str, Callable] = {
            "length_threshold": self._apply_length_threshold,
        }

    def register_rule_type(self, rule_type: str, handler: Callable) -> None:
        """Register a custom rule type handler.

        Args:
            rule_type: Name of the rule type
            handler: Function that takes (feature, rule_config) and returns classification or None

        Example:
            def custom_rule(feature, rule):
                if some_condition:
                    return "CustomLabel"
                return None

            classifier.register_rule_type("custom_rule", custom_rule)
        """
        self._rule_handlers[rule_type] = handler

    def classify(self, feature: Feature, config: FeatureConfig) -> None:
        """Apply classification rules to a feature.

        Modifies the feature's classification property in-place based on
        the rules defined in the config. Only applies rules if feature is present.

        Args:
            feature: The feature to classify
            config: Configuration containing classification rules
        """
        if not feature.is_present:
            return

        for rule in config.classification_rules:
            rule_type = rule.get("type")
            if not rule_type:
                continue

            handler = self._rule_handlers.get(rule_type)
            if not handler:
                continue

            classification = handler(feature, rule)
            if classification:
                feature.classification = classification
                # Stop at first matching rule
                break

    def _apply_length_threshold(self, feature: Feature, rule: Dict[str, Any]) -> str | None:
        """Classify based on maximum dimension (length) of the bbox.

        Rule config:
            - min_length_px: Minimum length in pixels
            - fail_label: Label to apply if below threshold (default: "Short")

        Example:
            {"type": "length_threshold", "min_length_px": 50, "fail_label": "TooShort"}
        """
        if not isinstance(feature.bbox, list) or len(feature.bbox) != 4:
            return None

        x1, y1, x2, y2 = feature.bbox
        length = max(x2 - x1, y2 - y1)

        min_length = rule.get("min_length_px")
        if min_length is not None and length < min_length:
            return rule.get("fail_label", "Short")

        return None
