
import os
from flask import Flask, request, abort

from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
)
from bot_agent import BotRepository, BotAgent

Repo = BotRepository()

def main():

    userid_list = [ 'user001', 'user002', 'user003' ]
    name_list = [ '太郎', '次郎', '三郎' ]

    for i in range(0,len(userid_list)):
        print("---")
        name = name_list[i]
        agent = Repo.get_agent(name)
        query = f'こんにちは、私の名前は{name}です'
        print( f"[REPLY]{query}")
        reply = agent.llm_run(query)
        print( f"[REPLY]{reply}")

    print("---")
    query03 = '私の名前は？お腹すいてない？'
    print( f"[REPLY]{query03}")
    for i in range(0,len(userid_list)):
        name = name_list[i]
        agent = Repo.get_agent(name)
        print("---")
        reply032 = agent.llm_run(query03)
        print( f"[REPLY]{reply032}")
        agent.dump_mem()

if __name__ == "__main__":
    main()