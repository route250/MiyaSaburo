from typing import Any, Dict, List, Optional, Sequence, Union
from langchain.memory import ConversationBufferMemory,ConversationSummaryBufferMemory,CombinedMemory
from langchain.schema.messages import BaseMessage
from langchain.schema.messages import SystemMessage, AIMessage, HumanMessage
from libs.bot_model import AbstractBot

class ExtConversationSummaryBufferMemory(ConversationSummaryBufferMemory):

    Bot : AbstractBot
    _extend_data = {}

    def set_post_prompt(self, message:str):
        self._extend_data['post_prompt'] = message

    def clear_post_prompt(self):
        del self._extend_data['post_prompt']

    def summarize_all(self) -> None:
        pruned_memory = self.chat_memory.messages[:]
        self.moving_summary_buffer = self.predict_new_summary( pruned_memory, self.moving_summary_buffer )
        self.chat_memory.messages = []

    def load_memory_variables(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        ret = super().load_memory_variables(inputs)
        post_prompt = self._extend_data.get('post_prompt',None)
        if self.return_messages and post_prompt:
            self.clear_post_prompt()
            buf = ret.get(self.memory_key,[])
            post_messages: List[BaseMessage] = [
                self.summary_message_cls(content=post_prompt)
            ]
            buffer = buf + post_messages
            ret[self.memory_key] = buffer
        return ret

    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, str]) -> None:
        if self.output_key is None:
            if len(outputs) != 1:
                raise ValueError(f"One output key expected, got {outputs.keys()}")
            output_key = list(outputs.keys())[0]
        else:
            output_key = self.output_key
        ai_message = outputs.get(output_key,"")
        if ai_message and self.Bot is not None:
            outputs[output_key] = self.Bot.tone_convert(ai_message)
        super().save_context(inputs,outputs)