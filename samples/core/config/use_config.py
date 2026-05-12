from mindtrace.core.config import Config

# Step 1: Create a Config instance
# Config loads from (highest to lowest precedence):
#   1. Constructor kwargs
#   2. Environment variables (SECTION__KEY delimiter)
#   3. .env file
#   4. config.ini bundled with the package
config = Config()

# Step 2: Access values (attribute or dict-style)
print("attribute style access", config.MINDTRACE_DIR_PATHS.TEMP_DIR)
print("dict style access", config["MINDTRACE_DIR_PATHS"]["TEMP_DIR"])
print("get method", config.get("MINDTRACE_DIR_PATHS").get("TEMP_DIR"))

# Step 3: Retrieve secrets
api_key = config.get_secret("MINDTRACE_API_KEYS", "OPENAI")
print("API key:", api_key)

# Step 4: Serialize to dict (reveals secrets)
config_dict = config.model_dump()
print("Config dict:", config_dict)

# Step 5: Serialize to JSON (reveals secrets via field_serializer)
config_json = config.model_dump_json(indent=2)
print("Config JSON:", config_json)
