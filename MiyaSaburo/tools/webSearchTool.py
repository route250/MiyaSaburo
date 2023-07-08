
import os
import sys
import re
import requests
import lxml.html
import urllib.parse

from langchain.tools.base import BaseTool
from typing import Optional, Type

from langchain.callbacks.manager import (
    AsyncCallbackManagerForToolRun,
    CallbackManagerForToolRun,
)


class WebSearchModule:

    IGNORE_LINK_EQ = (
         "https://www.asahi.com/news/", "https://news.yahoo.co.jp/",
         "https://www3.nhk.or.jp/news/", 
         "https://news.goo.ne.jp/", 
         "https://www.nikkei.com/","https://mainichi.jp/",
         "https://news.google.co.jp/","https://www.asahi.com/","https://newsdig.tbs.co.jp/",
         "https://www.biglobe.ne.jp/a-top/today24/",
         "https://www.benricho.org/G_Gadgets/whatday_today/index.php",
         "https://www.ne.jp/asahi/fki/st/link/today.html",
         'https://weather.goo.ne.jp/',
    )
    IGNORE_LINK_STARTS = (
        "https://www.nhk.or.jp/","https://www1.nhk.or.jp/","https://www2.nhk.or.jp/","https://www3.nhk.or.jp/",
        "https://news.tv-asahi.co.jp/",
        "https://tenki.jp/", "https://www.toshin.com/weather/",
        "https://www.jma.go.jp/bosai/forecast/","https://www.jma.go.jp/bosai/map.html",
        "https://www.jma-net.go.jp/",
        "https://s.n-kishou.co.jp/w/charge/","https://weather.yahoo.co.jp/",
    )
    num_results: int = 4

    def __init__(self):
        pass
   
    def urlEncode(self,aText:str) -> str:
        try:
            zEncoded = urllib.parse.quote(aText, encoding='UTF-8')
            return zEncoded
        except:
            pass
        return aText

    def getText(self,e) -> str:
        txt:str = ""
        try:
            for v in e.itertext():
                txt += v
        except:
            pass
        return txt

    def getTextX(self,elem, word) -> str:
        txt:str = ""
        try:
            for v in elem.itertext():
                if v.startswith(word):
                    v=v[len(word):]
                if v.endswith(word):
                    v=v[:-len(word)]
                txt += v
        except:
            pass
        return txt

    def search_snippet(self, query: str) -> str:
        """Run query through GoogleSearch and parse result."""
        snippets = []
        results = self.search_meta(query, num=self.num_results)
        if len(results) == 0:
            return "No good Google Search Result was found"
        for result in results:
            if "snippet" in result:
                snippets.append(result["snippet"])

        return " ".join(snippets)

    mBaseURL = "https://www.google.com/search"
    UA_WIN10 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.121 Safari/537.36";

    def get_weather(self):

        mUserAgent = WebSearchModule.UA_WIN10
        mTimeout = 3000
        aQuery='Weather'
        zEncQuery = self.urlEncode(aQuery)
        zURL = WebSearchModule.mBaseURL + "?q=" + zEncQuery + "&ie=UTF-8&hl=en"

        try:
            # requestsを使用してWebページを取得
            response = requests.get(zURL, timeout=mTimeout, headers={"User-Agent": mUserAgent})
            with open("weather.html","wb") as f:
                f.write(response.content)
            zDocument = lxml.html.fromstring(response.content)
            zWeathernewsList = zDocument.xpath(".//div[div/div/span/span='Weather' and .//a[contains(@href,'weathernews') and contains(span,'weathernews')]]")
            pattern = r"^[A-Z][a-z]+ [0-9]+:[0-9]+\n"
            for zWeathernews in zWeathernewsList:
                print(self.getText(zWeathernews))
                content:str = "Location"
                for txt in zWeathernews.itertext():
                    txt = txt.strip()
                    if txt == 'weathernews':
                        continue
                    txt = re.sub(pattern, "", txt )
                    content += " "+txt
                print(f"[WEATHER]{content}")
                return content
        except Exception as ex:
            print(ex)
            pass
        return ""

    def search_meta(self,aQuery, num=10):

        metadata_result = []

        mUserAgent = WebSearchModule.UA_WIN10
        mTimeout = 3000

        zEncQuery = self.urlEncode(aQuery)
        #zURL = mBaseURL + "?q=" + zEncQuery + "&ie=UTF-8&gl=us&hl=en"
        zURL = WebSearchModule.mBaseURL + "?q=" + zEncQuery + "&ie=UTF-8&hl=en"

        try:
            # requestsを使用してWebページを取得
            response = requests.get(zURL, timeout=mTimeout, headers={"User-Agent": mUserAgent})
            with open("search.html","wb") as f:
                f.write(response.content)
            zDocument = lxml.html.fromstring(response.content)
            zYahooNewsList = zDocument.xpath(".//a[@href and contains(.,'Yahoo!ニュース')]")
            for zYahooNews in zYahooNewsList:
                LINKPRE = "/url?esrc=s&q=&rct=j&sa=U&url=https://"
                zLink = zYahooNews.get("href")
                if not zLink.startswith(LINKPRE):
                    continue
                zLink = "https://" + zLink[len(LINKPRE):]
                content = self.getTextX(zYahooNews,'Yahoo!ニュース')
                zResult = {}
                zResult["link"] = zLink
                zResult["title"] = "Yahoo!ニュース"
                zResult["snippet"] = content
                metadata_result.append(zResult)
            # 特定の要素を選択して情報を取得する
            zSegments = zDocument.xpath(".//div[div/div/a//h3]")
            for zYahooNews in zSegments:
                zAtags = zYahooNews.xpath(".//a[@href]")
                if len(zAtags) == 0:
                    continue
                zLink = zAtags[0].get("href")
                LINKPRE = "/url?esrc=s&q=&rct=j&sa=U&url=https://"
                if not zLink.startswith(LINKPRE):
                    continue
                zLink = "https://" + zLink[len(LINKPRE):]
                amp = zLink.find("&")
                if amp >= 0:
                    zLink = zLink[:amp]

                if zLink in WebSearchModule.IGNORE_LINK_EQ:
                    continue
                if any(zLink.startswith(a) for a in WebSearchModule.IGNORE_LINK_STARTS):
                    continue
                zResult = {}
                zResult["link"] = zLink

                zDivTags = zYahooNews.xpath("div/div")
                for zDiv in zDivTags:
                    zH3 = zDiv.xpath(".//h3")
                    if len(zH3) > 0:
                        for e in zH3:
                            zResult["title"] = self.getText(e)
                        continue
                    zResult["snippet"] = self.getText(zDiv)
                metadata_result.append(zResult)
                if len(metadata_result) >= self.num_results:
                    break

        except requests.exceptions.RequestException as e:
            print(e)

        return metadata_result

