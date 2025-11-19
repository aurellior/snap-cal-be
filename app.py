import os
import json
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from google import genai
from google.genai import types

from prompts import SYSTEM_PROMPT

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY belum diset di .env")

client = genai.Client(api_key=api_key)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_MODEL = "gemini-2.5-flash"
FALLBACK_MODEL = "gemini-2.0-flash"


def run_generation(model, image_bytes, file):
    return client.models.generate_content(
        model=model,
        contents=[
            "Analisis makanan pada gambar ini dan kembalikan HASIL "
            "hanya dalam JSON sesuai format yang sudah dijelaskan.",
            types.Part.from_bytes(
                data=image_bytes,
                mime_type=file.content_type or "image/jpeg",
            ),
        ],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0,
            response_mime_type="application/json",
        ),
    )


@app.post("/analyze-image")
async def analyze_image(file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File harus berupa gambar")

    image_bytes = await file.read()

    try:
        # 🟧 STEP 1 — Coba pakai model utama 2.5-flash
        try:
            response = run_generation(DEFAULT_MODEL, image_bytes, file)
        except Exception as e:
            err = str(e)

            # Jika error terkait overload / unavailable → fallback
            if "503" in err or "UNAVAILABLE" in err or "overloaded" in err:
                try:
                    response = run_generation(FALLBACK_MODEL, image_bytes, file)
                except Exception as e2:
                    raise HTTPException(
                        status_code=503,
                        detail=f"Model utama & fallback keduanya gagal: {str(e2)}"
                    )
            else:
                raise

        raw_text = response.text.strip()

        # 🟦 Parse ke JSON
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=500,
                detail="Output model bukan JSON valid. Coba perbaiki prompt atau coba lagi.",
            )

        return data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
