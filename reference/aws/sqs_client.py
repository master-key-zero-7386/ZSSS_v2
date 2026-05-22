

"""
Amazon SQS クライアント雛形
将来、ZSSSで通知を受信・処理するために利用する。
"""

import boto3


def create_sqs_queue(queue_name: str):
    """
    将来的に SQS キューを作成する処理をここに実装予定
    """
    raise NotImplementedError("SQSキュー作成は未実装です")


def get_queue_url(queue_name: str):
    """
    将来的に SQS の URL を取得する処理をここに実装予定
    """
    raise NotImplementedError("SQSキュー取得は未実装です")