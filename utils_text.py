import re
from io import BytesIO

def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()

def strip_accents(s: str) -> str:
    try:
        import unicodedata
        return "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")
    except Exception:
        return s

def normalize_answer(s: str) -> str:
    s = (s or "").strip().lower()
    s = strip_accents(s)
    s = re.sub(r"[^\w\s\-]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def split_sentences(text: str):
    text = normalize_ws(text)
    if not text:
        return []
    parts = re.split(r"(?<=[\.\!\?;:])\s+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 40]

def extract_text_from_upload(uploaded_file) -> str:
    """Supports: txt, md, pdf, docx"""
    name = (uploaded_file.name or "").lower()
    data = uploaded_file.getvalue()

    if name.endswith(".txt") or name.endswith(".md"):
        try:
            return data.decode("utf-8")
        except Exception:
            return data.decode("latin-1", errors="ignore")

    if name.endswith(".docx"):
        from docx import Document
        bio = BytesIO(data)
        doc = Document(bio)
        paras = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
        return "\n".join(paras)

    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except Exception:
            from PyPDF2 import PdfReader
        bio = BytesIO(data)
        reader = PdfReader(bio)
        texts = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                texts.append(t)
        return "\n".join(texts)

    try:
        return data.decode("utf-8")
    except Exception:
        return data.decode("latin-1", errors="ignore")

def split_into_sections(text: str, mode: str = "artigos", max_chars: int = 6000):
    """Return list of (title, chunk_text)"""
    text = (text or "").strip()
    if not text:
        return []

    if mode == "tamanho":
        chunks = []
        i = 0
        k = 1
        while i < len(text):
            chunk = text[i:i+max_chars].strip()
            if chunk:
                chunks.append((f"Parte {k}", chunk))
                k += 1
            i += max_chars
        return chunks

    markers = list(re.finditer(r"\b(Art\.|Artigo)\s*\d+[A-Za-z\-]*\b", text))
    if len(markers) < 2:
        return split_into_sections(text, mode="tamanho", max_chars=max_chars)

    chunks = []
    for idx, m in enumerate(markers):
        start = m.start()
        end = markers[idx+1].start() if idx+1 < len(markers) else len(text)
        title = text[m.start(): min(m.start()+40, len(text))].splitlines()[0].strip()
        chunk = text[start:end].strip()
        if chunk:
            chunks.append((title[:60], chunk))
    return chunks
