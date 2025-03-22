from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
from typing import Tuple, Dict, Any
import logging
from config.settings import (
    BERT_MODEL_PATH,
    TOXIC_MODEL_PATH,
    EMOTION_MODEL_PATH,
    NEGATIVE_THRESHOLD
)
from tqdm import tqdm
import torch
from huggingface_hub import model_info
import traceback

class TextAnalyzer:
    MODELS = {
        'sentiment': 'cointegrated/rubert-tiny2-sentiment',
        'toxic': 'cointegrated/rubert-tiny2-toxic',
        'emotion': 'cointegrated/rubert-tiny2-emotion'
    }

    def __init__(self):
        try:
            logging.info("Initializing text analyzers...")
            print("Загрузка моделей из HuggingFace...")
            
            # Устройство для вычислений
            device = 0 if torch.cuda.is_available() else -1
            print(f"Используется устройство: {'GPU' if device == 0 else 'CPU'}")
            
            try:
                print("\n1/3 Загрузка модели анализа тональности...")
                self.sentiment_analyzer = pipeline(
                    "sentiment-analysis",
                    model="blanchefort/rubert-base-cased-sentiment",
                    device=device
                )
                print("✓ Модель тональности загружена")
            except Exception as e:
                print(f"✗ Ошибка загрузки модели тональности: {str(e)}")
                traceback.print_exc()
                raise
            
            try:
                print("\n2/3 Загрузка модели определения токсичности...")
                self.toxic_analyzer = pipeline(
                    "text-classification",
                    model="SkolkovoInstitute/russian_toxicity_classifier",
                    device=device
                )
                print("✓ Модель токсичности загружена")
            except Exception as e:
                print(f"✗ Ошибка загрузки модели токсичности: {str(e)}")
                traceback.print_exc()
                raise
            
            try:
                print("\n3/3 Загрузка модели определения эмоций...")
                self.emotion_analyzer = pipeline(
                    "text-classification",
                    model="Aniemore/rubert-tiny2-russian-emotion-detection",
                    device=device
                )
                print("✓ Модель эмоций загружена")
            except Exception as e:
                print(f"✗ Ошибка загрузки модели эмоций: {str(e)}")
                traceback.print_exc()
                raise
            
            print("\n✅ Все модели успешно загружены!")
            logging.info("Successfully initialized text analyzers")
            self.using_mock = False
            
        except Exception as e:
            logging.error(f"Failed to initialize text analyzers: {e}")
            logging.warning("Falling back to mock analyzers")
            print("\n❌ Ошибка загрузки моделей, использую заглушки для тестирования")
            print(f"Причина: {str(e)}")
            traceback.print_exc()
            self.sentiment_analyzer = MockSentimentAnalyzer()
            self.toxic_analyzer = MockToxicAnalyzer()
            self.emotion_analyzer = MockEmotionAnalyzer()
            self.using_mock = True

    async def is_negative(self, text: str) -> bool:
        """Анализ текста на негативность"""
        try:
            if not text:
                return False
                
            # Анализ тональности
            sentiment = self.sentiment_analyzer(text)[0]
            sentiment_score = sentiment['score'] if sentiment['label'] == 'POSITIVE' else -sentiment['score']
            
            # Анализ токсичности
            toxic = self.toxic_analyzer(text)[0]
            toxic_score = toxic['score'] if toxic['label'] == 'toxic' else 0
            
            # Анализ эмоций
            emotion = self.emotion_analyzer(text)[0]
            
            # Логируем результаты анализа
            logging.info(f"Text analysis results: sentiment={sentiment}, toxic={toxic}, emotion={emotion}")
            
            # Определяем негативность по комбинации факторов
            is_negative = (
                sentiment_score < NEGATIVE_THRESHOLD or
                toxic_score > 0.7 or
                emotion['label'] in ['anger', 'sadness', 'fear', 'disgust']
            )
            
            return is_negative
            
        except Exception as e:
            logging.error(f"Error analyzing text: {e}")
            return False

    async def get_toxicity_score(self, text: str) -> float:
        """Получение оценки токсичности текста"""
        try:
            toxic = self.toxic_analyzer(text)[0]
            return toxic['score'] if toxic['label'] == 'toxic' else 0
        except Exception as e:
            logging.error(f"Error getting toxicity score: {e}")
            return 0.0

    async def get_emotion(self, text: str) -> str:
        """Получение эмоциональной окраски текста"""
        try:
            emotion = self.emotion_analyzer(text)[0]
            return emotion['label']
        except Exception as e:
            logging.error(f"Error getting emotion: {e}")
            return 'neutral'

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

# Mock-классы для fallback при ошибках
class MockSentimentAnalyzer:
    def __call__(self, text):
        return [{'label': 'POSITIVE', 'score': 0.9}]
        
class MockToxicAnalyzer:
    def __call__(self, text):
        return [{'label': 'non-toxic', 'score': 0.9}]
        
class MockEmotionAnalyzer:
    def __call__(self, text):
        return [{'label': 'neutral', 'score': 0.9}] 