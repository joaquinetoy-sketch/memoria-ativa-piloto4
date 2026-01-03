import json
import hashlib
from datetime import datetime
from difflib import SequenceMatcher

import streamlit as st

import db
import cloze
from sr import ScheduleState, update as sr_update
from utils_text import extract_text_from_upload, normalize_answer, split_into_sections

APP_NAME = "Memória Ativa — Piloto 4"

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def ensure_state():
    defaults = {
        "user": None,
        "page": "Hoje",
        "current_card": None,
        "checked": False,
        "ans_input": "",
        "goal": 20,
        "_last_correct": False,
        "_last_missing": [],
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

def login_ui():
    st.subheader("Entrar")
    u = st.text_input("Usuário", key="login_user")
    p = st.text_input("Senha", type="password", key="login_pw")
    if st.button("Entrar", type="primary"):
        user = db.get_user(u.strip())
        if not user:
            st.error("Usuário não encontrado.")
            return
        if user["password_hash"] != hash_pw(p):
            st.error("Senha incorreta.")
            return
        st.session_state.user = user
        st.success("Login realizado!")
        st.rerun()

    st.divider()
    st.subheader("Criar conta")
    nu = st.text_input("Novo usuário", key="new_user")
    npw = st.text_input("Nova senha", type="password", key="new_pw")
    if st.button("Criar conta"):
        ok = db.create_user(nu.strip(), hash_pw(npw))
        st.success("Conta criada. Agora faça login.") if ok else st.error("Esse usuário já existe. Tente outro.")

def sidebar_nav():
    st.sidebar.title(APP_NAME)
    st.sidebar.caption("Hoje • Revisar • Variantes aceitas • Decks por partes")

    stats = db.stats(st.session_state.user["id"])
    st.sidebar.metric("Para revisar agora", int(stats["due_now"]))
    st.sidebar.metric("Cards", int(stats["cards"]))
    st.sidebar.metric("Acerto médio", f"{float(stats['avg_correct'])*100:.0f}%")

    st.session_state.goal = st.sidebar.slider("Meta de hoje (cards)", 5, 100, int(st.session_state.goal), step=5)

    page = st.sidebar.radio(
        "Navegação",
        ["Hoje", "Revisar", "Criar deck", "Meus decks", "Importar/Exportar", "Progresso"],
        index=["Hoje", "Revisar", "Criar deck", "Meus decks", "Importar/Exportar", "Progresso"].index(st.session_state.page)
    )
    st.session_state.page = page

    if st.sidebar.button("Sair"):
        st.session_state.user = None
        st.session_state.current_card = None
        st.rerun()

def fuzzy_match(expected: str, provided: str) -> bool:
    e = normalize_answer(expected)
    p = normalize_answer(provided)
    if not e or not p:
        return False
    if e in p:
        return True
    return SequenceMatcher(None, e, p).ratio() >= 0.82

def check_answer(answers, variants_map, user_answer: str):
    got = [g.strip() for g in (user_answer or "").split(",") if g.strip()]
    if not got:
        return False, answers
    missing = []
    for a in answers:
        variants = variants_map.get(a, []) if isinstance(variants_map, dict) else []
        pool = [a] + list(variants)
        ok = any(any(fuzzy_match(v, g) for g in got) for v in pool)
        if not ok:
            missing.append(a)
    return len(missing) == 0, missing

def add_variant(card_id: int, expected: str, new_variant: str):
    card = db.get_card(card_id)
    variants = json.loads(card.get("variants_json","{}") or "{}")
    variants.setdefault(expected, [])
    nv_norm = normalize_answer(new_variant)
    if nv_norm and nv_norm not in [normalize_answer(x) for x in variants[expected]]:
        variants[expected].append(new_variant.strip())
        db.update_variants(card_id, variants)

def page_today():
    st.header("Hoje")
    st.caption("Revisões por deck (agora/hoje). Sem planilha.")

    rows = db.get_due_today_by_deck(st.session_state.user["id"])
    due_now_total = sum(int(r.get("due_now",0) or 0) for r in rows)
    st.metric("Revisões pendentes agora", due_now_total)

    st.write("**Por deck:**")
    shown = 0
    for r in rows:
        now = int(r.get("due_now",0) or 0)
        today = int(r.get("due_today",0) or 0)
        if now == 0 and today == 0:
            continue
        st.write(f"• **{r['deck_name']}** — agora: **{now}** | hoje: **{today}**")
        shown += 1
    if shown == 0:
        st.success("Nada pendente hoje 🎉")

    st.divider()
    st.info("Meta de hoje: faça seus cards e o sistema naturalmente espaça as revisões para reduzir volume.")

def page_review():
    st.header("Revisar")
    st.caption("Se a resposta estiver certa mas diferente, você pode salvar uma variação (o app aprende seu jeito).")

    limit = st.slider("Quantidade nesta sessão", 5, 120, int(st.session_state.goal), step=5)
    due = db.get_due_cards(st.session_state.user["id"], limit=limit)
    if not due:
        st.success("Nada para revisar agora 🎉")
        return

    if st.session_state.current_card is None:
        st.session_state.current_card = due[0]["id"]
        st.session_state.checked = False

    card = db.get_card(st.session_state.current_card)
    if not card:
        st.session_state.current_card = None
        st.rerun()

    answers = json.loads(card["answers_json"])
    variants_map = json.loads(card.get("variants_json","{}") or "{}")

    st.markdown(f"**Deck:** {card['deck_name']}")
    st.markdown(f"**Venceu em:** {datetime.fromisoformat(card['due_date']).strftime('%d/%m/%Y %H:%M')}")
    st.write(card["prompt"])

   input_key = f"ans_input_{card['id']}"

user_answer = st.text_input(
    "Sua resposta (se houver mais de uma lacuna, separe por vírgula):",
    key=input_key
)

    c1, c2 = st.columns([1,1])
    with c1:
        if st.button("Conferir", type="primary"):
            correct, missing = check_answer(answers, variants_map, user_answer)
            st.session_state.checked = True
            st.session_state._last_correct = correct
            st.session_state._last_missing = missing
    with c2:
        if st.button("Pular", use_container_width=True):
            state = ScheduleState(
                due_date=datetime.fromisoformat(card["due_date"]),
                interval_days=float(card["interval_days"]),
                ease=float(card["ease"]),
                reps=int(card["reps"]),
                lapses=int(card["lapses"]),
            )
            new_state = sr_update(state, "hard")
            db.update_schedule(card["id"], new_state.due_date.isoformat(), new_state.interval_days, new_state.ease, new_state.reps, new_state.lapses)
            st.session_state.current_card = None
            st.session_state.checked = False
            st.session_state.pop(input_key, None)
            st.rerun()

    if st.session_state.checked:
        if st.session_state._last_correct:
            st.success(f"Acertou ✅ Resposta esperada: {', '.join(answers)}")
        else:
            st.error(f"Errou ❌ Faltou: {', '.join(st.session_state._last_missing)}")
            st.write("**Frase original (para consolidar):**")
            st.write(card["original"])
            st.write(f"**Este exercício treina:** {', '.join(answers)}")

            st.markdown("**Sua resposta estava certa, só em outra forma?**")
            ex = st.selectbox("Qual termo você quer ensinar uma variação?", st.session_state._last_missing)
            nv = st.text_input("Digite a variação aceita", placeholder="Ex.: Administração Pública / Admin Pública")
            if st.button("Salvar variação e marcar como correto"):
                if nv.strip():
                    add_variant(card["id"], ex, nv.strip())
                    st.info("Variação salva ✅")
                    st.session_state._last_correct = True

        st.markdown("**Como foi?** (define o próximo intervalo)")
        r1, r2, r3, r4 = st.columns(4)

        def apply_rating(rating: str):
            correct = bool(st.session_state._last_correct)
            state = ScheduleState(
                due_date=datetime.fromisoformat(card["due_date"]),
                interval_days=float(card["interval_days"]),
                ease=float(card["ease"]),
                reps=int(card["reps"]),
                lapses=int(card["lapses"]),
            )
            new_state = sr_update(state, rating)
            db.add_review(card["id"], rating, correct, user_answer)
            db.update_schedule(card["id"], new_state.due_date.isoformat(), new_state.interval_days, new_state.ease, new_state.reps, new_state.lapses)

            st.session_state.checked = False
            st.session_state.pop(input_key, None)
            new_due = db.get_due_cards(st.session_state.user["id"], limit=limit)
            st.session_state.current_card = new_due[0]["id"] if new_due else None
            st.rerun()
        with r1:
            if st.button("De novo", use_container_width=True):
                apply_rating("again")
        with r2:
            if st.button("Difícil", use_container_width=True):
                apply_rating("hard")
        with r3:
            if st.button("Bom", use_container_width=True):
                apply_rating("good")
        with r4:
            if st.button("Fácil", use_container_width=True):
                apply_rating("easy")

def page_create_deck():
    st.header("Criar deck")
    st.caption("Cole texto ou envie arquivo. Opcional: criar vários decks por artigos ou por blocos.")

    base_name = st.text_input("Nome base do deck", value=f"Deck {datetime.now().strftime('%d/%m %H:%M')}")
    difficulty = st.selectbox("Nível", ["Fácil", "Médio", "Difícil"], index=1)
    max_cards = st.slider("Lacunas por deck", 10, 160, 40, step=5)

    tab1, tab2 = st.tabs(["Colar texto", "Enviar arquivo"])
    text = ""
    with tab1:
        text = st.text_area("Cole o conteúdo", height=240)
    with tab2:
        up = st.file_uploader("PDF/DOCX/TXT/MD (PDF pesquisável)", type=["pdf","docx","txt","md"])
        if up is not None:
            extracted = extract_text_from_upload(up)
            st.success(f"Texto extraído: {len(extracted)} caracteres")
            st.text_area("Prévia (recorte se quiser)", value=extracted[:6000], height=180)
            text = extracted

    st.markdown("### Dividir em vários decks (opcional)")
    mode = st.selectbox("Dividir por", ["Não dividir (um deck)", "Artigos (Art. 1, Art. 2...)", "Por tamanho (blocos)"])
    max_chars = st.slider("Tamanho do bloco (se usar blocos)", 2000, 12000, 6000, step=500)

    if st.button("Gerar e salvar", type="primary"):
        content = (text or "").strip()
        if len(content) < 400:
            st.error("Conteúdo muito curto. Use alguns parágrafos.")
            return

        sections = [("Conteúdo", content)]
        if mode == "Artigos (Art. 1, Art. 2...)":
            sections = split_into_sections(content, mode="artigos", max_chars=max_chars)
        elif mode == "Por tamanho (blocos)":
            sections = split_into_sections(content, mode="tamanho", max_chars=max_chars)

        created = 0
        for title, chunk in sections:
            deck_name = base_name.strip()
            if mode != "Não dividir (um deck)":
                deck_name = f"{deck_name} — {title}"
            deck_id = db.create_deck(st.session_state.user["id"], deck_name)
            cards = cloze.build_deck(chunk, difficulty, max_cards)
            if not cards:
                continue
            now = datetime.now().isoformat()
            for c in cards:
                cid = db.add_card(deck_id, c["prompt"], c["answers"], c.get("variants", {}), c["original"])
                db.init_schedule(cid, due_date_iso=now, interval_days=0.0, ease=2.2, reps=0, lapses=0)
            created += 1

        if created == 0:
            st.warning("Não consegui gerar lacunas com esse conteúdo. Tente um texto mais conceitual.")
            return

        st.success(f"Criei {created} deck(s). Vá em **Revisar** para começar.")
        st.session_state.page = "Revisar"
        st.session_state.current_card = None
        st.rerun()

def page_decks():
    st.header("Meus decks")
    decks = db.list_decks(st.session_state.user["id"])
    if not decks:
        st.info("Você ainda não tem decks.")
        return
    for d in decks:
        with st.expander(f"{d['name']} • {d['cards_count']} cards • agora: {int(d.get('due_now',0) or 0)}"):
            if st.button("Excluir deck", key=f"del_{d['id']}"):
                ok = db.delete_deck(st.session_state.user["id"], d["id"])
                st.success("Deck excluído.") if ok else st.error("Não foi possível excluir.")
                st.rerun()

def page_import_export():
    st.header("Importar / Exportar")
    decks = db.list_decks(st.session_state.user["id"])
    if decks:
        deck_id = st.selectbox("Exportar deck", [d["id"] for d in decks], format_func=lambda x: next(dd["name"] for dd in decks if dd["id"]==x))
        if st.button("Gerar exportação"):
            payload = db.export_deck(st.session_state.user["id"], int(deck_id))
            if payload:
                data = json.dumps(payload, ensure_ascii=False, indent=2)
                st.download_button("Baixar JSON", data=data, file_name=f"deck_{deck_id}.json", mime="application/json")

    st.divider()
    st.subheader("Importar deck (JSON)")
    up = st.file_uploader("Arquivo JSON", type=["json"])
    if up is not None:
        payload = json.loads(up.getvalue().decode("utf-8"))
        if st.button("Importar agora", type="primary"):
            new_id = db.import_deck(st.session_state.user["id"], payload)
            st.success(f"Importado! Novo deck id: {new_id}")
            st.rerun()

def page_progress():
    st.header("Progresso")
    s = db.stats(st.session_state.user["id"])
    st.metric("Decks", int(s["decks"]))
    st.metric("Cards", int(s["cards"]))
    st.metric("Revisões feitas", int(s["reviews"]))
    st.metric("Para revisar agora", int(s["due_now"]))
    st.metric("Acerto médio", f"{float(s['avg_correct'])*100:.0f}%")
    st.info("Piloto 4: o app aprende variantes. Próximo passo: sinônimos e explicações com IA.")

def main():
    st.set_page_config(page_title=APP_NAME, layout="wide")
    db.init_db()
    ensure_state()

    if st.session_state.user is None:
        st.title(APP_NAME)
        st.caption("Piloto 4: hoje por deck + revisão mais humana + variantes aceitas + decks por partes.")
        login_ui()
        return

    sidebar_nav()

    if st.session_state.page == "Hoje":
        page_today()
    elif st.session_state.page == "Revisar":
        page_review()
    elif st.session_state.page == "Criar deck":
        page_create_deck()
    elif st.session_state.page == "Meus decks":
        page_decks()
    elif st.session_state.page == "Importar/Exportar":
        page_import_export()
    else:
        page_progress()

if __name__ == "__main__":
    main()
