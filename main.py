import asyncio
import json
import os
import sys
import tempfile
from typing import AsyncGenerator, Optional

import ytmusicapi
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from ytmusicapi import YTMusic


def resource_path(relative_path: str) -> str:
    """Resolve path to a bundled resource (PyInstaller) or local file."""
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, relative_path)


app = FastAPI()
app.mount("/static", StaticFiles(directory=resource_path("static")), name="static")

SEARCH_DELAY = 0.5
BATCH_SIZE = 50

_stop_requested: bool = False


@app.post("/stop-import")
async def stop_import_endpoint() -> JSONResponse:
    global _stop_requested
    _stop_requested = True
    print("[INFO] Stop requested by client")
    return JSONResponse({"ok": True})


async def import_stream(
    headers_raw: str,
    playlist_name: str,
    tracks: list[str],
    start_from: int = 0,
    existing_video_ids: Optional[list[str]] = None,
) -> AsyncGenerator[str, None]:
    global _stop_requested
    _stop_requested = False

    def send(data: dict) -> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    if existing_video_ids is None:
        existing_video_ids = []

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            tmp_path = f.name

        try:
            headers_raw = "\n".join(line.rstrip("\r") for line in headers_raw.splitlines())
            print(f"[INFO] Auth setup: headers={len(headers_raw)}ch, start_from={start_from}, existing={len(existing_video_ids)}")
            ytmusicapi.setup(filepath=tmp_path, headers_raw=headers_raw)
            ytmusic = YTMusic(tmp_path)
            print("[INFO] YTMusic initialized")
        except Exception as e:
            print(f"[ERROR] Auth failed: {type(e).__name__}: {e}")
            yield send({"type": "error", "message": f"Ошибка авторизации: {e}"})
            return

        remaining = tracks[start_from:]
        total = len(tracks)
        yield send({"type": "status", "message": f"Авторизация успешна. Ищем {len(remaining)} треков..."})

        video_ids: list[str] = list(existing_video_ids)
        not_found: list[str] = []

        for i, query in enumerate(remaining):
            if _stop_requested:
                print(f"[INFO] Stop at track {start_from + i + 1}/{total}, found so far: {len(video_ids)}")
                yield send({"type": "status", "message": f"Поиск остановлен. Найдено {len(video_ids)} треков."})
                break

            await asyncio.sleep(SEARCH_DELAY)
            try:
                print(f"[DEBUG] Searching {start_from + i + 1}/{total}: {query!r}")
                results = ytmusic.search(query, filter="songs", limit=1)
                if not results:
                    results = ytmusic.search(query, filter="videos", limit=1)
                if results:
                    vid = results[0].get("videoId")
                    print(f"[DEBUG]   ok -> {vid}")
                    video_ids.append(vid)
                    yield send({
                        "type": "track",
                        "status": "ok",
                        "query": query,
                        "videoId": vid,
                        "index": start_from + i + 1,
                        "total": total,
                    })
                else:
                    print(f"[DEBUG]   not found: {query!r}")
                    not_found.append(query)
                    yield send({"type": "track", "status": "skip", "query": query, "index": start_from + i + 1, "total": total})
            except Exception as e:
                print(f"[ERROR] Search error for {query!r}: {type(e).__name__}: {e}")
                not_found.append(query)
                yield send({"type": "track", "status": "skip", "query": query, "index": start_from + i + 1, "total": total})

        if not video_ids:
            yield send({"type": "error", "message": "Ни одного трека не найдено."})
            return

        yield send({"type": "status", "message": f"Создаём плейлист «{playlist_name}»..."})

        try:
            playlist_id = ytmusic.create_playlist(playlist_name, "Импортировано из Яндекс Музыки")
            print(f"[INFO] Playlist created: {playlist_id}")
        except Exception as e:
            print(f"[ERROR] Playlist creation failed: {type(e).__name__}: {e}")
            yield send({"type": "error", "message": f"Ошибка создания плейлиста: {e}"})
            return

        yield send({"type": "status", "message": f"Плейлист создан. Добавляем {len(video_ids)} треков..."})

        total_batches = -(-len(video_ids) // BATCH_SIZE)
        for i in range(0, len(video_ids), BATCH_SIZE):
            batch = video_ids[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            try:
                ytmusic.add_playlist_items(playlist_id, batch, duplicates=False)
                print(f"[INFO] Batch {batch_num}/{total_batches} added ({len(batch)} tracks)")
                yield send({"type": "batch", "current": batch_num, "total": total_batches})
            except Exception as e:
                print(f"[ERROR] Batch {batch_num} failed: {type(e).__name__}: {e}")
                yield send({"type": "error", "message": f"Ошибка батча {batch_num}: {e}"})
            await asyncio.sleep(1)

        yield send({
            "type": "done",
            "found": len(video_ids),
            "not_found": len(not_found),
            "playlist_id": playlist_id,
            "not_found_list": not_found,
        })

    finally:
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.post("/import")
async def import_tracks(
    headers_raw: str = Form(...),
    playlist_name: str = Form(...),
    file: UploadFile = File(None),
    tracks_text: str = Form(""),
    start_from: int = Form(0),
    existing_video_ids: str = Form("[]"),
):
    if file is not None:
        content = (await file.read()).decode("utf-8")
    elif tracks_text:
        content = tracks_text
    else:
        return JSONResponse({"error": "No tracks provided"}, status_code=400)

    tracks = [line.strip() for line in content.splitlines() if line.strip()]

    try:
        vid_ids: list[str] = json.loads(existing_video_ids)
    except Exception as e:
        print(f"[ERROR] Failed to parse existing_video_ids: {e}")
        vid_ids = []

    print(f"[INFO] /import: {len(tracks)} tracks, start_from={start_from}, existing={len(vid_ids)}")

    return StreamingResponse(
        import_stream(headers_raw, playlist_name, tracks, start_from, vid_ids),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/", response_class=HTMLResponse)
async def index():
    with open(resource_path("index.html"), encoding="utf-8") as f:
        return f.read()
