import io
import wave


def synthetic_wav():
    b=io.BytesIO()
    with wave.open(b,'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(b'\x00\x01'*16000)
    return b.getvalue()
