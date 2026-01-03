import re
import random
from utils_text import split_sentences, normalize_answer, strip_accents

STOPWORDS = set("""
a o os as um uma uns umas de da do das dos e em no na nos nas por para com sem
que se ao aos à às como mais menos muito pouco já ainda também porque porém
entre sobre até após antes desde quando onde qual quais quem cujo cuja cujos cujas
ser estar ter haver foi são era eram
""".split())

SIGNALS = [
    "desde que", "salvo", "exceto", "independentemente", "conforme", "nos termos",
    "vedado", "proibido", "deverá", "deve", "pode", "não", "nao",
    "requisitos", "condições", "condicoes", "hipóteses", "hipoteses",
    "prazo", "competência", "competencia"
]

# small expandable synonym list for pilot
SYN_MAP = {
    "administracao": ["administração pública", "admin publica", "adm pública", "adm publica"],
    "servidor": ["agente público", "agente publico"],
    "requisitos": ["condições", "condicoes"],
}

def pick_candidates(sentence: str):
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9\-]+", sentence)
    cands = []
    for w in words:
        wl = w.lower()
        if wl in STOPWORDS:
            continue
        if len(w) >= 6:
            cands.append(w)
    seen = set()
    out = []
    for w in cands:
        lw = w.lower()
        if lw not in seen:
            out.append(w)
            seen.add(lw)
    return out

def score_sentence(sentence: str) -> int:
    s = sentence.lower()
    score = 0
    for sig in SIGNALS:
        if sig in s:
            score += 2
    for k in ["quando", "desde", "salvo", "exceto", "independentemente", "se ", "desde que", "nos termos"]:
        if k in s:
            score += 1
    if ":" in sentence or ";" in sentence:
        score += 1
    return score

def generate_variants(answer: str):
    variants = set()
    a = (answer or "").strip()
    if not a:
        return []
    variants.add(a)
    variants.add(a.lower())
    variants.add(strip_accents(a).lower())
    na = normalize_answer(a)
    variants.add(na)

    # basic plural/singular tweak
    if na.endswith("s") and len(na) > 4:
        variants.add(na[:-1])
    else:
        variants.add(na + "s")

    if na in SYN_MAP:
        for s in SYN_MAP[na]:
            variants.add(s)
            variants.add(normalize_answer(s))

    variants.add(na.replace("-", " "))
    return sorted(v for v in variants if v)

def make_cloze(sentence: str, difficulty: str):
    cands = pick_candidates(sentence)
    if not cands:
        return None

    if difficulty == "Fácil":
        n = 1
    elif difficulty == "Médio":
        n = 2
    else:
        n = 3
    n = min(n, len(cands))

    def cand_score(w):
        s = min(len(w), 14)
        if w.isupper(): s += 4
        if w.istitle(): s += 2
        if any(ch.isdigit() for ch in w): s += 1
        return s

    pool = sorted(cands, key=cand_score, reverse=True)[: min(len(cands), 14)]
    chosen = random.sample(pool, k=n)

    cloze = sentence
    answers = []
    variants = {}
    for w in chosen:
        pattern = r"\b" + re.escape(w) + r"\b"
        if re.search(pattern, cloze):
            cloze = re.sub(pattern, "_____", cloze, count=1)
            answers.append(w)
            variants[w] = generate_variants(w)

    if "_____" not in cloze:
        return None

    return {"prompt": cloze, "answers": answers, "original": sentence, "variants": variants}

def build_deck(text: str, difficulty: str, max_cards: int):
    sents = split_sentences(text)
    if not sents:
        return []
    ranked = sorted(sents, key=score_sentence, reverse=True)
    band = ranked[: min(len(ranked), max(80, max_cards * 5))]
    random.shuffle(band)

    cards = []
    for s in band:
        item = make_cloze(s, difficulty)
        if item:
            cards.append(item)
        if len(cards) >= max_cards:
            break
    return cards
