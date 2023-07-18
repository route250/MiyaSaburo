import typing
import re

from langchain.memory.chat_message_histories.in_memory import ChatMessageHistory
from langchain.schema import AIMessage

class CustomChatMessageHistory(ChatMessageHistory):

    post_process : typing.Callable = None

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
    _split_re = re.compile(r"([。！])")

    def _is_ignore_word(self, message:str) -> str:
        buf = self._pattern.sub("", message.strip("  。\n"))
        return buf.endswith(self._IGNORE_TUPLE)

    def convert(self, message: str) -> str:
        # lines0 = re.split(r"(?<=[\n])",message0)
        # message = lines0[0]
        lines = re.split(r"(?<=[。！\n])",message)
        results = [line for line in lines if not self._is_ignore_word(line)]
        if self.post_process is not None:
            results = self.post_process(results,lines)
        return "".join(results) if results else "".join(lines)

    def add_ai_message(self, message: str) -> None:
        """Add an AI message to the store"""
        result = self.convert(message)
        self.add_message(AIMessage(content=result))

def test():
    def mypost( m1, m2 ):
        print(f"m1 {m1}")
        print(f"m2 {m2}")
    mem = CustomChatMessageHistory()
    mem.convert("こんにちは！いい天気です。どのようにお手伝いできますか？")
if __name__ == '__main__':
    test()
