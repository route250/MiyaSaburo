import sys,os,json
if __name__=="__main__": sys.path.append( os.getcwd() )
from MiyaSaburo.tools import JsonStreamParser,JsonStreamParseError

def encode_str( text, X=False ):
    j=json.dumps( {"str": text }, ensure_ascii=X )
    #print(f"str:{j[8:-1]}")
    return j[8:-1]

def test_parser( text ):
    parser = JsonStreamParser()
    try:
        for cc in text:
            obj = parser.put(cc)
        return obj
    except Exception as ex:
        return {"ERROR": str(ex) }

def json_parser( text ):
    try:
        return json.loads(text)
    except Exception as ex:
        return {"ERROR": str(ex) }

def estr( text ):
    return text.replace("\r\n","<CRNL>").replace("\n","<NL>").replace("\r","<CR>").replace("\t","<TAB>")

def test():
    # 値
    # dict list str float int

    svalues0=[ None, "abc", "abc\ndef", "ghi\rjkl", "あい\"うえ", "おか\\きく","\u3084\u3091\u3086\u3091\u3088" ]
    svalues=[ encode_str(s) for s in svalues0]
    fvalues=[ "3.14", "7.8e3", "-0.1e-1" ]
    fvalues_ext = [ ".1", "2.", "+.3", "-.4", "+5.", "-6.", "+9.0e+1" ]
    ivalues=[ "0", "-1" ]
    ivalues_ext =[ "+1" ]
    spaces=[
         [ "", "", "", "", "", ""  ],
         [ " "," "," "," "," "," " ],
         [ "\n","\n","\n","\n","\n","\n"],
         [ "\t","\t","\t","\t","\t","\t"],
         [ "", "", "", "", ",\"v\":0", ""  ],
         [ "", "", "", "", " ,\"v\":0", ""  ],
         [ "", "", "", "", ", \"v\":0", ""  ],
    ]
    values=svalues+fvalues+ivalues

    test_list=[]
    txt=values[0]
    for s0,s1,s2,s3,s4,s5 in spaces:
        test_list.append(s0+"{"+s1+"\"key\""+s2+":"+s3+txt+s4+"}"+s5)
    test_list.append( "{ \"key\":[0]}")
    test_list.append( "{ \"key\": [0]}")
    test_list.append( "{ \"key\":[0] }")
    test_list.append( "{ \"key\":{\"key\":0}}")
    test_list.append( "{ \"key\": {\"key\":0}}")
    test_list.append( "{ \"key\":{\"key\":0} }")
    for txt in values:
        test_list.append("{ \"key\": "+txt+" }")
        test_list.append( "[ "+txt+" ]")
    test_list.append( "[0,1]" )
    test_list.append( " [0,1]" )
    test_list.append( "[ 0,1]" )
    test_list.append( "[0 ,1]" )
    test_list.append( "[0, 1]" )
    test_list.append( "[0,1 ]" )
    test_list.append( "[0,1] " )
    for tst in test_list:
        obj1 = test_parser( tst )
        res1 = json.dumps( obj1, ensure_ascii=False )
        obj2 = json_parser( tst )
        res2 = json.dumps( obj2, ensure_ascii=False )
        if res1==res2:
            print( f"OK: {estr(tst)}" )
        else:
            print( f"NG: {estr(tst)}" )
            print( f"    result:{estr(res1)}")
            print( f"    actual:{estr(res2)}")

     # 使用例
    # parser = JsonStreamParser()
    # json_text = '{ "data":{"key": "value", "uuu":"xyz", "numbers": [1,1.5,[100,{"erer":"tere"},200],+3,-4.0]}, "arry":["a","b","c"], "data2":{ "abc":"def","ijk":"lmn"  } }  '
    # for cc in json_text:
    #     print( f"[{cc}]")
    #     obj = parser.put(cc)
    #     try:
    #         ret = json.dumps(obj,ensure_ascii=False) if obj is not None else "None"
    #     except:
    #         ret = str(obj)
    #     print( f"[{cc}] Parsed object:", ret)

if __name__ == "__main__":
    test()
