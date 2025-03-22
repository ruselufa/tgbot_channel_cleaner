from transformers import pipeline
from typing import Tuple, Dict, Any
import logging
from config.settings import (
    BERT_MODEL_PATH,
    TOXIC_MODEL_PATH,
    EMOTION_MODEL_PATH,
    NEGATIVE_THRESHOLD
)

class TextAnalyzer:
    def __init__(self):
        try:
            # Временно заменяем использование реальных моделей на заглушки для тестирования
            logging.info("Using mock analyzers for testing")
            self.sentiment_analyzer = MockSentimentAnalyzer()
            self.toxic_analyzer = MockToxicAnalyzer()
            self.emotion_analyzer = MockEmotionAnalyzer()
            logging.info("Successfully initialized mock text analyzers")
        except Exception as e:
            logging.error(f"Failed to initialize text analyzers: {e}")

    async def is_negative(self, text: str) -> Tuple[bool, float, Dict[str, Any]]:
        """Анализ текста на негативность"""
        try:
            # Анализ тональности
            sentiment = self.sentiment_analyzer(text)[0]
            sentiment_score = sentiment['score'] if sentiment['label'] == 'POSITIVE' else -sentiment['score']
            
            # Анализ токсичности
            toxic = self.toxic_analyzer(text)[0]
            toxic_score = toxic['score'] if toxic['label'] == 'toxic' else 0
            
            # Анализ эмоций
            emotion = self.emotion_analyzer(text)[0]
            
            analysis = {
                'sentiment': sentiment,
                'toxic': toxic,
                'emotion': emotion
            }
            
            # Определяем негативность по комбинации факторов
            is_negative = (
                sentiment_score < NEGATIVE_THRESHOLD or
                toxic_score > 0.7 or
                emotion['label'] in ['anger', 'disgust']
            )
            
            return is_negative, sentiment_score, analysis
            
        except Exception as e:
            logging.error(f"Error analyzing text: {e}")
            return False, 0.0, {}

    def get_toxicity_reason(self, analysis: Dict[str, Any]) -> str:
        """Получение причины токсичности"""
        try:
            reasons = []
            
            if analysis.get('sentiment', {}).get('label') == 'NEGATIVE':
                reasons.append("негативная тональность")
                
            if analysis.get('toxic', {}).get('label') == 'toxic':
                reasons.append("токсичное содержание")
                
            emotion = analysis.get('emotion', {}).get('label')
            if emotion in ['anger', 'disgust']:
                reasons.append(f"выраженная эмоция: {emotion}")
                
            return ", ".join(reasons) if reasons else "неприемлемое содержание"
            
        except Exception as e:
            logging.error(f"Error getting toxicity reason: {e}")
            return "неприемлемое содержание"

class MockSentimentAnalyzer:
    def __call__(self, text):
        return [{'label': 'POSITIVE', 'score': 0.9}]
        
class MockToxicAnalyzer:
    def __call__(self, text):
        return [{'label': 'non-toxic', 'score': 0.9}]
        
class MockEmotionAnalyzer:
    def __call__(self, text):
        return [{'label': 'neutral', 'score': 0.9}] 