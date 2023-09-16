import json
import os
from datetime import datetime, timedelta
from urllib.parse import urlparse
import openai
from openai.embeddings_utils import cosine_similarity

class CustomJsonEncorder(json.JSONEncoder):

    def default(self, obj):
        # embeddingの部分を特別に処理
        key='embedding'
        if key in obj:
            embedding_str = json.dumps(obj[key], separators=(',', ':'))
            obj = dict(obj)  # 元のオブジェクトを変更しないようにコピー
            obj[key] = embedding_str
        return super().default(self, obj)

class TweetHist:

    def __init__(self, jsonpath: str):
        self.hist = {'site': {}, 'article': []}
        self.jsonpath = jsonpath
       # self.load()

    def load(self):
        """ self.jsonpathがあれば、self.histに読み込む。なければ読まない"""
        if os.path.exists(self.jsonpath):
            with open(self.jsonpath, 'r', encoding='utf-8') as f:
                self.hist = json.load(f)

    def save(self):
        """ self.histをself.jsonpathに書き込む """
        directory = os.path.dirname(self.jsonpath)
        if directory is not None and len(directory)>0 and not os.path.exists(directory):
            os.makedirs(directory)
        
        with open(self.jsonpath, 'w', encoding='utf-8') as f:
            json.dump(self.hist, f, indent=4, ensure_ascii=False, cls=CustomJsonEncorder)

    def is_used(self, url: str, days: int) -> str:
        """ days日以内に、urlのサイトの記事を使ったか？ """
        hostname = urlparse(url).netloc
        if hostname in self.hist['site']:
            dt = self.hist['site'][hostname]['time']
            last_time = datetime.strptime( dt, '%Y/%m/%d %H:%M:%S' )
            if datetime.now() - last_time <= timedelta(days=days):
                return dt
        return None

    def get_embedding(self, content: str, limit: float = 0.8) -> list[float]:
        """ contentと似た記事がなければ記録してFalseを返す。似た記事があればTrueを返す"""
        embedding = to_embedding( content )
        if leng(embedding) != 1:
            return None
        embedding=embedding[0]
        if leng(embedding)<10:
            return None

        # Check similarity with existing embeddings. This is also a dummy check.
        for article in self.hist['article']:
            embB = article.get('embedding',None)
            if embB is not None:
                sim = cosine_similarity( embedding, embB )
                if sim>=limit:
                    return None
        return embedding

    def put_site(self, url: str, content: str, embedding: list[float], type: str ) -> None:
        """ urlのホスト名、日時、回数を記録する """
        hostname = urlparse(url).netloc
        current_time = datetime.now().strftime('%Y/%m/%d %H:%M:%S')
        if hostname in self.hist['site']:
            self.hist['site'][hostname]['count'] += 1
            self.hist['site'][hostname]['time'] = current_time  # timeを更新
        else:
            self.hist['site'][hostname] = {'time': current_time, 'count': 1}
        # 記事のembeddingを記録する
        self.hist['article'].append({
            'time': current_time,
            'url': url,
            'type': type,
            'embedding': embedding
        })
        self.save()

def leng( value ) -> int:
    try:
        if value is not None:
            return len(value)
    except:
        return 0

def to_embedding( input ):
    res = openai.Embedding.create(input=input, model="text-embedding-ada-002")
    return [data.get('embedding',None) for data in res.get('data',[])]

if __name__ == "__main__":
    print("main")
    hist = TweetHist( 'dmmy.json')
    hist.put_site( 'https://sample.com', 'text_text_text', [1,2,3,4], 'debug')
