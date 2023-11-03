import time
import json
import traceback
import concurrent.futures
import queue
from concurrent.futures import ThreadPoolExecutor, Future
from DxBotUtils import BotCore, BotUtils
from DxChatBot import ChatMessage,DxChatBot
from DxBotUI import debug_ui

class DxEmoChatBot(DxChatBot):
    EMO_FMT = {
        '嬉しさ': '0-5の整数',
        '悲しさ': '0-5の整数',
        '怒り': '0-5の整数',
        '困惑': '0-5の整数'
    }
    def __init__(self):
        super().__init__()
        self.emotion_data:dict = {}
        for key in DxEmoChatBot.EMO_FMT.keys():
            self.emotion_data[key] = '0'

    #Override
    def create_prompt(self,*,prefix=None,postfix=None) -> str:
        prompt_history:str = ChatMessage.list_to_prompt( self.mesg_list + [self.chat_busy])
        prompt_x = f"上記の会話の結果、{ChatMessage.ASSISTANT}の感情がどのようになるかを下記のフォーマットで記述してください。"
        prompt_fmt = BotUtils.to_format( DxEmoChatBot.EMO_FMT)

        prompt = f"Conversation history:\n{prompt_history}\n\n{prompt_x}\n{prompt_fmt}:"
        print( f"[DBG]EmoPrompt\n{prompt}" )
        res:str = self.Completion( prompt )
        print( f"[DBG]Emo response\n{res}")
        new_emo:dict = BotUtils.parse_response( DxEmoChatBot.EMO_FMT, res )
        if new_emo is not None:
            BotUtils.update_dict( new_emo, self.emotion_data )
        #---------------------------------
        prompt_emo:str = BotUtils.to_prompt(self.emotion_data)
        prompt_emo = "emotion of " + ChatMessage.ASSISTANT +"\n" + "感情に合うセリフを生成してね\n" + prompt_emo
        return super().create_prompt( prefix=prefix, postfix=prompt_emo )

def test():
    bot: DxEmoChatBot = DxEmoChatBot()
    debug_ui(bot)

if __name__ == "__main__":
    test()