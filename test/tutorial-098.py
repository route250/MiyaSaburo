import os

def main():
    # 環境変数 'SAMPLE_ENV_VAR' の値を取得します。
    # 環境変数が設定されていない場合は、'Not Set' というデフォルト値を使用します。
    env_var_value = os.getenv('SAMPLE_ENV_VAR', 'Not Set')
    
    # 環境変数の値（またはデフォルト値）を表示します。
    print(f"SAMPLE_ENV_VAR の値: {env_var_value}")

    # 環境変数を設定する例を示します（実際のプログラムでこのように設定することは少ないですが、理解の助けになります）。
    # 注意: この設定はこのプログラムの実行中にのみ有効であり、プログラムが終了すると失われます。
    os.environ['SAMPLE_ENV_VAR'] = 'Example Value'
    updated_value = os.getenv('SAMPLE_ENV_VAR')
    print(f"更新後の SAMPLE_ENV_VAR の値: {updated_value}")

if __name__ == "__main__":
    main()
