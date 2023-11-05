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
        'happiness': '0-5の整数',
        'sadness': '0-5の整数',
        'anger': '0-5の整数',
        'confusion': '0-5の整数'
    }
    def __init__(self):
        super().__init__()
        self.emotion_data:dict = {}
        for key in DxEmoChatBot.EMO_FMT.keys():
            self.emotion_data[key] = '0'

    #Override
    def eval_emotion(self) -> str:
        profile = self.create_promptA()

        prompt:str = ""
        if profile is not None:
            prompt = profile + "\n\n"

        prompt_history:str = ChatMessage.list_to_prompt( self.mesg_list + [self.chat_busy])
        prompt += f"Conversation history:\n{prompt_history}\n\n"

        prompt_x = f"上記のConversation historyから、{ChatMessage.ASSISTANT}の感情を推測し、下記のフォーマットで記述してください。"
        prompt_fmt = BotUtils.to_format( DxEmoChatBot.EMO_FMT)
        prompt += f"{prompt_x}\n{prompt_fmt}:"

        print( f"[DBG]EmoPrompt\n{prompt}" )
        self.notify_log(prompt)
        res:str = self.Completion( prompt )
        self.notify_log(res)
        print( f"[DBG]Emo response\n{res}")
        new_emo:dict = BotUtils.parse_response( DxEmoChatBot.EMO_FMT, res )
        if new_emo is not None:
            BotUtils.update_dict( new_emo, self.emotion_data )
            self.update_info( {'emotions': self.emotion_data} )

    #Override
    def create_promptC(self) -> str:
        self.eval_emotion()
        emotion_text:str = BotUtils.to_prompt(self.emotion_data)
        prompt = f"Below are your emotional parameters. Please behave accordingly to this feeling.\n{emotion_text}"
        return prompt

def test():
    bot: DxEmoChatBot = DxEmoChatBot()
    debug_ui(bot)

if __name__ == "__main__":
    test()