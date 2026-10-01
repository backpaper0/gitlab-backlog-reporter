class ReportError(Exception):
    """レポートを書かずに終了コード 1 で止めるエラー。メッセージは1件につき1行。"""

    def __init__(self, *messages: str) -> None:
        super().__init__(*messages)
        self.messages = messages
