
import os
import sys
import re
import json
import traceback,logging
import requests
import lxml.html as html
from lxml.html import HtmlMixin, HtmlElement, HtmlComment, TextareaElement, HtmlEntity
import urllib.parse
from urllib.parse import urlparse
from enum import Enum
from pydantic import Field, BaseModel
from langchain.tools.base import BaseTool
from typing import Optional, Type
from .html_util import HtmlUtil

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
        "https://twitter.com","https://www.instagram.com","https://www.facebook.com"
    )
    GOOGLE_EXCLUDE_SITE = [
        "-site:youtube.com",
        "-site:amazon.co.jp", "-site:amazon.com",
        "-site:facebook.com",
        "-site:instagram.com", "-site:twitter.com",
        "-site:google.com",
        "-site:twicomi.com",
        "-site:mercari.com", "-site:rakuten.co.jp", 
        "-site:tbs.co.jp", "-site:nhk.or.jp",
        "-site:oricon.co.jp", 
        "-site:pixiv.net",
        "-site:buzzfeed.com",
        "-site:piapro.jp",
        "-site:thoroughbreddailynews.com",
        "-site:www.jrha.or.jp", #馬専門サイト
        "-site:togetter.com",
        '-"記事一覧"', '-"記事 まとめ"', '-"最新情報"', '-"レスリリース一覧"', '-"検索結果"'
       # "cat.blogmura.com": 1,
       ]
    DEFAULT_NUM_RESULT: int = 4

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

    def search_snippet(self, query: str, *,num_result=None,qdr=None,hl:str=None) -> str:
        """Run query through GoogleSearch and parse result."""
        snippets = []
        # results = self.search_meta(query, num_result=num_result,qdr=qdr,hl=hl)
        results = self.google_custom_search(query, num_result=num_result,qdr=qdr,hl=hl)
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

    def search_meta(self,aQuery, *, num_result: int=None, qdr: str = "m1", gl: str = None, hl: str = None, user_agent = None, timeout = None) -> list[dict]:
        
        # qdrは期間指定 1ヶ月 m1 48時間 h48

        num_result = num_result if num_result else WebSearchModule.DEFAULT_NUM_RESULT
        metadata_result = []

        user_agent = user_agent if user_agent else self.mUserAgent
        timeout = timeout if timeout else self.mTimeout

        zEncQuery = WebSearchModule.urlEncode(aQuery)
        #zURL = mBaseURL + "?q=" + zEncQuery + "&ie=UTF-8&gl=us&hl=en"
        zURL = WebSearchModule.mBaseURL + "?q=" + zEncQuery + "&ie=UTF-8"
        # gws_rdはリダイレクト　gws_rd=crでリダイレクト無効
        zURL += "&gws_rd=cr"
        # pwsはプライベート検索 pws=0でプライベート検索無効
        zURL += "&pws=0"
        # glは国を指定
        if gl is not None and len(gl)>0:
            zURL += f"&gl={gl}"
        # hlは言語を指定
        if hl is not None and len(hl)>0:
            zURL += f"&hl={hl}"
        if qdr is not None and len(qdr)>0:
            zURL += f"&tbs=qdr:{qdr}"

        try:
            # requestsを使用してWebページを取得
            response = requests.get(zURL, timeout=timeout, headers={"User-Agent": user_agent}, verify=True)
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
            zSegments = zDocument.xpath(".//div[div/div/a//h3]|.//article[div/div/a//h3]")
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
                if len(metadata_result) >= num_result:
                    break
        except requests.exceptions.ConnectionError as ex:
            print(ex)
        except requests.exceptions.RequestException as e:
            logger.exception("")

        return metadata_result
    
    def google_custom_search (self,aQuery, *, num_result: int=None, qdr: str = "m1", gl: str = None, hl: str = None, timeout = None, cse_id=None, api_key=None) -> list[dict]:
        
        if api_key is None:
            api_key = os.getenv('GOOGLE_API_KEY')
        if cse_id is None:
            cse_id = os.getenv('GOOGLE_CSE_ID')
        url = "https://www.googleapis.com/customsearch/v1"

        # qdrは期間指定 1ヶ月 m1 48時間 h48

        num_result = num_result if num_result else WebSearchModule.DEFAULT_NUM_RESULT
        metadata_result = []

        if api_key is None or cse_id is None:
            return metadata_result

        timeout = timeout if timeout else self.mTimeout

        Q = aQuery + " " + ( " ".join( WebSearchModule.GOOGLE_EXCLUDE_SITE ))
        params = {
            'key': api_key,
            'cx': cse_id,
            'q': Q,
            'c2coff': 1,
            'safe': 'active',
            'fileType': 'html',
        }

        # glは国を指定
        if gl is not None and len(gl)>0:
            params["gl"] = gl
        # hlは言語を指定
        if hl is not None and len(hl)>0:
            params["hl"] = hl
            params["lr"] = f"lang_h{hl}"
        if qdr is not None and len(qdr)>0:
            params["dateRestrict"] = qdr
   
        start_num = 1
        try:
            while start_num>0 and len(metadata_result)<num_result:
                params['start'] = start_num
                response = requests.get(url, params=params)
                if response.status_code != 200:
                    logger.error(f"エラー： {response.status_code} {response.text}.")
                    break
                os.makedirs("logs", exist_ok=True)
                j = None
                try:
                    j = json.loads(response.text)
                    with open("logs/search.json","w") as f:
                        json.dump( j, f, indent=2, ensure_ascii=False )
                except Exception as ex:
                    with open("logs/search.json","wb") as f:
                        f.write(response.text)
                    raise ex
                for item in j.get("items",{}):
                    zLink = item.get("link","")
                    if len(zLink)<3:
                        continue
                    zTitle = item.get("title",None)
                    zSnippet = item.get("snippet",None)
                    zResult = {}
                    zResult["link"] = zLink
                    if zSnippet is None:
                        if zTitle is None:
                            pass
                        else:
                            zSnippet = zTitle
                    else:
                        if zTitle is None:
                            zTitle = zSnippet
                        else:
                            pass
                    zResult["snippet"] = zSnippet
                    zResult["title"] = zTitle
                    metadata_result.append(zResult)
                    if len(metadata_result)>=num_result:
                        break
                
                np = j.get("queries",{}).get("nextPage",[])
                start_num = np[0].get("startIndex",-1) if len(np)>0 else -1
        #   "searchInformation": {
        #     "searchTime": 0.49328,
        #     "formattedSearchTime": "0.49",
        #     "totalResults": "13500000",
        #     "formattedTotalResults": "13,500,000"
        #   },
        except Exception as ex:
            logger.exception("")

        return metadata_result
    

    XPATH_HTAG=".//h1|.//h2|.//h3|.//h4|.//h5|.//h6"
    RE_H_MATCH = re.compile('^h[1-6]$')

    def get_content_bin(self, link: str, *, user_agent = None, timeout = None) -> bytes:
        user_agent = user_agent if user_agent else self.mUserAgent
        timeout = timeout if timeout else self.mTimeout
        # requestsを使用してWebページを取得
        response = requests.get(link, timeout=timeout, headers={"User-Agent": user_agent})
        return response.content
    
    def get_content_as_html( self, link: str,*, user_agent = None, timeout = None, type:str='htag' ) -> HtmlElement:
        try:
            b: bytes = self.get_content_bin( link, user_agent=user_agent, timeout=timeout)
            zDocument = HtmlUtil.bytes_to_document( b )
            return zDocument
        except requests.exceptions.SSLError:
            logger.error( f"SSLError url:{link}")
        except Exception as e:
            logger.exception("Error occured while getting content from URL: {0}. Error: {1}".format(link, str(e)))
        return ""

    def get_content(self, link: str, *, user_agent = None, timeout = None, type:str='htag' ) -> str:
        try:
            # requestsを使用してWebページを取得
            response: bytes = self.get_content_bin( link, user_agent=user_agent, timeout=timeout)
            os.makedirs("logs", exist_ok=True)
            with open("logs/content.html","wb") as f:
                f.write(response)
            return WebSearchModule.get_content_from_bytes( response, None, type=type )
        except requests.exceptions.SSLError:
            logger.error( f"SSLError url:{link}")
        except Exception as e:
            logger.exception("Error occured while getting content from URL: {0}. Error: {1}".format(link, str(e)))
        return ""

    @staticmethod
    def get_content_from_bytes( b: bytes, encoding: str = None,*, type:str='htag') -> str:
        zDocument = HtmlUtil.bytes_to_document( b )
        return WebSearchModule.get_content_from_xxx(zDocument, type=type)

    @staticmethod
    def get_content_from_str( content: str,*, type:str='htag') -> str:
        zDocument: HtmlElement = html.fromstring(content)
        return WebSearchModule.get_content_from_xxx(zDocument)

    @staticmethod
    def get_content_from_xxx( zDocument: HtmlElement,*, type:str='htag') -> str:
        HtmlUtil.trim_html( zDocument )
        os.makedirs("logs", exist_ok=True)
        with open("logs/content-trim.html","wb") as f:
            f.write( html.tostring(zDocument))
        text = WebSearchModule.get_child_content(zDocument)
        norm_text = HtmlUtil.str_normalize(text)
        return norm_text

    @staticmethod
    def get_content_from_xxx_old( zDocument: HtmlElement,*, type:str='htag') -> str:
        h_content = []
        try:
            ads_xpath = [
                 "body//script[contains(@src,'googlesyndication')]",
                 "body//a[contains(@href,'doubleclick.net')]",
                 "body//a[contains(@href,'amazon')]",
                ]
            remove_xpath = [
                ".//head/meta", ".//head/comment()", ".//head/link",
                 ".//script",".//style", ".//svg", ".//comment()",
                ]
            deltag = {}
            for xpath in ads_xpath:
                for e1 in zDocument.xpath(xpath):
                    parent = e1.getparent()
                    parent.remove(e1)
                    e2 = parent
                    while e2 is not None:
                        parent = e2.getparent()
                        if parent is not None and e2.tag == "div":
                            deltag[e2] = 1
                            break
                        e2 = parent
            for e in deltag.keys():
                clear_tag(e)
            for xpath in remove_xpath:
                for e in zDocument.xpath(xpath):
                    clear_tag(e)
            ads_remove_tags(zDocument)

            os.makedirs("logs", exist_ok=True)
            with open("logs/content-trim.html","wb") as f:
                f.write( html.tostring(zDocument))

            if type=='title':
                zMain = scan_main_content_by_title( zDocument )
                if zMain is not None:
                    ads_remove_tags(zDocument)
                    text = WebSearchModule.get_child_content(zMain)
                    norm_text = HtmlUtil.str_normalize(text)
                    if len(norm_text)>0:
                        h_content.append( norm_text )
            else:
                zMain = WebSearchModule._scan_main_content_by_htag( zDocument )
                if zMain is not None:
                    # 特定の要素を選択して情報を取得する
                    h_tag: HtmlElement
                    for h_tag in zMain.xpath(WebSearchModule.XPATH_HTAG):
                        h_text = h_tag.text_content()
                        h_text = HtmlUtil.str_normalize(h_text)
                        text = WebSearchModule.get_next_content(h_tag,stop=True)
                        norm_text = HtmlUtil.str_normalize(text)
                        if len(norm_text)>0:
                            h_content.append( norm_text )
        except Exception as e:
            logger.exception("")
        return HtmlUtil.str_normalize("\n".join(h_content))

    # -----------------------------------------------------------------
    # 配下のhタグが一番多いdivタグを探す
    # -----------------------------------------------------------------
    @staticmethod
    def _scan_main_content_by_htag( elem: HtmlElement) -> HtmlElement:
        zMap: dict[HtmlElement,int] = {}
        for h_tag in elem.xpath(WebSearchModule.XPATH_HTAG):
            e: HtmlElement = h_tag
            while e is not None:
                try:
                    if e.tag == "div" or e.tag == "article":
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
    # titleが含まれるdivタグを探す
    # -----------------------------------------------------------------
    @staticmethod
    def _scan_main_content_by_title( elem: HtmlElement ) -> HtmlElement:
        title: str = ""
        tags = elem.xpath("/html/head/title/text()")
        if tags is not None and len(tags)>0:
            title = str(tags[0])
        zTarget: HtmlElement = WebSearchModule._get_element_by_content( elem, title )
        if zTarget is None:
            return None
        # print( f"タイトル:{title}\n選択されたタグ")
        # print( html.unicode( html.tostring(zTarget,encoding="utf8"), encoding="utf8" ) )

        e = zTarget
        p1 = e
        p1000 = None
        p2000 = None
        minlen = len(title)+200
        while e is not None:
            p1 = e
            txt = WebSearchModule.get_child_content(e)
            size = len( txt )
            if size > 2000:
                p2000 = e
                break
            elif size > minlen:
                p1000 = e
            e = e.getparent()
        if p1000 is not None:
            return p1000
        if p2000 is not None:
            return p2000
        return p1

    @staticmethod
    def _get_element_by_content( elem: HtmlElement, title: str ) -> HtmlElement:
        top = HtmlUtil.get_tags_by_title( elem, title )
        if top is None:
            return None
        if len(top) == 1:
            return top[0]

        # 復数あったので、絞り込む
        zTagMap = {}
        for e in top:
            e = HtmlUtil.pop_tag(e)
            ss = e.xpath("following-sibling::*")
            nn = len(ss)
            zTagMap[e] = nn
        top, maxcount = HtmlUtil.maxscore(zTagMap)
        if len(top) == 1:
            return top[0]

        # 復数あったので、絞り込む
        zTagMap = {}
        for e in top:
            pri = tag_pri(e)
            zTagMap[e] = pri
        top, maxcount = HtmlUtil.maxscore(zTagMap)
        if len(top) == 1:
            return top[0]

        maxcount = 0
        sib = []
        for e in top:
            n = e.xpath("count(following-sibling::*)")
            # pp = e.getparent()
            # ptxt = WebSearchModule.get_child_content(pp)
            # print(f"select:{n}\n{ptxt}\n\n\n")
            if n>maxcount:
                maxcount = n
                sib = [ e ]
            elif n == maxcount:
                sib.append(e)
        if len(sib) == 1:
            return sib[0]

        key = max(zTagMap, key=zTagMap.get)
        if zTagMap[key]>0:
            return key
        return None

    @staticmethod
    def _axdepth( elem, limit ):
        e = elem
        ret = 0
        while e is not None:
            txt = WebSearchModule.get_child_content(e)
            size = len(txt)
            if size> limit:
                break
            ret += 1
            e = e.getparent()
        return ret

    @staticmethod
    def get_depth(element):
        depth = 0
        while element.getparent() is not None:
            depth += 1
            element = element.getparent()
        return depth
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
    # テキスト化する
    # -----------------------------------------------------------------
    @staticmethod
    def get_child_content( elem: HtmlElement ) -> str:
        tag_list = elem.xpath("text()|*")
        return WebSearchModule.__get_next_content( tag_list, stop=False )
    
    # -----------------------------------------------------------------
    # elemとその次のエレメントをテキスト化する
    # -----------------------------------------------------------------
    @staticmethod
    def get_next_content( elem, stop=False ) -> str:
        tag_list = elem.xpath(".|following-sibling::*|following-sibling::text()")
        return WebSearchModule.__get_next_content( tag_list, stop=stop, elem=elem )

    # -----------------------------------------------------------------
    # elemとその次のエレメントをテキスト化する
    # -----------------------------------------------------------------
    @staticmethod
    def __get_next_content( tag_list, stop=False, elem=None ) -> str:
        text_list=[]
        buffer = ""
        for next_tag in tag_list:
            if isinstance( next_tag, HtmlMixin ):
                if stop and elem != next_tag and WebSearchModule.RE_H_MATCH.match( str(next_tag.tag) ):
                    break
                if isinstance( next_tag, HtmlComment ):
                    continue
                #child_list = next_tag.getchildren()
                #if len(child_list)>0:
                #    text = WebSearchModule.get_next_content( child_list[0] )
                #else:
                #    text = next_tag.text_content()
                text = WebSearchModule.get_child_content( next_tag )
                text = HtmlUtil.str_normalize( text )
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
                        buffer = f"{buffer} {text}".strip()
            else:
                text = HtmlUtil.str_normalize( str(next_tag) )
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

    # -----------------------------------------------------------------
    # イテレーター
    # -----------------------------------------------------------------
    def inerator( self, query_list: list[str], *, num_result = 10, qdr=None, hl=None ):
        Ite: WebSearchModule.ResultIterator = self.ResultIterator(query_list,num_result=num_result, qdr=qdr, hl=hl )
        return Ite

    class ResultIterator(object):

        def __init__(self, query_list: list[str], num_result = 10, qdr=None, gl=None, hl=None ):
            self.module : WebSearchModule = WebSearchModule()
            self.num_result = num_result
            self.qdr = qdr
            self.gl = gl
            self.hl = hl
            self.res_list = []
            self.res_index = 0
            self.query_list = query_list
            self.query_index = 0

        def __iter__(self):
            return self

        def __next__(self):
            ret = self.next()
            if ret is None:
                raise StopIteration()
            else:
                return ret

        def next(self):
            ret = None
            while ret is None:
                while self.res_index>=len(self.res_list):
                    if self.query_index<len(self.query_list):
                        query,prop = self.query_list[self.query_index]
                        self.query_index += 1
                        self.res_index = 0
                        self.res_list = self.search_meta( query,prop )
                    else:
                        return None
                ret = self.res_list[self.res_index]
                self.res_index += 1
                # youtubeは除外
                site_link = ret.get('link',"")
                hostname = urlparse(site_link).netloc if site_link is not None or len(site_link)>1 else None
                if hostname is None or len(hostname)<1 or not any(c.isalpha() for c in hostname):
                    ret = None
                elif hostname.find("youtube")>=0:
                    ret = None
            return ret

        def search_meta( self, query: str, prop: dict=None ):
            print( f"[検索中] {query}" )
            results = None
            try:
                if isinstance(prop,dict):
                    xnum = prop.get("num",self.num_result)
                    xqdr = prop.get("qdr",self.qdr)
                    xgl = prop.get("gl",self.gl)
                    xhl = prop.get("hl",self.hl)
                else:
                    xnum = self.num_result
                    xqdr = self.qdr
                    gl = self.gl
                    hl = self.hl                    
                # results = self.module.search_meta( query, num_result = xnum, qdr=xqdr, gl=xgl, hl=xhl )
                results = self.module.google_custom_search( query, num_result = xnum, qdr=xqdr, gl=xgl, hl=xhl )
                if prop is not None:
                    for r in results:
                        r['prop'] = prop
            except Exception as ex:
                print(ex)
            if results is None:
                results = []
            return results

    def inerator2( self, q1: list[str], q2: list[str], num_result = 10, qdr=None, gl=None, hl=None ):
        Ite1: WebSearchModule.ResultIterator = self.ResultIterator(q1,num_result=num_result, qdr=qdr, gl=gl, hl=hl )
        Ite2: WebSearchModule.ResultIterator = self.ResultIterator(q2,num_result=num_result, qdr=qdr, gl=gl, hl=hl )
        return WebSearchModule.MultiIterator( [ Ite1, Ite2 ] )

    class MultiIterator(object):

        def __init__(self, ite_list: list):
            self.ite_list = ite_list
            self.ite_index = 0

        def __iter__(self):
            return self

        def xget(self):
            try:
                return self.ite_list[self.ite_index].__next__()
            except:
                return None

        def __next__(self):
            ret = None
            while ret is None:
                ret = self.xget()
                self.ite_index = (self.ite_index + 1) % len(self.ite_list)
                if ret is None and self.ite_index==0:
                    raise StopIteration()
            return ret
    

