# コンポーネント構成（ドラフト）

- `config.py`：設定・環境変数の単一入口
- `token_store.py`：ローカルトークンI/O
- `parameter_store.py`：AWS SSM I/O（任意）
- `token_refresh.py`：リフレッシュの単一実装（CLI/Actions 共用）
- `notion_queue.py`：キュー取得/更新（プロパティ名は `config` で一元管理）
- `post.py`：投稿実行（変換/エラー判定ユーティリティ呼び出し）
- `cli.py`：`x-post run / authorize / refresh` の窓口（将来）