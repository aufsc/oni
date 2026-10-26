from http.server import HTTPServer, SimpleHTTPRequestHandler
import os

PORT = 5000
DIRECTORY = "dist"

class BlogHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

if __name__ == "__main__":
    if not os.path.exists(DIRECTORY):
        print(f"❌ '{DIRECTORY}' not found. Run 'python build.py' first.")
    else:
        with HTTPServer(("", PORT), BlogHandler) as httpd:
            print(f"🚀 Server running at http://localhost:{PORT}")
            httpd.serve_forever()