#------------------------------------------------------------------------------
# clear tags
#------------------------------------------------------------------------------
def clear_tag( elem ):
    try:
        if elem is not None:
            for child in list(elem):
                elem.remove(child)
            elem.attrib.clear()
            elem.text = None
    except:
        logger.exception("")
    return elem

#------------------------------------------------------------------------------
#
#------------------------------------------------------------------------------
def get_first( list: list[HtmlElement] ) -> HtmlElement:
    if list is None or len(list)==0:
        return None
    return list[0]

#------------------------------------------------------------------------------
#
#------------------------------------------------------------------------------
def get_first_by_xpath( elem: HtmlElement, xpath: str ) -> HtmlElement:
    try:
        return get_first( elem.xpath( xpath ))
    except:
        logger.exception(f"xpath:{xpath}")
    return None

#------------------------------------------------------------------------------
#
#------------------------------------------------------------------------------
def get_div_tag( elem: HtmlElement ) -> list[HtmlElement]:
    try:
        result: list[HtmlElement] = []
        div_list: list[HtmlElement] = elem.xpath( ".//div|.//span|.//section|.//ul|.//ol|.//td" )
        for div in div_list:
            childs = div.xpath( ".//div|.//span|.//section|.//ul|.//ol|.//td")
            if childs is None or len(childs)==0:
                result.append(div)
        return result
    except:
        pass
    return []

