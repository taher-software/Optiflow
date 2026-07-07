from functools import lru_cache
from google.cloud import storage


class GcsInteraction:

    @lru_cache
    def _initialize_gcp_storage_client(self):
        storage_client = storage.Client()
        return storage_client

    def create_gcp_bucket(self, bucket_name):

        storage_client = self._initialize_gcp_storage_client()

        bucket = storage_client.create_bucket(bucket_name)
        return

    def gcp_bucket_exists(self, bucket_name):
        storage_client = self._initialize_gcp_storage_client()
        bucket = storage_client.lookup_bucket(bucket_name)

        return bucket is not None

    def upload_to_bucket(
        self,
        bucket_name,
        source_file_name,
        destination_blob_name,
        make_public=False,
        **kwargs,
    ):
        bucket_name = bucket_name.value if hasattr(bucket_name, "value") else bucket_name
        storage_client = self._initialize_gcp_storage_client()

        if not self.gcp_bucket_exists(bucket_name):
            self.create_gcp_bucket(bucket_name)

        bucket = storage_client.bucket(bucket_name)

        blob = bucket.blob(destination_blob_name)

        blob.upload_from_filename(source_file_name)

        if make_public:
            blob.make_public()

        print(f"File {source_file_name} uploaded to {destination_blob_name}.")
        return f"https://storage.googleapis.com/{bucket_name}/{destination_blob_name}"

    def delete_from_bucket(self, bucket_name, blob_name):
        """Delete a blob from a GCS bucket"""
        bucket_name = bucket_name.value if hasattr(bucket_name, "value") else bucket_name
        storage_client = self._initialize_gcp_storage_client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.delete()

    def download_from_bucket(self, bucket_name, blob_name, destination_file_name):
        """Download a file from GCS bucket to local filesystem"""
        bucket_name = bucket_name.value if hasattr(bucket_name, "value") else bucket_name
        storage_client = self._initialize_gcp_storage_client()

        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        blob.download_to_filename(destination_file_name)
        print(f"Downloaded {blob_name} to {destination_file_name}")
        return destination_file_name


@lru_cache
def initialize_GcsInteraction():
    return GcsInteraction()


storage_client = initialize_GcsInteraction()