class WebSearchTool(BaseTool):
    name = "WebSearchTool"
    description = (
        "A search engine of Web."
        "Useful for when you need to answer questions about current events from internet content."
        "Input should be a search query."
    )
    module : WebSearchModule = WebSearchModule()

    def get_weather(self) -> str:
        return self.module.get_weather()

    def _run(
        self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Use the tool."""
        return self.module.search_snippet(query)

    async def _arun(
        self, query: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None
    ) -> str:
        """Use the tool asynchronously."""
        raise NotImplementedError("custom_search does not support async")
    
class WebSearchToolJ(BaseTool):
    name = "WebSearchToolJ"
    description = (
        "A search engine of Web."
        "Useful for when you need to answer questions about current events from internet content."
        "Input should be a search query. Output is a JSON array of the query results"
    )
    module : WebSearchModule = WebSearchModule()

    def get_weather(self) -> str:
        return self.module.get_weather()

    def _run(
        self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Use the tool."""
        return self.module.search_meta(query)

    async def _arun(
        self, query: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None
    ) -> str:
        """Use the tool asynchronously."""
        raise NotImplementedError("custom_search does not support async")
    
    
def main(argv):
    mod = WebSearchModule()
    #mod.get_weather()
    ret = mod.search_meta('京田辺 天気')
    for r in ret:
        print( r )
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))