#------------------------------------------------------------------------------
# parentの子孫にchildが存在するか？
# childはparentの子孫か？
#------------------------------------------------------------------------------
def is_child( parent: HtmlElement, child: HtmlElement ) -> bool:
    if parent is None or child is None or parent == child:
        return False
    child = child.getparent()
    while child is not None:
        if parent == child:
            return True
        child = child.getparent()
    return False    
        
#------------------------------------------------------------------------------
# dictのキーが他のキーの子供なら削除する
#------------------------------------------------------------------------------
def uniq_tag( map: dict ) -> dict:
    list = [ x for x in map.keys()]
    for tag in list:
        tag = tag.getparent()
        while tag is not None:
            if tag in map:
                break
            tag = tag.getparent()
        if tag is not None:
            del map[tag]
    return map

#------------------------------------------------------------------------------
# タグ名による優先度
#------------------------------------------------------------------------------
def tag_pri( elem: HtmlElement ) -> int:
    while elem is not None:
        tag = elem.tag.lower()
        if "article"==tag:
            return 10
        elif "h1"==tag:
            return 9
        elif "h2"==tag:
            return 8
        elif "h3"==tag:
            return 7
        elif "h4"==tag:
            return 6
        elif "h5"==tag:
            return 5
        elif "h6"==tag:
            return 4
        elif "div"==tag:
            return 3
        elif "span"==tag:
            return 2
        elem = elem.getparent()
    return 0

