import argparse
import redis
import json
from google.cloud import language_v1
from Preprocessor import Preprocessor
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import time
from ratelimit import limits, sleep_and_retry

CALLS = 450 # max 450 requests
TIME_PERIOD = 60 # per min (to the Google API)

class Analyzer():
    def __init__(self, redis_client, max_threads: int = 10):
        self.redis_client = redis_client
        self.preprocessor = Preprocessor(redis_client, local=True)
        self.client = language_v1.LanguageServiceClient()

        self.threadpool = ThreadPoolExecutor(max_threads)

    def analyze(self, inputs: list) -> list:
        futures = []
        for input in inputs:
            futures.append(self.threadpool.submit(self._analyze, (input)))
        
        coin_sentiments = []
        for future in futures:
            coin_sentiments.extend(future.result())

        return coin_sentiments

    @sleep_and_retry
    @limits(calls=CALLS, period=TIME_PERIOD)
    def _analyze(self, input: str) -> list:
        """Run a sentiment analysis request on text within a passed filename."""
        document = language_v1.Document(content=input[0], type_=language_v1.Document.Type.PLAIN_TEXT)
        try:
            response = self.client.analyze_entity_sentiment(request={'document': document})
        except: # some shitty exception like this dude that posted in german and not english
            return []

        created = input[1]
        # YES RAGHAV I YOINKED YOUR CODE GET HECKED ON
        coinResults = []
        for entity in response.entities:
            if entity.sentiment.score != 0:
                coin = self.preprocessor.get_crypto(entity.name)
                if coin:
                    coin_sentiment = CoinSentiment(coin, entity.sentiment.score, created, input[0])
                    coinResults.append(coin_sentiment)

        return coinResults

class CoinSentiment:
    def __init__(self, coin, sentiment, created, text):
        self.coin = coin
        self.sentiment = sentiment
        self.created = created
        self.text = text
