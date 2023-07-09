from langchain.memory.chat_message_histories.in_memory import ChatMessageHistory
from langchain.schema import AIMessage


import re


class CustomChatMessageHistory(ChatMessageHistory):
    _IGNORE_WORDS = (
        "お手伝いできますか",
        "お手伝いがあれば教えてください",
        "手伝いできることがあれば教えてください",
        "お手伝いできることはありますか",
        "お手伝いいたします",

        "質問やサポートがあればお知らせください",
        "困っているのか教えてください",
        "困り事があればお知らせください",

        "頑張ってください", "応援しています",
        "何か特別な予定はありますか",
        "質問があればどうぞ","何か質問がありますか"
        "お申し付けください",
        "伝いが必要な場合はお知らせください",
        "遠慮なくお知らせください",
        "お気軽にお聞きください","お気軽にお聞かせください",
        "サポートいたします",
        "良い一日をお過ごしください",

        )
    _IGNORE_TUPLE = tuple( set(_IGNORE_WORDS) )
    _pattern = re.compile(r"[、？！]")

    def convert(self, message: str) -> str:
        lines = message.split("。")
        results = []
        for line in lines:
            line = self._pattern.sub("", line)
            if line and not line.endswith(self._IGNORE_TUPLE):
                results.append(line)
        if results:
            return "。".join(results) + "。"
        else:
            return ""

    def add_ai_message(self, message: str) -> None:
        """Add an AI message to the store"""
        result = self.convert(message)
        self.add_message(AIMessage(content=result))
