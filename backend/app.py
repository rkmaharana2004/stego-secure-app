from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import numpy as np
from PIL import Image
import io, uuid, hashlib, hmac, struct, os
from pathlib import Path
import uvicorn
from scipy.ndimage import convolve
from evaluator import StegoEvaluator
from ranking import AlgorithmRanker
from existing_models import (
    MSBModel, DCTJStegModel, DWTHaarModel
)

app = FastAPI(title="Adaptive Pixel Steganography with Edge Preservation for Secure Image Communication")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Ensure directories exist relative to this file's location
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
GALLERY_DIR = BASE_DIR / "gallery"
UPLOAD_DIR.mkdir(exist_ok=True)
GALLERY_DIR.mkdir(exist_ok=True)

app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
app.mount("/gallery", StaticFiles(directory=str(GALLERY_DIR)), name="gallery")

MAGIC, HEADER_SIZE, THRESHOLD = 0x53544547, 72, 50
BLUR = np.array([[1,2,1],[2,4,2],[1,2,1]], dtype=np.float32) / 16

class StegoSystem:
    def _edge_mask(self, img):
        green = img[:,:,1] & 0xFE
        gray = green.astype(np.float32)
        smooth = convolve(gray, BLUR, mode="reflect")
        sx = convolve(smooth, [[-1,0,1],[-2,0,2],[-1,0,1]], mode="reflect")
        sy = convolve(smooth, [[-1,-2,-1],[0,0,0],[1,2,1]], mode="reflect")
        return np.sqrt(sx*sx + sy*sy) > THRESHOLD

    def _permute(self, password, n):
        seed = int.from_bytes(hashlib.sha256(password.encode()).digest()[:4], "big")
        rng = np.random.RandomState(seed)
        p = list(range(n))
        for i in range(n-1,0,-1):
            j = rng.randint(0,i+1); p[i], p[j] = p[j], p[i]
        return p

    def embed(self, img, payload_bytes, password):
        edges = np.argwhere(self._edge_mask(img))
        if len(edges) == 0:
            h,w,_ = img.shape
            edges = np.array([(i,j) for i in range(h) for j in range(w)])
        header = struct.pack(">II", MAGIC, len(payload_bytes)) + \
                 hashlib.sha256(payload_bytes).digest() + \
                 hmac.new(hashlib.sha256(password.encode()).digest(), 
                          payload_bytes + hashlib.sha256(payload_bytes).digest(), 
                          hashlib.sha256).digest()
        bits = []
        for b in (header + payload_bytes):
            bits.extend((b>>i)&1 for i in range(7,-1,-1))
        if len(bits) > len(edges) * 3:
            raise ValueError("Data exceeds capacity")
        perm = self._permute(password, len(edges))
        stego = img.copy()
        k = 0
        for idx in perm:
            if k >= len(bits): break
            i,j = edges[idx]
            for c in range(3):
                if k >= len(bits): break
                stego[i,j,c] = (stego[i,j,c] & 0xFE) | bits[k]
                k += 1
        return stego

    def extract(self, img, password):
        edges = np.argwhere(self._edge_mask(img))
        perm = self._permute(password, len(edges))
        bits = []
        for idx in perm:
            i,j = edges[idx]
            for c in range(3): bits.append(img[i,j,c] & 1)
        data = []
        for i in range(0, len(bits), 8):
            if i+8 > len(bits): break
            b = 0
            for j in range(8): b = (b<<1) | bits[i+j]
            data.append(b)
        data = bytes(data)
        magic, length = struct.unpack(">II", data[:8])
        if magic != MAGIC: raise ValueError("Invalid header or key")
        return data[HEADER_SIZE:HEADER_SIZE+length]

stego_sys = StegoSystem()

@app.get("/")
async def read_index():
    return FileResponse(BASE_DIR.parent / "frontend" / "index.html")

@app.post("/api/hide")
async def hide(image: UploadFile = File(...), password: str = Form(...), message: str = Form(...)):
    try:
        cover = Image.open(io.BytesIO(await image.read())).convert("RGB")
        arr = np.array(cover)
        payload_bytes = message.encode()
        our_stego = stego_sys.embed(arr, payload_bytes, password)
        our_metrics = StegoEvaluator.calculate_all_metrics(arr, our_stego, payload_bytes)

        models = {
            "MSB (Most Significant Bit)": MSBModel,
            "DCT (JSteg)": DCTJStegModel,
            "DWT (Haar)": DWTHaarModel,
        }

        leaderboard = [{"name": "KRISHNA (Prime‑Seq)", **our_metrics, "is_ours": True, "stego_arr": our_stego}]
        for name, ModelClass in models.items():
            try:
                stego_arr = ModelClass.embed(arr, payload_bytes)
                extracted = ModelClass.extract(stego_arr, len(payload_bytes))
                metrics = StegoEvaluator.calculate_all_metrics(arr, stego_arr, payload_bytes, extracted)
                metrics["name"] = name
                metrics["is_ours"] = False
                metrics["stego_arr"] = stego_arr
                leaderboard.append(metrics)
            except Exception as e:
                print(f"{name} failed: {e}")
                leaderboard.append({"name": name, "is_ours": False, "psnr": 0, "ssim": 0, "snr": 0, "mse": 999, "capacity_bpp": 0, "fdm": 999, "epi": 0, "entropy_original": 0, "entropy_stego": 0, "sei": 0, "stego_arr": None})

        leaderboard.sort(key=lambda x: x.get("sei", 0), reverse=True)
        for i, entry in enumerate(leaderboard, 1): entry["rank"] = i

        gallery_urls = []
        for entry in leaderboard:
            if entry.get("stego_arr") is not None:
                fname = f"gallery_{entry['name'].replace(' ', '_').replace('(', '').replace(')', '')}_{uuid.uuid4().hex[:6]}.png"
                img_path = GALLERY_DIR / fname
                Image.fromarray(entry["stego_arr"]).save(img_path)
                entry["stego_url"] = f"/gallery/{fname}"
                gallery_urls.append({"name": entry["name"], "url": entry["stego_url"]})

        stego_filename = f"stego_{uuid.uuid4().hex[:8]}.png"
        Image.fromarray(our_stego).save(UPLOAD_DIR / stego_filename)

        ranking = AlgorithmRanker.rank_algorithms(leaderboard)
        best_algo, recommendation = AlgorithmRanker.get_best_algorithm(leaderboard)

        for entry in leaderboard:
            entry.pop("stego_arr", None)

        return {
            "success": True,
            "stego_url": f"/uploads/{stego_filename}",
            "metrics": our_metrics,
            "leaderboard": leaderboard,
            "gallery": gallery_urls,
            "ranking": ranking,
            "best_algorithm": best_algo,
            "recommendation": recommendation
        }
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/reveal")
async def reveal(image: UploadFile = File(...), password: str = Form(...)):
    try:
        img = Image.open(io.BytesIO(await image.read())).convert("RGB")
        payload = stego_sys.extract(np.array(img), password)
        return {"success": True, "message": payload.decode()}
    except Exception as e:
        raise HTTPException(400, str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)