from pipeline.ml_predictor import predictor

machine_id = "HPR001"

state = {
    "buffers": {
        "main_pressure": [150.0] * 30,
        "horizontal_press_pressure": [120.0] * 30,
        "oil_tank_temperature": [65.0] * 30
    },
    "ewma_mean": {
        "main_pressure": 150.0,
        "horizontal_press_pressure": 120.0,
        "oil_tank_temperature": 65.0
    },
    "ewma_var": {
        "main_pressure": 0.0,
        "horizontal_press_pressure": 0.0,
        "oil_tank_temperature": 0.0
    },
    "sample_count": {
        "main_pressure": 30,
        "horizontal_press_pressure": 30,
        "oil_tank_temperature": 30
    }
}

result = predictor.predict_risk(machine_id, state)
print("Score:", result.score)
print("Confidence:", result.confidence)
print("Top Features:", result.top_features)
print("-" * 50)
print("Explanation:\n", result.explanation)
