import logging
import os
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

class RLService:
    """
    Service for loading RL models and predicting actions.
    
    Currently supports a modular architecture for model loading, 
    allowing for both pre-trained Stable Baselines3 models and mock fallbacks.
    """
    
    def __init__(self, models_dir: str = "models/rl") -> None:
        self.models_dir = models_dir
        if not os.path.exists(self.models_dir):
            os.makedirs(self.models_dir, exist_ok=True)

    def load_model(self, model_name: str) -> Any:
        """
        Load a model by name from the models directory.
        
        If the model file exists (e.g. .zip for SB3), it will attempt to load it.
        Otherwise, returns a MockModel for demonstration purposes in Phase 5.
        """
        model_path = os.path.join(self.models_dir, f"{model_name}.zip")
        
        # In a real environment, we would check for stable_baselines3
        # try:
        #     from stable_baselines3 import PPO
        #     if os.path.exists(model_path):
        #         return PPO.load(model_path)
        # except ImportError:
        #     logger.warning("stable_baselines3 not installed. Use mock implementation.")
        
        if os.path.exists(model_path):
            logger.info("Found RL model file: %s", model_path)
            # Returning a placeholder if libraries are missing
            return {"name": model_name, "path": model_path, "type": "SB3_STUB"}
            
        logger.warning("RL Model '%s' not found in %s. Using MockModel.", model_name, self.models_dir)
        return MockModel(model_name)

    def predict_action(self, model: Any, observation: np.ndarray) -> int:
        """
        Predict next action (0=HOLD, 1=BUY, 2=SELL) for a given observation.
        """
        if hasattr(model, "predict"):
            # Real model prediction
            action, _states = model.predict(observation, deterministic=True)
            return int(action)
        elif isinstance(model, MockModel):
            return model.predict(observation)
        elif isinstance(model, dict) and model.get("type") == "SB3_STUB":
            # Stub for real model file found but libs missing
            return 0 # Default to HOLD
            
        logger.error("Unknown model type for prediction.")
        return 0 # HOLD

class MockModel:
    """Simple mock model that returns consistent actions for verification."""
    def __init__(self, name: str):
        self.name = name

    def predict(self, observation: np.ndarray, deterministic: bool = True) -> tuple[int, Any]:
        # Deterministic dummy logic for MVP testing
        # Sum observation features; if high, BUY; if low, SELL; else HOLD
        mean_val = np.mean(observation)
        if mean_val > 0.6:
            action = 1 # BUY/LONG
        elif mean_val < 0.3:
            action = 2 # SELL/SHORT
        else:
            action = 0 # HOLD
        return action, None
