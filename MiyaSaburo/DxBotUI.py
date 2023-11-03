
import queue
import tkinter as tk
from tkinter import scrolledtext
from DxBotUtils import BotCore, BotUtils

def debug_ui( bot ):
    # キューの作成
    update_queue = queue.Queue()

    # GUIを作成する
    root = tk.Tk()
    root.title("LLM Interaction GUI")

    # 画面サイズを縦長に設定（幅x高さ）
    root.geometry("1000x800")
    # 左側の列
    history_textarea = scrolledtext.ScrolledText(root, height=10)
    history_textarea.grid(row=0, column=0, padx=10, pady=5, sticky="nsew")

    send_textarea = scrolledtext.ScrolledText(root, height=3)
    send_textarea.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")

    def send_to_bot():
        response_text = send_textarea.get('1.0', tk.END)
        if bot.add_talk( response_text.strip() ):
            send_textarea.delete('1.0',tk.END)

    send_button = tk.Button(root, text="Send Prompt", command=send_to_bot)
    send_button.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

    # ウィンドウのグリッド設定
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(0, weight=10)
    root.grid_rowconfigure(1, weight=3)
    root.grid_rowconfigure(2, weight=1)

    def append_message( role, message ):
        current:str = history_textarea.get(1.0,tk.END)
        text:str = f"{role}: {message}"
        if len(current.strip())==0:
            history_textarea.delete(1.0,tk.END)
            history_textarea.insert(1.0,text)
        else:
            history_textarea.insert(tk.END,"\n"+text)

    bot.chat_callback = lambda role,message: append_message(role,message)

    # GUIを更新するためにメインスレッドで定期的に呼び出される関数
    def check_queue():
        try:
            while not update_queue.empty():
                func = update_queue.get_nowait()
                func()  # ラムダ式や関数を実行する
            # 100ms後に再度この関数を呼び出す
        finally:
            root.after(100, lambda: check_queue() )
    check_queue()
    # GUIを起動する
    root.mainloop()

