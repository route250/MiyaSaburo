
import os
import sys
import re
import traceback,logging
import requests
import lxml.html as html
from lxml.html import HtmlElement, HtmlComment, TextareaElement, HtmlEntity
import urllib.parse
from enum import Enum
from pydantic import Field, BaseModel
from langchain.tools.base import BaseTool
from typing import Optional, Type

from langchain.callbacks.manager import (
    AsyncCallbackManagerForToolRun,
    CallbackManagerForToolRun,
)

logger = logging.getLogger("webSearchTool")

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
        self.mUserAgent = WebSearchModule.UA_WIN10
        self.mTimeout = 3000

    @staticmethod
    def urlEncode(aText:str) -> str:
        try:
            zEncoded = urllib.parse.quote(aText, encoding='UTF-8')
            return zEncoded
        except:
            logger.exception("")
        return aText

    @staticmethod
    def getText(e) -> str:
        txt:str = ""
        try:
            for v in e.itertext():
                txt += v
        except:
            logger.exception("")
        return txt

    @staticmethod
    def getTextX(elem, word) -> str:
        txt:str = ""
        try:
            for v in elem.itertext():
                if v.startswith(word):
                    v=v[len(word):]
                if v.endswith(word):
                    v=v[:-len(word)]
                txt += v
        except:
            logger.exception("")
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

    def get_weather(self, *, user_agent=None, timeout=None):

        user_agent = user_agent if user_agent else self.mUserAgent
        timeout = timeout if timeout else self.mTimeout
        aQuery='Weather'
        zEncQuery = WebSearchModule.urlEncode(aQuery)
        zURL = WebSearchModule.mBaseURL + "?q=" + zEncQuery + "&ie=UTF-8&hl=en"

        try:
            # requestsを使用してWebページを取得
            response = requests.get(zURL, timeout=timeout, headers={"User-Agent": user_agent})
            os.makedirs("logs", exist_ok=True)
            with open("logs/weather.html","wb") as f:
                f.write(response.content)
            zDocument = html.fromstring(response.content)
            zWeathernewsList = zDocument.xpath(".//div[div/div/span/span='Weather' and .//a[contains(@href,'weathernews') and contains(span,'weathernews')]]")
            pattern = r"^[A-Z][a-z]+ [0-9]+:[0-9]+\n"
            for zWeathernews in zWeathernewsList:
                print(WebSearchModule.getText(zWeathernews))
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
            logger.exception("")
        return ""

    def search_meta(self,aQuery, num=10,qdr=None, *, user_agent = None, timeout = None) -> list[dict]:

        metadata_result = []

        user_agent = user_agent if user_agent else self.mUserAgent
        timeout = timeout if timeout else self.mTimeout

        zEncQuery = WebSearchModule.urlEncode(aQuery)
        #zURL = mBaseURL + "?q=" + zEncQuery + "&ie=UTF-8&gl=us&hl=en"
        zURL = WebSearchModule.mBaseURL + "?q=" + zEncQuery + "&ie=UTF-8&hl=en"
        if qdr:
            zURL += f"&tbs=qdr:{qdr}"

        try:
            # requestsを使用してWebページを取得
            response = requests.get(zURL, timeout=timeout, headers={"User-Agent": user_agent})
            os.makedirs("logs", exist_ok=True)
            with open("logs/search.html","wb") as f:
                f.write(response.content)
            zDocument = html.fromstring(response.content)
            zYahooNewsList = zDocument.xpath(".//a[@href and contains(.,'Yahoo!ニュース')]")
            for zYahooNews in zYahooNewsList:
                LINKPRE = "/url?esrc=s&q=&rct=j&sa=U&url=https://"
                zLink = zYahooNews.get("href")
                if not zLink.startswith(LINKPRE):
                    continue
                zLink = "https://" + zLink[len(LINKPRE):]
                content = WebSearchModule.getTextX(zYahooNews,'Yahoo!ニュース')
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
                            zResult["title"] = WebSearchModule.getText(e)
                        continue
                    zResult["snippet"] = WebSearchModule.getText(zDiv)
                metadata_result.append(zResult)
                if len(metadata_result) >= self.num_results:
                    break

        except requests.exceptions.RequestException as e:
            logger.exception("")

        return metadata_result
    
    RE_NORMALIZE_1 = r"[ \t\r]*\n"
    RE_NORMALIZE_2 = r"\n\n\n*"

    @staticmethod
    def normalize( value:str )->str:
        if value is None:
            return "#None"
        value = re.sub(WebSearchModule.RE_NORMALIZE_1,"\n", value)
        value = re.sub(WebSearchModule.RE_NORMALIZE_2,"\n\n", value)
        return value

    @staticmethod
    def dump_str( value:str )->str:
        if value is None:
            return "#None"
        value = value.replace("\\\\","\\")
        value = value.replace("\n","\\n").replace("\\r","\\r").replace("\t","\\t")
        return value

    XPATH_HTAG=".//h1|.//h2|.//h3|.//h4|.//h5|.//h6"
    RE_H_MATCH = re.compile('^h[1-6]$')
            
    def get_content(self, link: str, *, user_agent = None, timeout = None ) -> str:
        h_content = []
        try:
            user_agent = user_agent if user_agent else self.mUserAgent
            timeout = timeout if timeout else self.mTimeout
            # requestsを使用してWebページを取得
            response = requests.get(link, timeout=timeout, headers={"User-Agent": user_agent})
            os.makedirs("logs", exist_ok=True)
            with open("logs/content.html","wb") as f:
                f.write(response.content)
            return WebSearchModule.get_content_from_bytes( response.content, response.encoding )
        except Exception as e:
            logger.exception("")
        return ""

    @staticmethod
    def get_content_from_bytes( b: bytes, encoding: str = "utf-8") -> str:
        content = ""
        try:
            content = b.decode( encoding )
        except:
            try:
                content = b.decode( "utf-8" )
            except:
                logger.exception("")
                content = b.decode( "ISO-88591-1" )
        return WebSearchModule.get_content_from_str(content)

    @staticmethod
    def get_content_from_str( content: str) -> str:
        h_content = []
        try:
            zDocument = html.fromstring(content)
            zMain = WebSearchModule._scan_main_content( zDocument )
            # 特定の要素を選択して情報を取得する
            h_tag: HtmlElement
            for h_tag in zMain.xpath(WebSearchModule.XPATH_HTAG):
                h_text = h_tag.text_content()
                h_text = WebSearchModule.normalize(h_text)
                print("----")
                print(f"[DBG] {h_tag.tag} {WebSearchModule.dump_str(h_text)}")
                text = WebSearchModule.get_next_content(h_tag,stop=True)
                norm_text = WebSearchModule.normalize(text)
                if len(norm_text)>0:
                    h_content.append( norm_text )
        except Exception as e:
            logger.exception("")
        return WebSearchModule.normalize("\n".join(h_content))

    # -----------------------------------------------------------------
    # 配下のhタグが一番多いdivタグを探す
    # -----------------------------------------------------------------
    @staticmethod
    def _scan_main_content( elem: HtmlElement) -> HtmlElement:
        zMap: dict[HtmlElement,int] = {}
        for h_tag in elem.xpath(WebSearchModule.XPATH_HTAG):
            e: HtmlElement = h_tag
            while e is not None:
                try:
                    if e.tag == "div":
                        count: int = zMap.get(e,0)
                        zMap[e] = count + 1
                        break
                except Exception as ex:
                    logger.exception("")
                finally:
                    e = e.getparent()
        ret = elem
        max = 0
        for e, n in zMap.items():
            if n>max:
                ret = e
                max = n
        return ret

    # -----------------------------------------------------------------
    # blockタグか？
    # -----------------------------------------------------------------
    @staticmethod
    def _is_block( elem ):
        if elem is not None and isinstance(elem,HtmlElement) and elem.tag:
            tag: str = elem.tag.lower()
            if tag == "div" or tag == "p":
                return True
            if tag == "h1" or tag == "h2" or tag=="h3" and tag == "h4" or tag == "h5" or tag=="h6":
                return True
        return False

    # -----------------------------------------------------------------
    # elemとその次のエレメントをテキスト化する
    # -----------------------------------------------------------------
    @staticmethod
    def get_next_content( elem, stop=False ) -> str:
        text_list=[]
        buffer = ""
        next_tag_list = elem.xpath(".|following-sibling::*|following-sibling::text()")
        for next_tag in next_tag_list:
            if isinstance( next_tag, HtmlElement ):
                if elem != next_tag and stop and WebSearchModule.RE_H_MATCH.match( str(next_tag.tag) ):
                    break
                if isinstance( next_tag, HtmlComment ):
                    continue
                child_list = next_tag.getchildren()
                if len(child_list)>0:
                    text = WebSearchModule.get_next_content( child_list[0] )
                else:
                    text = next_tag.text_content()
                text = WebSearchModule.normalize( text )
                if "a" == next_tag.tag:
                    href = next_tag.attrib.get("href",None)
                    if href is not None and len(href)>0:
                        text = f"[{text}]({href})"
                elif "img" == next_tag.tag:
                    alt = next_tag.attrib.get("alt",None)
                    if alt and len(alt):
                        text = alt
                if WebSearchModule._is_block(next_tag):
                    if len(buffer)>0:
                        text_list.append(buffer)
                        buffer = ""
                    text_list.append(text)
                else:
                    if len(text)>0:
                        buffer = f"{buffer} {text}"
            else:
                text = WebSearchModule.normalize( str(next_tag) )
                re11 = r"^[\r\n\t ]*"
                text = re.sub(re11,"",text)
                re12 = r"[\r\n\t ]*$"
                text = re.sub(re12,"",text)
                if len(text)>0:
                    buffer = f"{buffer} {text}"
        if len(buffer)>0:
            text_list.append(buffer)
            buffer = ""
        return "\n".join(text_list)