#------------------------------------------------------------------------------
# titleが含まれるdivタグを探す
#------------------------------------------------------------------------------
def scan_main_content_by_title( elem: HtmlElement ) -> HtmlElement:

    title_tag = get_title_tag( elem )
    if title_tag is None:
        return None

    title = title_tag.text_content().strip()
    print( f"タイトル:{title}\n選択されたタグ")
    print( html.unicode( html.tostring(title_tag,encoding="utf8"), encoding="utf8" ) )

    e = title_tag
    p1 = e
    p1000 = None
    p2000 = None
    minlen = len(title)+200
    while e is not None:
        p1 = e
        txt = e.text_content().strip()
        size = len( txt )
        if size > 2000:
            p2000 = e
            break
        elif size > minlen:
            p1000 = e
        e = e.getparent()
    if p1000 is not None:
        return p1000
    if p2000 is not None:
        return p2000
    return p1

#------------------------------------------------------------------------------
#
#------------------------------------------------------------------------------
def get_title_tag( html: HtmlElement ) -> list[HtmlElement]:
    # headerからタイトル
    tags = get_first_by_xpath( html, "/html/head/title")
    if tags is None:
        return None
    title: str = tags.text_content().strip()
    if len(title)==0:
        return None
    # タイトル文字列を含むタグを探す
    step = 3
    word_list = []
    for i in range(0,len(title)):
        key = title[i:i+step].strip()
        if len(key)>0:
            key=key.replace("&","&amp;")
            key=key.replace("'","&quot;")
            word_list.append(key)
    for i in range(0,len(title),step+2):
        key = title[i:i+step].strip()
        if len(key)>0:
            word_list.append(key)

    zTagMap: dict[HtmlElement,int] = {}
    for w in word_list:
        for e in html.xpath(f"/html/body//*[contains(text(),'{w}')]"):
            zTagMap[e] = zTagMap.get(e,0) + 1
    if not zTagMap:
        return None
    count = len(word_list)*0.5
    # スコアが高いのを選択
    title_tags, score = HtmlUtil.maxscore(zTagMap)
    if score<count:
        return None

    title_tags = [ HtmlUtil.pop_tag(e) for e in title_tags ]
    
    if len(title_tags)==1:
        return title_tags[0]
    
    # 広告タグを除外
    x_title_tags = title_tags
    ads_tags = ads_get_tags( html )
    for ad in ads_tags:
        x_title_tags = [ x for x in x_title_tags if not is_child(ad,x)]

    if len(x_title_tags)==1:
        return x_title_tags[0]
    if len(x_title_tags)>0:
        title_tags = x_title_tags

    # タグ名で除外
    zTagMap = {}
    for e in title_tags:
        pri = tag_pri(e)
        zTagMap[e] = pri
    title_tags, maxcount = HtmlUtil.maxscore(zTagMap)
    if len(title_tags) == 1:
        return title_tags[0]

    return title_tags[0]

