class BackendError(Exception):
    def __init__(self, status_code: int, code: str, message: str, **context):
        super().__init__(message)
        self.status_code = status_code
        self.detail = {"code": code, "message": message, **context}
