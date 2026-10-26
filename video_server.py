import os
import sys
import signal
import socket
from socketserver import ThreadingMixIn
from http.server import HTTPServer, BaseHTTPRequestHandler

if len(sys.argv) < 3:
    print("Uso: python3 video_server.py <puerto> <ruta_al_video>")
    sys.exit(1)

PORT = int(sys.argv[1])
VIDEO_FILE = sys.argv[2]

if not os.path.exists(VIDEO_FILE):
    print(f"Error: {VIDEO_FILE} no existe")
    sys.exit(1)

class VideoStreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        try:
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
            self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 * 1024 * 1024)
        except Exception:
            pass

    def log_message(self, format, *args):
        pass

    def do_HEAD(self):
        try:
            size = os.path.getsize(VIDEO_FILE)
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Connection", "keep-alive")
            self.send_header("Keep-Alive", "timeout=60, max=100")
            self.send_header("Content-Length", str(size))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
        except Exception:
            self.send_error(500)

    def do_GET(self):
        try:
            file_size = os.path.getsize(VIDEO_FILE)
            range_header = self.headers.get("Range")

            if range_header:
                bytes_range = range_header.strip().split("=")[-1]
                start_str, _, end_str = bytes_range.partition("-")
                start = int(start_str) if start_str else 0
                end = int(end_str) if end_str else file_size - 1
                if end >= file_size:
                    end = file_size - 1
                content_length = end - start + 1

                self.send_response(206)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Content-Length", str(content_length))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Connection", "keep-alive")
                self.send_header("Keep-Alive", "timeout=60, max=100")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                with open(VIDEO_FILE, "rb") as f:
                    f.seek(start)
                    remaining = content_length
                    chunk_size = 1024 * 1024  # 1 MB para maximizar rendimiento
                    while remaining > 0:
                        read_bytes = min(remaining, chunk_size)
                        chunk = f.read(read_bytes)
                        if not chunk:
                            break
                        self.connection.sendall(chunk)
                        remaining -= len(chunk)
            else:
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(file_size))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Connection", "keep-alive")
                self.send_header("Keep-Alive", "timeout=60, max=100")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                with open(VIDEO_FILE, "rb") as f:
                    chunk_size = 1024 * 1024
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        self.connection.sendall(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            pass

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

def run():
    server = ThreadedHTTPServer(("0.0.0.0", PORT), VideoStreamHandler)
    def stop_handler(signum, frame):
        server.server_close()
        sys.exit(0)
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    print(f"Streaming {VIDEO_FILE} en puerto {PORT}")
    server.serve_forever()

if __name__ == "__main__":
    run()