#------------------------------------------------------------------------------
# 広告除去
#------------------------------------------------------------------------------
def ads_remove_tags( elem: HtmlElement ):
    ads_tags = ads_get_tags( elem )
    for tag in ads_tags:
        clear_tag(tag)
        try:
            tag.getparent().remove(tag)
        except:
            pass
#------------------------------------------------------------------------------
#
#------------------------------------------------------------------------------
def ads_strip( text: str ) -> str:
    if text is None or len(text)==0:
            return ""
    text = text.strip()
    text = text.replace('\xa0',' ')
    text = text.replace("»"," ")
    text = re.sub( r"[ 0-9]+年[ 0-9]+月[ 0-9]+日[ ]*"," ",text)
    text = re.sub( r"[\r\n\t ]+"," ",text)
    text = re.sub( r"[*＊ ][*＊ ][*＊ ]+","***", text)
    text = re.sub( r"[-= ][-= ][-= ]+","---", text)
    return text
#------------------------------------------------------------------------------
# 広告タグを取得する
#------------------------------------------------------------------------------
def ads_get_tags( elem: HtmlElement ) -> list[HtmlElement]:
    try:
        result: dict[HtmlElement,float] = {}
        div_list = elem.xpath( ".//div|.//span|.//section|.//ul|.//ol|.//table|.//tr|.//td" )
        for div in div_list:

            div_txt = ads_strip( div.text_content() )
            l1 = len( div_txt )
            if l1<10:
                continue
            l2 = 0
            for a in div.xpath(".//a"):
                a_txt = ads_strip( a.text_content() )
                l2 = l2 + len(a_txt) + 1
            rate = l2/l1

            if rate>0.8:
                tag = HtmlUtil.pop_tag(div)
                result[tag] = rate

        uniq_tag( result )
        return [ x for x in result.keys()]
    except:
        logger.exception("error")
        pass
    return []


