def main():
    try:
        while True:  # 無限ループ
            user_input = input("何か入力してください（Ctrl+DまたはCtrl+Zで終了）: ")
            print("あなたが入力したのは: " + user_input)
    except EOFError:
        print("\nプログラムを終了します。")

if __name__ == "__main__":
    main()