# Toolの入力パラメータを定義するモデル
class WebSearchInput(BaseModel):
    query: str = Field( '', description='query for google search')

class WebSearchTool(BaseTool):
    name = "WebSearchTool"
    description = (
        "A search engine of Web."
        "Useful for when you need to answer questions about current events from internet content."
    )
    # 入力パラメータのスキーマを定義
    args_schema: Optional[Type[BaseModel]] = WebSearchInput

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
    # 入力パラメータのスキーマを定義
    args_schema: Optional[Type[BaseModel]] = WebSearchInput
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
    
def test():
    module : WebSearchModule = WebSearchModule()
    list = module.search_meta( "迷い猫")
    for d in list:
        print("-----")
        print( f"{d['title']} {d['link']}")
        text = module.get_content( d['link'] )
        print(text)

def main(argv):
    test()
    
def main2(argv):
    module = WebSearchModule()

    zURL="https://udemy.benesse.co.jp/development/python-work/python-list.html"
    zURL="https://www.neko-search.com/"
    #zURL="https://twitter.com/aaaaki1129"
    ret = module.get_content(zURL)

    with open("logs/content.html","rb") as f:
        content = f.read()

    ret = module.get_content_from_bytes( content )
    #mod.get_weather()
    #ret = mod.search_meta('京田辺 天気')
    # for r in ret:
    #     print( r )
    # return 0
    #ret = module.search_snippet('最新ニュース')
    print( ret )

if __name__ == '__main__':
    sys.exit(main(sys.argv))

