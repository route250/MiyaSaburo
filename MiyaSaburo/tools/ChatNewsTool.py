
import sys
import time
import random
import openai
import openai.embeddings_utils
from tools.webSearchTool import WebSearchModule

class NewsData:
    def __init__(self,dict_data):
        self.title = dict_data.get("title",None)
        self.link = dict_data.get("link",None)
        self.snippet = dict_data.get("snippet",None)
        self.snippet_vect = None
        self.content = None
        self.summally = None
        self._used : dict = dict()
    def used(self) -> int:
        if self._used:
            return len(self._used)
        else:
            return 0

    def is_used(self,userid) -> bool:
        if self._used:
            return userid in self._used
        else:
            return False

    def use(self, userid:str ) -> bool:
        if self._used:
            if userid in self._used:
                return False
        else:
            self._used = {}
        self._used[userid]="o"
        return True

class NewsRepo:
    def __init__(self,query,qdr=None):
        self._last_timer = 0
        self._list : list[NewsData] = list()
        self._module = WebSearchModule()
        self.query = query
        self.qdr = qdr

    def size(self) -> int:
        return len(self._list)

    def search(self):
        ret = self._module.search_meta(self.query,qdr=self.qdr)
        ret = [r for r in ret if 'snippet' in r and isinstance(r['snippet'], str) and len(r['snippet']) >= 1]
        snippet_list = [r['snippet'] for r in ret]
        vect_list = openai.embeddings_utils.get_embeddings(snippet_list)
        for i,r in enumerate(ret):
            n = NewsData(r)
            n.snippet_vect = vect_list[i]
            if self.add(n):
                print("[ADD]"+n.snippet)
            else:
                print("[skip]"+n.snippet)

    def add(self, news: NewsData ) -> bool:
        for n in self._list:
            sim = openai.embeddings_utils.cosine_similarity(news.snippet_vect,n.snippet_vect)
            if sim>0.9:
                return False
        self._list.append(news)
        return True

    def random_get(self,userid:str):
        i=len(self._list)
        while i>0:
            i-=1
            rnd = random.choice(self._list)
            if rnd.use(userid):
                return rnd
        return None

    def call_timer(self):
        now = int(time.time()*1000)
        if (now-self._last_timer)<60*60*1000:
            return
        self._last_timer = now
        self.search()

def main(argv):
    userid = 'a0001'

    news_repo = NewsRepo('ニュース AND 猫 OR キャット OR にゃんこ',qdr="h48")

    news_repo.search()
    news_repo.search()

    for i in range(0,news_repo.size()):
        nd = news_repo.random_get(userid)
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))