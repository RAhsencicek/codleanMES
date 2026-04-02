import json
import logging
from typing import Dict, Any, Tuple

log = logging.getLogger("causal_evaluator")

class CausalEvaluator:
    def __init__(self, rules_path: str):
        self.rules = {}
        try:
            with open(rules_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.rules = data.get("rules", {})
        except Exception as e:
            log.exception(f"Causal kuralları %s okunamadı: %s", rules_path, e)

    def evaluate(self, machine_data: Dict[str, Any]) -> Tuple[str, str]:
        """
        Makine verisini kurallarla karşılaştırır. Eşleşen Kural ID ve Açıklamasını döner.
        Hiçbiri eşleşmezse ("", "") döner.
        """
        if not self.rules:
            return "", ""

        # Flatten machine data for easy condition parsing
        sensors = machine_data.get("sensors", {})
        trends = machine_data.get("trend_info", {})
        booleans = machine_data.get("booleans", {})

        for rule_id, rule_data in self.rules.items():
            condition = rule_data.get("condition", {})
            explanation = rule_data.get("explanation_tr", "")
            
            matched = True
            for field, expected in condition.items():
                actual_val = None
                
                # Değeri bul:
                if field.endswith("_slope"):
                    base_sensor = field.replace("_slope", "")
                    actual_val = trends.get(base_sensor)
                elif field.endswith("_volatility"):
                    base_sensor = field.replace("_volatility", "")
                    actual_val = None # Volatility canlı olarak henüz verilmiyor, false olacak
                else:
                    actual_val = sensors.get(field)
                
                if actual_val is None:
                    matched = False
                    break
                
                # expected string parse et (örn: "> 0.50", "< 10")
                try:
                    if expected.startswith(">="):
                        val = float(expected.replace(">=", "").strip())
                        if not (actual_val >= val): matched = False
                    elif expected.startswith("<="):
                        val = float(expected.replace("<=", "").strip())
                        if not (actual_val <= val): matched = False
                    elif expected.startswith(">"):
                        val = float(expected.replace(">", "").strip())
                        if not (actual_val > val): matched = False
                    elif expected.startswith("<"):
                        val = float(expected.replace("<", "").strip())
                        if not (actual_val < val): matched = False
                    elif expected.lower() in ("true", "false"):
                        b_val = (expected.lower() == "true")
                        if actual_val != b_val: matched = False
                except Exception:
                    matched = False
                
                if not matched:
                    break
            
            if matched:
                human_readable_name = rule_id.replace("_", " ").title()
                return human_readable_name, explanation
                
        return "", ""
