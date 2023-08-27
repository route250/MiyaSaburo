import os
import sys
import re
import traceback,logging
import lxml.html
from copy import deepcopy
from lxml import html
from lxml.html import  HtmlElement, HtmlComment, HtmlMixin, HtmlEntity

logger = logging.getLogger("HtmlUtil")

class HtmlUtil:

    HTML_SCRIPT_TAGS = [ "script", "#comment" ]
    HTML_BLOCK_TAGS = [ "div","span", "ol", "ul" ]
    HTML_LINK_TAGS = [ "a", "form" ]
    HTML_LINK_ATTS = [ "onclick", "on_click" ]

    @staticmethod
    def bytes_to_document( b: bytes, encoding: str = None ) -> HtmlElement:
        content = None
        enc_list = ["utf-8", "cp932", "iso-2022-jp", "euc-jp"]
        if encoding and encoding in enc_list:
            enc_list = [encoding] + [enc for enc in enc_list if enc != encoding]

        min_count = len(b)+1
        for enc in enc_list:
            try:
                txt = b.decode( enc, errors="backslashreplace" )
                if txt is None or len(txt)==0:
                    continue
                count = txt.count('\\')
                if count < min_count:
                    content = txt
                    min_count = count
            except:
                logger.exception(f"encoding:{enc}")
        if content is None:
            return None

        zDocument: HtmlElement = None
        try:
            zDocument = html.fromstring(content)
        except:
            try:
                zDocument = html.fromstring(b)
            except:
                logger.exception(f"encoding:{encoding}")
                zDocument = None

        return zDocument

    @staticmethod
    def trim_html( doc: HtmlElement ) -> None:
        HtmlUtil.trim_article_tag(doc)
        HtmlUtil.trim_block_tag(doc)

    @staticmethod
    def trim_article_tag( doc: HtmlElement ) -> None:
        article_tags = doc.xpath("//article")
        if article_tags is not None and len(article_tags)>0:
            tag_paths = {}
            # articleタグの祖先をマークする
            for tag in article_tags:
                while tag is not None:
                    tag_paths[tag] = 1
                    tag = tag.getparent()
            # マークされてないタグをクリアする
            for tag in article_tags:
                parent = tag.getparent()
                while parent is not None:
                    tagname = HtmlUtil.tagname(parent)
                    if "html" == tagname:
                        break
                    for child in parent.getchildren():
                        if not child in tag_paths:
                            HtmlUtil.reset_tag(child)
                    parent = parent.getparent()

    @staticmethod
    def trim_block_tag( doc: HtmlElement, limit: float = 0.7 ) -> HtmlElement:
        child: HtmlElement
        for child in doc.getchildren():
            HtmlUtil.trim_block_tag(child)
        tagname = HtmlUtil.tagname( doc )
        if tagname in HtmlUtil.HTML_SCRIPT_TAGS:
            HtmlUtil.reset_tag(doc)
            return doc
        if tagname in HtmlUtil.HTML_BLOCK_TAGS:
            orig_txt: str = HtmlUtil.to_content( doc )
            orig_len: int = HtmlUtil.str_len(orig_txt)
            if orig_len == 0:
                HtmlUtil.reset_tag( doc )
                return doc
            if orig_len>0:
                copy_child = deepcopy(doc)
                HtmlUtil.reset_link_tag( copy_child )
                trim_txt = HtmlUtil.to_content( copy_child )
                rate: float = HtmlUtil.str_len(trim_txt) / orig_len
                if rate < limit:
                    HtmlUtil.reset_tag( doc )
                    return doc
        return doc

    @staticmethod
    def reset_link_tag( doc: HtmlElement ) -> bool:
        tagname = HtmlUtil.tagname(doc)
        if tagname in HtmlUtil.HTML_LINK_TAGS or tagname in HtmlUtil.HTML_SCRIPT_TAGS:
            HtmlUtil.reset_tag(doc)
            return True
        for at in doc.attrib.keys():
            if at.lower() in HtmlUtil.HTML_LINK_ATTS:
                HtmlUtil.reset_tag(doc)
                return True
        result: bool = False
        child: HtmlElement
        for child in doc.getchildren():
            result = HtmlUtil.reset_link_tag(child) or result
        if result:
            txt: str = HtmlUtil.to_content( doc )
            txt_len: int = HtmlUtil.str_len(txt)
            if txt_len == 0:
                HtmlUtil.reset_tag(doc)
                return True
        return False

    @staticmethod
    def reset_tag( doc: HtmlElement ) -> None:
        for child in doc.getchildren():
            doc.remove(child)
        doc.attrib.clear()
        doc.text=''

    @staticmethod
    def tagname( doc: HtmlMixin ) -> str:
        if doc is not None:
            if isinstance(doc,HtmlElement):
                if doc.tag and doc.tag is not None:
                    return doc.tag.lower()
            elif isinstance(doc,HtmlComment):
                return "#comment"
        return None

    @staticmethod
    def to_str( doc: HtmlElement ) -> str:
        return html.unicode( html.tostring( doc,encoding="utf8"), encoding="utf8" )

    @staticmethod
    def to_content( doc: HtmlElement ) -> str:
        content: str = doc.text_content()
        content = re.sub("[\r\n\t ]+","",content)
        return content

    @staticmethod
    def str_is_empty( s: str ) -> bool:
        return HtmlUtil.str_len(s)>0

    @staticmethod
    def str_len( s: str ) -> int:
        if s is None:
            return 0
        return len(str(s))

    RE_NORMALIZE_1 = r"[ \t\r]*\n"
    RE_NORMALIZE_2 = r"\n\n\n*"

    @staticmethod
    def str_normalize( value:str )->str:
        if value is None:
            return "#None"
        value = re.sub(HtmlUtil.RE_NORMALIZE_1,"\n", value)
        value = re.sub(HtmlUtil.RE_NORMALIZE_2,"\n\n", value)
        return value

    @staticmethod
    def str_dump( value:str )->str:
        if value is None:
            return "#None"
        value = value.replace("\\\\","\\")
        value = value.replace("\n","\\n").replace("\\r","\\r").replace("\t","\\t")
        return value


