def respond_to_user(input):
    """ユーザーの入力に応じて返答する"""
    # 入力と返答のペアをリストで定義
    input_responses = [
        ["こんにちは", "こんにちは！どうしたの？"],
        ["おはよう", "おはようございます！今日はいい天気ですね。"],
        ["こんばんは", "こんばんは。今日の夜は何をして過ごす予定ですか？"]
    ]
    
    # ユーザーの入力に対応する返答を検索
    for input_pair in input_responses:
        if input == input_pair[0]:
            return input_pair[1]
    
    # 対応する返答がない場合のデフォルトの返答
    return "ごめんなさい、よくわかりません。"

def main():
    try:
        while True:
            user_input = input("何か入力してください（Ctrl+DまたはCtrl+Zで終了）: ")
            response = respond_to_user(user_input)
            print(response)
    except EOFError:
        print("\nプログラムを終了します。")

if __name__ == "__main__":
    main()
