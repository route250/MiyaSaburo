import json
import os
from datetime import datetime, timedelta
from urllib.parse import urlparse

class TweetHist:

    def __init__(self, jsonpath: str):
        self.hist = {'site': {}, 'article': []}
        self.jsonpath = jsonpath
        self.load()

    def load(self):
        """ self.jsonpathがあれば、self.histに読み込む。なければ読まない"""
        if os.path.exists(self.jsonpath):
            with open(self.jsonpath, 'r') as f:
                self.hist = json.load(f)

    def save(self):
        """ self.histをself.jsonpathに書き込む """
        with open(self.jsonpath, 'w') as f:
            json.dump(self.hist, f)

    def is_site(self, url: str, days: int) -> bool:
        """ days日以内に、urlのサイトの記事を使ったか？ """
        hostname = urlparse(url).netloc
        if hostname in self.hist['site']:
            last_time = datetime.strptime(self.hist['site'][hostname]['time'], '%Y/%m/%d %H:%M:%S')
            if datetime.now() - last_time <= timedelta(days=days):
                return True
        return False

    def put_site(self, url: str) -> None:
        """ urlのホスト名、日時、回数を記録する """
        hostname = urlparse(url).netloc
        current_time = datetime.now().strftime('%Y/%m/%d %H:%M:%S')
        if hostname in self.hist['site']:
            self.hist['site'][hostname]['count'] += 1
            self.hist['site'][hostname]['time'] = current_time  # timeを更新
        else:
            self.hist['site'][hostname] = {'time': current_time, 'count': 1}
        self.save()

    def put_article(self, content: str, limit: float = 0.8) -> bool:
        """ contentと似た記事がなければ記録してFalseを返す。似た記事があればTrueを返す"""
        # TODO: Convert content to embedding. For simplicity, this step is not implemented.
        embedding = content  # This is a dummy. Convert this to a real embedding

        # Check similarity with existing embeddings. This is also a dummy check.
        for article in self.hist['article']:
            # TODO: Replace this with a real similarity check
            if embedding == article['embedding']:
                return True

        # If no similar article found, record the new article
        self.hist['article'].append({
            'time': datetime.now().strftime('%Y/%m/%d %H:%M:%S'),
            'embedding': embedding
        })
        self.save()
        return False
