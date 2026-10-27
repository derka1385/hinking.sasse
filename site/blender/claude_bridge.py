# Claude bridge — run once per Blender session (Scripting tab > Open > Run Script).
# Listens on 127.0.0.1:8977 only (this Mac). Each connection sends Python, which runs on Blender's
# main thread; the reply is what it printed, or the traceback. Stop it by quitting Blender.
import contextlib
import io
import queue
import socket
import threading
import traceback

import bpy

HOST, PORT = "127.0.0.1", 8977
jobs = queue.Queue()
env = {"bpy": bpy, "__name__": "__claude__"}   # shared between calls, so variables persist


def serve(srv):
    while True:
        conn, _ = srv.accept()
        data = b""
        while chunk := conn.recv(65536):
            data += chunk
        box, done = {}, threading.Event()
        jobs.put((data.decode(), box, done))
        done.wait(300)
        conn.sendall(box.get("out", "timed out after 300 s").encode())
        conn.close()


def pump():
    while not jobs.empty():
        code, box, done = jobs.get()
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                exec(code, env)
        except Exception:
            out.write(traceback.format_exc())
        box["out"] = out.getvalue()
        done.set()
    return 0.1


try:
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(1)
    threading.Thread(target=serve, args=(srv,), daemon=True).start()
    bpy.app.timers.register(pump, persistent=True)
    print(f"Claude bridge listening on {HOST}:{PORT}")
except OSError:
    print("Claude bridge already running")