#------------------------------------------------------------------------------
# Toolの入力パラメータを定義するモデル
#------------------------------------------------------------------------------
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
        # return self.module.search_meta(query)
        return self.module.google_custom_search(query)
    async def _arun(
        self, query: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None
    ) -> str:
        """Use the tool asynchronously."""
        raise NotImplementedError("custom_search does not support async")
    
def test():
    module : WebSearchModule = WebSearchModule()
    # list = module.search_meta( "迷い猫")
    list = module.google_custom_search( "迷い猫")
    for d in list:
        print("-----")
        print( f"{d['title']} {d['link']}")
        text = module.get_content( d['link'] )
        print(text)

def xtest():
    module : WebSearchModule = WebSearchModule()

    # とあるビルにて「何階に行くの？」「3階ニャ！」猫が ... - カラパイア https://karapaia.com/archives/52324809.html
    site_link="https://karapaia.com/archives/52324809.html"

    # 扇風機大好き少年の夢をかなえるために→「ねこ型扇風機」のクラファンが話題　デザインは兄、鳴き声は猫……家族みんなで形に - ねとらぼ
    #site_link="https://nlab.itmedia.co.jp/nl/articles/2306/11/news016.html"

    # 最新猫ニュース2023年5月12日【感動の再会】米国サウスカロライナ州で飼い猫が行方不明になってしまう→10年ぶりに発見されて身元が判明by Cat Press編集部
    site_link="https://cat-press.com/cat-news/reunited-after-10-years"

    #2023'「長崎県の保護犬保護猫ビフォーアフター展」（佐世保市後援） https://www.city.sasebo.lg.jp/hokenhukusi/seikat/2023_dog_cat_before_after.html
    #site_link = "https://www.city.sasebo.lg.jp/hokenhukusi/seikat/2023_dog_cat_before_after.html"

    # 「自動改札機」の上でぐっすり眠る猫が話題 まったく起きない様子 ... https://news.yahoo.co.jp/articles/25303952d13383fc45e501c1c3a45a467ad0d53f
    #site_link = "https://news.yahoo.co.jp/articles/25303952d13383fc45e501c1c3a45a467ad0d53f"
    #---

    #飼い猫の1日の行動を首輪で追跡｢Catlog｣の凄み 犬に比べると｢猫は ... https://toyokeizai.net/articles/-/462291%3Fdisplay%3Db
    #site_link = "https://toyokeizai.net/articles/-/462291%3Fdisplay%3Db"
    #｢お洒落な人は犬派に多い｣猫好きが知らない真実 定点調査で検証｢犬 ... https://toyokeizai.net/articles/-/644505%3Fdisplay%3Db
    
    site_text = module.get_content( site_link, type="title" )
    print( f"{site_text}" )

def main(argv):
    xtest()
    
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
def test_cse():
    module = WebSearchModule()
    ret = module.google_custom_search( "猫" )
    print( ret )

if __name__ == '__main__':
    test_cse()
    #sys.exit(main(sys.argv))