#---------------------------------------------------------
# テスト用
#---------------------------------------------------------
test_data_dir = "MiyaSaburo/test/testData"
temp_data_dir = "tmp"
def main():
    print("----")
    for html_in in os.listdir( test_data_dir ):
        print( html_in)
        if not html_in.endswith("_inp.html"):
             continue
        html_out = html_in.replace("_inp.html","_out.html")
        data_in = f"{test_data_dir}/{html_in}"
        data_out = f"{test_data_dir}/{html_out}"
        if not os.path.exists(data_out):
             continue
        print( f"path {data_in} {data_out}")

        # テストデータ読み込む
        with open( data_in,"rb") as f:
            bin_in = f.read()
        doc_in = HtmlUtil.bytes_to_document( bin_in )
        if doc_in is None:
            print(" doc_in is None")
            continue
        txt_in = html.unicode( html.tostring( doc_in,encoding="utf8"), encoding="utf8" )

        # テスト実行
        HtmlUtil.trim_html( doc_in )

        # 結果を書き込む
        txt_tmp = html.unicode( html.tostring( doc_in,encoding="utf8"), encoding="utf8" )
        tmp_out = f"{temp_data_dir}/{html_out}"
        os.makedirs( temp_data_dir, exist_ok=True)
        with open( tmp_out,"wb") as f:
            f.write( txt_tmp.encode("utf-8"))

        if txt_in == txt_tmp:
            print("OK")
        else:
            print("NG")
            print( txt_tmp )

        # # 正解と比較
        # with open( data_out,"rb") as f:
        #     bin_out = f.read()
        # doc_out = module.get_content_from_bytes( bin_out )

if __name__ == "__main__":
    main()