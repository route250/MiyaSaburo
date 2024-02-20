import sys,os,json
if __name__=="__main__": sys.path.append( os.getcwd() )
from MiyaSaburo.tools import JsonStreamParser,JsonStreamParseError

def test():
    # 使用例
    parser = JsonStreamParser()
    json_text = '{ "data":{"key": "value", "uuu":"xyz", "numbers": [1,1.5,[100,{"erer":"tere"},200],+3,-4.0]}, "arry":["a","b","c"], "data2":{ "abc":"def","ijk":"lmn"  } }  '
    for cc in json_text:
        print( f"[{cc}]")
        obj = parser.put(cc)
        try:
            ret = json.dumps(obj,ensure_ascii=False) if obj is not None else "None"
        except:
            ret = str(obj)
        print( f"[{cc}] Parsed object:", ret)

if __name__ == "__main__":
    test()
