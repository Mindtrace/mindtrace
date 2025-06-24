from mindtrace.storage import GCSStorageHandler

storage = GCSStorageHandler(bucket_name="mtrix-datasets",credentials_path="/home/can/dev/creds/dl3.json")

#storage.upload("test.txt", "test.txt")


print(storage.list_objects(max_results=10))

download_files = storage.list_objects(prefix="DAGMSDD_seg/splits/test/images/",max_results=10)

to_download = []
for file in download_files:
    to_download.append((file, f"test_images/{file.split('/')[-1]}"))

print(storage.download_batch(to_download, on_error="skip"))


# storage.download(sample_img, "sample.png")
# print("create presigned url")
# print(storage.get_object_metadata(sample_img))
