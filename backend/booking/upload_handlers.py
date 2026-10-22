from django.core.files.uploadhandler import FileUploadHandler, StopUpload


class BoundedUploadHandler(FileUploadHandler):
    """Stop multipart streams before an oversized file exhausts temporary storage."""

    def __init__(self, request=None):
        super().__init__(request)
        self.total = 0

    def receive_data_chunk(self, raw_data, start):
        self.total += len(raw_data)
        if start + len(raw_data) > 40 * 1024 * 1024 or self.total > 50 * 1024 * 1024:
            raise StopUpload(connection_reset=False)
        return raw_data

    def file_complete(self, file_size):
        return None
