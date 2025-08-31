import json
import sys
import requests


def main():
    # Hardcoded defaults (assumes services already running)
    agent_host = "localhost"
    agent_port = 8080
    thread_id = "thread-astream"
    prompt = "Add 2 and 3, then multiply by 4"

    astream_url = f"http://{agent_host}:{agent_port}/astream"

    payload = {
        "thread_id": thread_id,
        "messages": [
            {"role": "user", "content": prompt}
        ],
    }

    try:
        with requests.post(
            astream_url,
            json=payload,
            stream=True,
            headers={"Accept": "application/x-ndjson"},
            timeout=(10, 600),  # (connect timeout, read timeout)
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    print(f"[raw] {line}")
                    continue
                etype = event.get("event")
                data = event.get("data", {})
                if etype == "status":
                    print(f"[status] {data}")
                elif etype == "message":
                    msg = data.get("message", {})
                    role = msg.get("role", "assistant")
                    content = msg.get("content", "")
                    print(f"[{role}] {content}")
                else:
                    print(f"[event] {event}")
    except requests.HTTPError as e:
        print(f"HTTP error: {e}", file=sys.stderr)
        if e.response is not None:
            print(e.response.text, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main() 