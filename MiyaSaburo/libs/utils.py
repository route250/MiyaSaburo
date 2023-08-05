
import logging
import time
from zoneinfo import ZoneInfo
from datetime import datetime, timezone

class Utils:

    logger = logging.getLogger(__name__)
    JST = ZoneInfo("Asia/Tokyo")

    @staticmethod
    def is_empty( text:str=None ) -> bool:
        return text is None or len(text)==0

    @staticmethod
    def empty_to_blank( text:str=None ) -> str:
        return text if not Utils.is_empty(text) else ""

    @staticmethod
    def empty_to_none( text:str=None ) -> str:
        return text if not Utils.is_empty(text) else None

    @staticmethod
    def strip( text:str=None ) -> str:
        if text and len( text.strip() ) > 0:
            return text
        return None

    @staticmethod
    def to_unix_timestamp_seconds( date_time:str) -> int:
        try:
            # 日付文字列をdatetimeオブジェクトに変換
            dt_object = datetime.strptime(date_time, '%Y/%m/%d %H:%M:%S')
            # Unix時間に変換 (秒単位)
            time = int(dt_object.replace(tzinfo=Utils.JST).timestamp())
            return time
        except:
            Utils.logger.exception(f"date_time:\"{date_time}\"")
            return 0

    @staticmethod
    def from_unix_timestamp_seconds(unix_time: int) -> str:
        # Unix時間をdatetimeオブジェクトに変換
        dt_object = datetime.fromtimestamp(unix_time, Utils.JST)
        # フォーマットに変換して返す
        return dt_object.strftime('%Y/%m/%d %H:%M:%S')

    @staticmethod
    def formatted_datetime():
        # オペレーティングシステムのタイムゾーンを取得
        #system_timezone = time.tzname[0]
        # 現在のローカル時刻を取得
        #current_time = time.localtime()
        # 日時を指定されたフォーマットで表示
        #formatted = time.strftime(f"%a %b %d %H:%M {system_timezone} %Y", current_time)
        jdt = datetime.now().astimezone(Utils.JST)
        # 日時を指定されたフォーマットで表示
        formatted = jdt.strftime(f"%a %b %d %H:%M %Z %Y")
        return formatted

    @staticmethod
    def to_int( value:str, default=0 ) -> int:
        try:
            return int(value)
        except:
            return default

if __name__ == "__main__":
    j = Utils.formatted_datetime()
    print(f"now {j}")
    now = int(time.time())
    x = "2023/08/02 06:51:00"
    s = Utils.to_unix_timestamp_seconds(x)
    d = s-now
    print(f"{x}")
    print(f"{s}")
    print(f"{now}")
    print(f"{d}")