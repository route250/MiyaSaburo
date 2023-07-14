from langchain.memory.chat_message_histories.in_memory import ChatMessageHistory
from langchain.schema import AIMessage


import re


class CustomChatMessageHistory(ChatMessageHistory):
    _IGNORE_WORDS = (
        "お手伝いできますか",
        "お手伝いができますか",
        "お手伝いがあれば教えてください",
        "お手伝いできることがあれば教えてください",
        "お手伝いできることはありますか",
        "お手伝いいたします",
        "お手伝いできることがあればお知らせください",
        "お手伝いできるかもしれません",
        "お手伝いできるかと思います",

        "お知らせください",
        "お聞きください",
        "お聞かせください",
        "お話しください",
        "困っているのか教えてください",
        "教えていただけますか",
        "お話を教えてください",

        "お話しましょうか","お話しすることはありますか？",

        "質問があればどうぞ","何か質問がありますか"

        "どんなことでも結構ですよ",


        "頑張ってください", "応援しています",
        "何か特別な予定はありますか",
        "お申し付けください",
        "伝いが必要な場合はお知らせください",
        "遠慮なくお知らせください",
        "サポートいたします",
        "良い一日をお過ごしください",

        "サイトで確認してください",
        "願っています",
        "計画はありますか",

        )
    _IGNORE_TUPLE = tuple( set(_IGNORE_WORDS) )
    _pattern = re.compile(r"[、？！]")

    def convert(self, message: str) -> str:
        lines = message.split("(。)")
        results = []
        for line in lines:
            buf = self._pattern.sub("", line.strip(" 。\n"))
            if buf and not buf.endswith(self._IGNORE_TUPLE):
                results.append(line)
        if results:
            return "".join(results)
        else:
            return ""

    def add_ai_message(self, message: str) -> None:
        """Add an AI message to the store"""
        result = self.convert(message)
        self.add_message(AIMessage(content=result))
