import re
import unicodedata
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Explorador de Correspondência", layout="wide")

# ---------- Helpers ----------
def normalize_text(s) -> str:
    if s is None or pd.isna(s):
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()

def normalize_key(s) -> str:
    s = normalize_text(s).lower()
    s = "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )
    return s

def safe_str(x):
    return normalize_text(x)

def contains_query(row_text: str, q: str) -> bool:
    return normalize_key(q) in normalize_key(row_text)

def build_search_blob(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    blob = pd.Series([""] * len(df), index=df.index)
    for c in cols:
        if c in df.columns:
            blob = blob + " | " + df[c].fillna("").astype(str)
    return blob

def make_filter_options(df: pd.DataFrame, colname: str):
    if colname not in df.columns:
        return []

    raw_vals = df[colname].fillna("").astype(str).map(normalize_text)
    vals = [v for v in raw_vals.unique() if v]

    # remove duplicados por versão normalizada, mantendo um rótulo legível
    dedup = {}
    for v in vals:
        key = normalize_key(v)
        if key and key not in dedup:
            dedup[key] = v

    return sorted(dedup.values(), key=normalize_key)

def multiselect_filter(label, colname):
    options = make_filter_options(df, colname)
    if not options:
        return []
    return st.sidebar.multiselect(label, options=options)

def apply_in_filter(df_in, col, selected):
    if col not in df_in.columns or not selected:
        return df_in

    selected_keys = {normalize_key(v) for v in selected if normalize_key(v)}

    if not selected_keys:
        return df_in

    col_keys = df_in[col].fillna("").astype(str).map(normalize_key)
    return df_in[col_keys.isin(selected_keys)]

# ---------- UI ----------
st.title("📁 Explorador de Correspondência (CSV)")
st.caption("Carrega um CSV, filtra e pesquisa, seleciona um registo e vê a ficha completa.")

uploaded = st.file_uploader("Carregar CSV", type=["csv"])

if not uploaded:
    st.info("⬆️ Carrega o CSV para começar.")
    st.stop()

# ---------- Load ----------
try:
    df = pd.read_csv(uploaded)
except Exception:
    df = pd.read_csv(uploaded, encoding="utf-8", sep=",")

df.columns = [normalize_text(c) for c in df.columns]

if "Ano" in df.columns:
    df["Ano"] = pd.to_numeric(df["Ano"], errors="coerce")

# ---------- Sidebar Filters ----------
st.sidebar.header("🔎 Filtros")

query = st.sidebar.text_input(
    "Pesquisa livre (ex: “Madeira”, “instituições”, “Eurico”, “Porto”)",
    value=""
).strip()

year_min = year_max = None
if "Ano" in df.columns and df["Ano"].notna().any():
    y_min = int(df["Ano"].dropna().min())
    y_max = int(df["Ano"].dropna().max())

    if y_min == y_max:
        st.sidebar.write(f"Ano: **{y_min}**")
        year_min, year_max = y_min, y_max
    else:
        year_min, year_max = st.sidebar.slider(
            "Intervalo de anos",
            y_min,
            y_max,
            (y_min, y_max)
        )

sel_tema = multiselect_filter("Tema", "Tema")
sel_tipologia = multiselect_filter("Tipologia", "Tipologia")
sel_remetente = multiselect_filter("Remetente", "Remetente")
sel_destinatario = multiselect_filter("Destinatário", "Destinatário")
sel_morada_rem = multiselect_filter("Morada do Remetente", "Morada do Remetente")
sel_morada_dest = multiselect_filter("Morada do Destinatário", "Morada do Destinatário")

# ---------- Apply Filters ----------
filtered = df.copy()

if year_min is not None and "Ano" in filtered.columns:
    filtered = filtered[
        (filtered["Ano"].isna()) |
        ((filtered["Ano"] >= year_min) & (filtered["Ano"] <= year_max))
    ]

filtered = apply_in_filter(filtered, "Tema", sel_tema)
filtered = apply_in_filter(filtered, "Tipologia", sel_tipologia)
filtered = apply_in_filter(filtered, "Remetente", sel_remetente)
filtered = apply_in_filter(filtered, "Destinatário", sel_destinatario)
filtered = apply_in_filter(filtered, "Morada do Remetente", sel_morada_rem)
filtered = apply_in_filter(filtered, "Morada do Destinatário", sel_morada_dest)

search_cols = [
    "Cota", "Data", "Ano", "Remetente", "Morada do Remetente",
    "Destinatário", "Morada do Destinatário",
    "Tipologia", "Âmbito da correspondência", "Tema",
    "Resumo do conteúdo",
    "Figuras musicais /culturais mencionadas", "Repertório mencionado",
    "Documentos anexos", "Observações"
]

if query:
    blob = build_search_blob(filtered, search_cols)
    mask = blob.apply(lambda t: contains_query(t, query))
    filtered = filtered[mask]

# ---------- Layout ----------
left, right = st.columns([1.15, 1])

selected_row_id = None

with left:
    st.subheader("📋 Resultados")
    st.write(f"Registos encontrados: **{len(filtered)}**")

    list_cols = [
        c for c in ["Cota", "Data", "Ano", "Remetente", "Destinatário", "Tema", "Tipologia"]
        if c in filtered.columns
    ]

    view = filtered[list_cols].copy() if list_cols else filtered.copy()

    sort_cols = [c for c in ["Ano", "Cota"] if c in view.columns]
    if sort_cols and not view.empty:
        view = view.sort_values(sort_cols, ascending=True, na_position="last")

    view = view.reset_index(drop=False).rename(columns={"index": "_row_id"})

    if view.empty:
        st.warning("Nenhum registo encontrado com os filtros atuais.")
    else:
        sel = st.dataframe(
            view,
            use_container_width=True,
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun",
            key="table"
        )

        if isinstance(sel, dict):
            rows = sel.get("selection", {}).get("rows", [])

            if rows:
                row_pos = rows[0]

                # Evita IndexError se a seleção antiga já não existir após novos filtros
                if isinstance(row_pos, int) and 0 <= row_pos < len(view):
                    selected_row_id = view.iloc[row_pos].get("_row_id")

                    if pd.notna(selected_row_id):
                        selected_row_id = int(selected_row_id)
                else:
                    selected_row_id = None

with right:
    st.subheader("🗂️ Ficha do registo")

    if selected_row_id is None:
        st.info("Seleciona um registo na tabela para ver a ficha completa.")
    elif selected_row_id not in df.index:
        st.warning("O registo selecionado já não está disponível. Ajusta os filtros ou seleciona outra linha.")
    else:
        row = df.loc[selected_row_id]

        title_bits = []
        if "Cota" in df.columns:
            cota = safe_str(row.get("Cota"))
            if cota:
                title_bits.append(f"Cota {cota}")

        if "Ano" in df.columns and pd.notna(row.get("Ano")):
            title_bits.append(f"{int(row.get('Ano'))}")

        st.markdown(f"### {' · '.join(title_bits) if title_bits else 'Registo selecionado'}")

        a, b = st.columns(2)

        with a:
            st.markdown("**Identificação**")
            if "Data" in df.columns:
                st.write("📅 **Data:**", safe_str(row.get("Data")) or "—")
            if "Tipologia" in df.columns:
                st.write("📄 **Tipologia:**", safe_str(row.get("Tipologia")) or "—")
            if "Formato" in df.columns:
                st.write("📐 **Formato:**", safe_str(row.get("Formato")) or "—")
            if "Dimensão (N.º de páginas)" in df.columns:
                st.write("📑 **Dimensão:**", safe_str(row.get("Dimensão (N.º de páginas)")) or "—")
            if "Âmbito da correspondência" in df.columns:
                st.write("🏷️ **Âmbito:**", safe_str(row.get("Âmbito da correspondência")) or "—")
            if "Tema" in df.columns:
                st.write("🧭 **Tema:**", safe_str(row.get("Tema")) or "—")

        with b:
            st.markdown("**Intervenientes & Locais**")
            if "Remetente" in df.columns:
                st.write("✉️ **Remetente:**", safe_str(row.get("Remetente")) or "—")
            if "Morada do Remetente" in df.columns:
                st.write("📍 **Morada (Remetente):**", safe_str(row.get("Morada do Remetente")) or "—")
            if "Destinatário" in df.columns:
                st.write("📨 **Destinatário:**", safe_str(row.get("Destinatário")) or "—")
            if "Morada do Destinatário" in df.columns:
                st.write("📍 **Morada (Destinatário):**", safe_str(row.get("Morada do Destinatário")) or "—")

        st.divider()

        if "Resumo do conteúdo" in df.columns:
            st.markdown("**Resumo do conteúdo**")
            st.write(safe_str(row.get("Resumo do conteúdo")) or "—")

        with st.expander("🎼 Referências musicais / culturais", expanded=False):
            if "Figuras musicais /culturais mencionadas" in df.columns:
                st.write(
                    "👥 **Figuras mencionadas:**",
                    safe_str(row.get("Figuras musicais /culturais mencionadas")) or "—"
                )
            if "Repertório mencionado" in df.columns:
                st.write(
                    "🎵 **Repertório mencionado:**",
                    safe_str(row.get("Repertório mencionado")) or "—"
                )

        with st.expander("📎 Anexos & Observações", expanded=False):
            if "Documentos anexos" in df.columns:
                st.write("📎 **Documentos anexos:**", safe_str(row.get("Documentos anexos")) or "—")
            if "Observações" in df.columns:
                st.write("📝 **Observações:**", safe_str(row.get("Observações")) or "—")

        with st.expander("🧾 Ver todos os campos (raw)", expanded=False):
            st.dataframe(row.to_frame("valor"), use_container_width=True)

st.caption("Dica: começa por filtros amplos (Ano/Tema) e depois usa a pesquisa livre para refinar.")