import sys, os
from pathlib import Path
from dotenv import load_dotenv
import logging
import time
from zoneinfo import ZoneInfo
from datetime import datetime, timezone, timedelta

class Utils:

    logger = logging.getLogger(__name__)
    JST = ZoneInfo("Asia/Tokyo")

    @staticmethod
    def load_env( name: str ) -> None:
        homedir=Path.home()
        if homedir is not None and len(str(homedir))>0:
            envfile=f"{homedir}/{name}"
            if os.path.exists(envfile):
                load_dotenv( envfile )

    @staticmethod
    def str_length( value ) -> int:
        if value is None:
            return 0
        if not isinstance( value, (str) ):
            value = str(value)
        return len(value)

    _QUOT_PAIR_ = [ "()",r"{}","<>","「」","「」","【】","（）","『』","［］", "『』" ]
    @staticmethod
    def str_unquote( value ) -> str:
        if value is None:
            return ""
        if not isinstance( value, (str) ):
            value = str(value)
        value = value.strip()
        b=True
        while b and len(value)>=2:
            b=False
            while len(value)>=2 and value[0] == value[-1]:
                b=True
                value = value[1:-1].strip()
            for q in Utils._QUOT_PAIR_:
                if value[0] == q[0] and value[-1] == q[-1]:
                    b=True
                    value = value[1:-1].strip()

        return value

    @staticmethod
    def contains_kana(text):
        for char in text:
            # ひらがなのUnicode範囲
            if '\u3040' <= char <= '\u309F':
                return True
            # カタカナのUnicode範囲
            if '\u30A0' <= char <= '\u30FF':
                return True
        return False

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
    def to_unix_timestamp_seconds( date_time:str, *, verbose = True) -> int:
        try:
            # 日付文字列をdatetimeオブジェクトに変換
            dt_object = None
            for fmt in ['%Y/%m/%d %H:%M:%S','%Y-%m-%d %H:%M:%S','%Y/%m/%d','%Y-%m-%d']:
                try:
                    dt_object = datetime.strptime(date_time, fmt)
                    break
                except:
                    pass
            if dt_object is None:
                raise Exception(f"invalid date string {date_time}")
            # Unix時間に変換 (秒単位)
            time = int(dt_object.replace(tzinfo=Utils.JST).timestamp())
            return time
        except:
            if verbose:
                Utils.logger.exception(f"date_time:\"{date_time}\"")
            return 0

    @staticmethod
    def from_unix_timestamp_seconds(unix_time: int) -> str:
        # Unix時間をdatetimeオブジェクトに変換
        dt_object = datetime.fromtimestamp(unix_time, Utils.JST)
        # フォーマットに変換して返す
        return dt_object.strftime('%Y/%m/%d %H:%M:%S')

    @staticmethod
    def date_from_unix_timestamp_seconds(unix_time: int) -> str:
        # Unix時間をdatetimeオブジェクトに変換
        dt_object = datetime.fromtimestamp(unix_time, Utils.JST)
        # フォーマットに変換して返す
        return dt_object.strftime('%Y/%m/%d')

    @staticmethod
    def date_from_str( date: str) -> str:
        try:
            sec = Utils.to_unix_timestamp_seconds( date, verbose=False )
            if sec>0:
                return Utils.date_from_unix_timestamp_seconds(sec)
        except:
            pass
        return None

    @staticmethod
    def date_today( days=0 ) -> str:
        jdt = datetime.now().astimezone(Utils.JST)
        if days != 0:
            td = timedelta(days=days)
            jdt = jdt + td
        # 日時を指定されたフォーマットで表示
        formatted = jdt.strftime(f"%Y/%m/%d")
        return formatted


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