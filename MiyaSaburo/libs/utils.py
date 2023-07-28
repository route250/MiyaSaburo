
import time
from zoneinfo import ZoneInfo
from datetime import datetime, timezone

class Utils:

    @staticmethod
    def is_empty( text:str=None ) -> bool:
        return not (text and len(text)>0)

    @staticmethod
    def strip( text:str=None ) -> str:
        if text and len( text.strip() ) > 0:
            return text
        return None

    JST = ZoneInfo("Asia/Tokyo")

    @staticmethod
    def to_unix_timestamp_seconds( date_time:str) -> int:
        try:
            # 日付文字列をdatetimeオブジェクトに変換
            dt_object = datetime.strptime(date_time, '%Y/%m/%d %H:%M:%S')
            # Unix時間に変換 (秒単位)
            time = int(dt_object.replace(tzinfo=Utils.JST).timestamp())
            return time
        except:
            return 0

    @staticmethod
    def from_unix_timestamp_seconds(unix_time: int) -> str:
        # Unix時間をdatetimeオブジェクトに変換
        dt_object = datetime.fromtimestamp(unix_time, Utils.JST)
        # フォーマットに変換して返す
        return dt_object.strftime('%Y/%m/%d %H:%M:%S')

    @staticmethod
    def to_int( value:str, default=0 ) -> int:
        try:
            return int(value)
        except:
            return default