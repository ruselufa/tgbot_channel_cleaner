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
        'sentiment': 'blanchefort/rubert-base-cased-sentiment',
        'toxic': 'SkolkovoInstitute/russian_toxicity_classifier',
        'emotion': 'Aniemore/rubert-tiny2-russian-emotion-detection'
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
                self.sentiment_analyzer = pipeline("sentiment-analysis", model=self.MODELS['sentiment'])
                print("✓ Модель тональности загружена")
            except Exception as e:
                print(f"✗ Ошибка загрузки модели тональности: {str(e)}")
                traceback.print_exc()
                raise
            
            try:
                print("\n2/3 Загрузка модели определения токсичности...")
                self.toxicity_analyzer = pipeline("text-classification", model=self.MODELS['toxic'])
                print("✓ Модель токсичности загружена")
            except Exception as e:
                print(f"✗ Ошибка загрузки модели токсичности: {str(e)}")
                traceback.print_exc()
                raise
            
            try:
                print("\n3/3 Загрузка модели определения эмоций...")
                self.emotion_analyzer = pipeline("text-classification", model=self.MODELS['emotion'])
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
            self.toxicity_analyzer = MockToxicAnalyzer()
            self.emotion_analyzer = MockEmotionAnalyzer()
            self.using_mock = True

    async def is_negative(self, text: str) -> bool:
        """Анализ текста на негативность"""
        try:
            if not text:
                return False
            
            # Анализ тональности
            sentiment = self.sentiment_analyzer(text)[0]
            
            # Анализ токсичности
            toxic = self.toxicity_analyzer(text)[0]
            
            # Анализ эмоций
            emotion = self.emotion_analyzer(text)[0]
            
            # Логируем результаты анализа
            logging.info(f"Text analysis results: sentiment={sentiment}, toxic={toxic}, emotion={emotion}")
            
            # Сообщение считается негативным если:
            # 1. Оно токсичное (любая токсичная метка со score > 0.8)
            # 2. ИЛИ имеет негативную тональность (NEGATIVE) И эмоцию anger/sadness/fear/disgust с высоким score (> 0.7)
            toxic_labels = ['toxic', 'insult', 'threat', 'obscene']
            is_negative = (
                (toxic['label'] in toxic_labels and toxic['score'] > 0.8) or
                (sentiment['label'] == 'NEGATIVE' and 
                 emotion['label'] in ['anger', 'sadness', 'fear', 'disgust'] and
                 emotion['score'] > 0.7)
            )
            
            return is_negative
            
        except Exception as e:
            logging.error(f"Error analyzing text: {e}")
            return False

    async def get_toxicity_score(self, text: str) -> float:
        """Возвращает оценку токсичности текста"""
        try:
            result = self.toxicity_analyzer(text)[0]
            logging.info(f"Toxicity analysis result: {result}")
            # Возвращаем score для любых токсичных меток
            toxic_labels = ['toxic', 'insult', 'threat', 'obscene']
            return result['score'] if result['label'] in toxic_labels else 0.0
        except Exception as e:
            logging.error(f"Error in toxicity analysis: {e}")
            return 0.0

    async def get_emotion(self, text: str) -> str:
        """Определяет эмоциональную окраску текста"""
        try:
            result = self.emotion_analyzer(text)[0]
            logging.info(f"Emotion analysis result: {result}")
            return result['label']
        except Exception as e:
            logging.error(f"Error in emotion analysis: {e}")
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