import io, json, os, re, time, datetime
import numpy as np
import pandas as pd, requests, yfinance as yf

TAGE = 20  # abrufbare Stichtage
OUT = "data_alle"
UA = {"User-Agent": "Mozilla/5.0 (compatible; rsl-dashboard)"}
SEC = {"Health Care": "Healthcare", "Information Technology": "Technology", "Communication": "Communication Services",
       "IT": "Technology", "Finanzwesen": "Financials", "Gesundheitsversorgung": "Healthcare", "Industrie": "Industrials",
       "Nichtzyklische Konsumgüter": "Consumer Staples", "Zyklische Konsumgüter": "Consumer Discretionary", "Energie": "Energy",
       "Materialien": "Materials", "Versorger": "Utilities", "Kommunikation": "Communication Services", "Immobilien": "Real Estate"}
URL_SP = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
URL_NDX = "https://en.wikipedia.org/wiki/Nasdaq-100"
URL_DOW = "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average"
URL_DAX = "https://en.wikipedia.org/wiki/DAX"
# iShares-Bestandslisten (ETF-Holdings als Ersatz fuer die Index-Mitglieder)
URLS_RUSSELL = [
    "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/latest-holdings.csv",
    "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund",
    "https://www.ishares.com/ch/professionelle-anleger/de/produkte/239710/ishares-russell-2000-etf/1495092304805.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund",
]
URLS_STOXX = [
    "https://www.ishares.com/ch/professionelle-anleger/de/produkte/251931/ishares-stoxx-europe-600-ucits-etf-de-fund/1495092304805.ajax?fileType=csv&fileName=EXSA_holdings&dataType=fund",
    "https://www.ishares.com/de/privatanleger/de/produkte/251931/ishares-stoxx-europe-600-ucits-etf-de-fund/1478358465952.ajax?fileType=csv&fileName=EXSA_holdings&dataType=fund",
    "https://www.ishares.com/de/privatanleger/de/produkte/251931/ishares-stoxx-europe-600-ucits-etf-de-fund/latest-holdings.csv",
]
# Eingebaute Reserveliste Dow Jones (Stand 14.11.2026; Alphabet ersetzt Verizon seit 29.06.2026) - nur als letzte Notloesung
DOW = "AAPL AMGN AMZN AXP BA CAT CRM CSCO CVX DIS GOOGL GS HD HON IBM JNJ JPM KO MCD MMM MRK MSFT NKE NVDA PG SHW TRV UNH V WMT".split()
KRYPTO = "BTC ETH BNB SOL XRP ADA DOGE AVAX TRX LINK DOT LTC BCH XLM ATOM ETC".split()
ORDER = ["S&P 500", "NASDAQ 100", "Dow Jones", "DAX", "STOXX 600", "Russell 2000", "SSE Comp.", "Krypto"]
FILES = {"S&P 500": "listen/sp500.csv", "NASDAQ 100": "listen/nasdaq100.csv", "Dow Jones": "listen/dow.csv", "DAX": "listen/dax.csv",
         "STOXX 600": "listen/stoxx600.csv", "Russell 2000": "listen/russell2000.csv", "SSE Comp.": "listen/sse.csv"}
# Boersen-Endungen fuer europaeische Ticker (Waehrung / ISIN-Land -> Yahoo-Suffix)
CUR = {"GBP": [".L"], "GBX": [".L"], "CHF": [".SW"], "SEK": [".ST"], "DKK": [".CO"], "NOK": [".OL"], "PLN": [".WA"], "USD": ["", ".L"]}
COUNTRY = {"GB": [".L", ".AS"], "JE": [".L"], "GG": [".L"], "IM": [".L"], "BM": [".L"], "IE": [".IR", ".L", ".AS"],
           "NL": [".AS", ".PA", ".BR"], "FR": [".PA"], "DE": [".DE"], "CH": [".SW"], "ES": [".MC"], "IT": [".MI"],
           "SE": [".ST"], "DK": [".CO"], "NO": [".OL"], "FI": [".HE"], "BE": [".BR", ".AS", ".PA"], "PT": [".LS"],
           "AT": [".VI"], "LU": [".PA", ".AS", ".DE", ".L"], "PL": [".WA"], "GR": [".AT"]}
FALL = [".L", ".DE", ".PA", ".AS", ".SW", ".MI", ".MC", ".ST"]
MAXPASS = 5
# Von STOXX offiziell gestrichen, aber in der iShares-Liste noch enthalten (Quelle: STOXX-Mitteilung vom 02.03.2026, gueltig ab 23.03.2026;
# in den Mitteilungen vom 01.06. und 01.09.2026 nicht wieder aufgenommen). Weitere Eintraege: Datei listen/ausschluss.csv (Spalten Index;Ticker).
EXCLUDE = {("STOXX 600", "TECN")}

def pick(cols, *keys):
    for k in keys:
        for c in cols:
            if k in str(c).lower():
                return c
    return None

def parse_table(t, minrows):
    t = t.copy()
    t.columns = [" ".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in t.columns]
    cols = list(t.columns)
    tk, nm = pick(cols, "ticker", "symbol"), pick(cols, "company", "security", "name")
    sc = pick(cols, "gics sector", "sector", "industry group", "industry")
    if tk is None or len(t) < minrows:
        return None
    return [(str(a).strip(), str(b).strip() if nm else str(a), str(c).strip() if sc else "Sonstige")
            for a, b, c in zip(t[tk], t[nm] if nm else t[tk], t[sc] if sc else ["Sonstige"] * len(t))]

def wiki(url, minrows):
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    for t in pd.read_html(io.StringIO(r.text)):
        res = parse_table(t, minrows)
        if res:
            return res
    raise ValueError("keine passende Tabelle")

def custom(path):
    df = pd.read_csv(path, sep=None, engine="python", dtype=str, encoding="utf-8-sig").fillna("")
    c = list(df.columns)
    return [(str(r[c[0]]).strip(), str(r[c[1]]).strip() if len(c) > 1 else str(r[c[0]]),
             str(r[c[2]]).strip() if len(c) > 2 else "Sonstige") for _, r in df.iterrows() if str(r[c[0]]).strip()]

def ishares_csv(urls, minrows):
    """Laedt eine iShares-Bestandsliste (CSV mit Vorspann), probiert mehrere Adressen."""
    last = "keine Adresse"
    for u in urls:
        try:
            r = requests.get(u, headers=UA, timeout=90)
            r.raise_for_status()
            lines = r.content.decode("utf-8-sig", errors="replace").splitlines()
            head = None
            for i, l in enumerate(lines[:40]):
                low = l.lower().replace('"', "")
                if low.startswith(("ticker,", "emittententicker,", "issuer ticker,")):
                    head = i
                    break
            if head is None:
                raise ValueError("Kopfzeile nicht gefunden (kein CSV?)")
            print("   Vorspann der Datei:", " | ".join(l.strip() for l in lines[:head] if l.strip())[:220])
            df = pd.read_csv(io.StringIO("\n".join(lines[head:])), dtype=str, on_bad_lines="skip").fillna("")
            if len(df) < minrows:
                raise ValueError(f"nur {len(df)} Zeilen")
            return df
        except Exception as e:
            last = f"{u[:70]}... -> {e}"
            print("   iShares-Adresse fehlgeschlagen:", last)
    raise ValueError(last)

def src_russell():
    df = ishares_csv(URLS_RUSSELL, 1000)
    c_t, c_n, c_s = pick(df.columns, "ticker"), pick(df.columns, "name"), pick(df.columns, "sector", "sektor")
    c_a = pick(df.columns, "asset class", "anlageklasse")
    out = []
    for _, r in df.iterrows():
        if c_a and r[c_a].strip().lower() not in ("equity", "aktien"):
            continue
        tk = r[c_t].strip().upper()
        if not tk or tk in ("-", "USD"):
            continue
        out.append((tk.replace(" ", "-").replace(".", "-"), r[c_n].strip(), r[c_s].strip() or "Sonstige"))
    return out

EXCH = [("xetra", ".DE"), ("deutsche b", ".DE"), ("frankfurt", ".DE"), ("london", ".L"), ("paris", ".PA"), ("amsterdam", ".AS"),
        ("br\u00fcssel", ".BR"), ("brussels", ".BR"), ("lissabon", ".LS"), ("lisbon", ".LS"), ("dublin", ".IR"), ("irish", ".IR"),
        ("swiss", ".SW"), ("six ", ".SW"), ("z\u00fcrich", ".SW"), ("mailand", ".MI"), ("milan", ".MI"), ("borsa italiana", ".MI"),
        ("madrid", ".MC"), ("bolsa", ".MC"), ("stockholm", ".ST"), ("kopenhagen", ".CO"), ("copenhagen", ".CO"), ("oslo", ".OL"),
        ("helsinki", ".HE"), ("wien", ".VI"), ("vienna", ".VI"), ("warschau", ".WA"), ("warsaw", ".WA"), ("athen", ".AT"), ("athens", ".AT")]
LAND = [("vereinigtes k", ".L"), ("united kingdom", ".L"), ("gro\u00dfbritannien", ".L"), ("jersey", ".L"), ("guernsey", ".L"),
        ("frankreich", ".PA"), ("france", ".PA"), ("deutschland", ".DE"), ("germany", ".DE"), ("niederlande", ".AS"), ("netherlands", ".AS"),
        ("schweiz", ".SW"), ("switzerland", ".SW"), ("spanien", ".MC"), ("spain", ".MC"), ("italien", ".MI"), ("italy", ".MI"),
        ("schweden", ".ST"), ("sweden", ".ST"), ("d\u00e4nemark", ".CO"), ("denmark", ".CO"), ("norwegen", ".OL"), ("norway", ".OL"),
        ("finnland", ".HE"), ("finland", ".HE"), ("belgien", ".BR"), ("belgium", ".BR"), ("portugal", ".LS"), ("\u00f6sterreich", ".VI"),
        ("austria", ".VI"), ("irland", ".IR"), ("ireland", ".IR"), ("luxemb", ".PA"), ("polen", ".WA"), ("poland", ".WA"),
        ("griechenland", ".AT"), ("greece", ".AT")]
FALL_ALL = [".L", ".DE", ".PA", ".AS", ".SW", ".MI", ".MC", ".ST", ".CO", ".OL", ".HE", ".BR", ".LS", ".VI"]

def first_hit(text, table):
    t = text.lower()
    for k, v in table:
        if k in t:
            return v
    return None

def cands(exch, land, isin, cur):
    """Reihenfolge der Boersen-Endungen: Boerse > ISIN-Land > Standort > Waehrung. Nur wenn nichts bekannt ist: alle durchprobieren."""
    res = []
    for s in ([first_hit(exch, EXCH)] + COUNTRY.get(isin[:2].upper(), []) + [first_hit(land, LAND)]):
        if s and s not in res:
            res.append(s)
    if not res:
        for s in CUR.get(cur, []) + FALL_ALL:
            if s not in res:
                res.append(s)
    return res

def local_symbol(tk):
    t = tk.strip().upper().rstrip(".")
    return t.replace(" ", "-").replace(".", "-")

def src_stoxx():
    df = ishares_csv(URLS_STOXX, 400)
    cols = list(df.columns)
    print("   STOXX-Datei, Spalten:", cols)
    c_t, c_n, c_s = pick(cols, "ticker"), pick(cols, "name"), pick(cols, "sektor", "sector")
    c_a, c_i = pick(cols, "anlageklasse", "asset class"), pick(cols, "isin")
    c_e, c_l = pick(cols, "b\u00f6rse", "exchange", "handelsplatz"), pick(cols, "standort", "location", "country")
    c_c = pick(cols, "marktw\u00e4hr", "market curr", "w\u00e4hrung", "currency")
    print("   erkannt: Ticker=%s Boerse=%s Standort=%s ISIN=%s Waehrung=%s" % (c_t, c_e, c_l, c_i, c_c))
    if not (c_e or c_l or c_i):
        raise ValueError("keine Boersen-, Standort- oder ISIN-Spalte gefunden - STOXX 600 wird NICHT aufgenommen, "
                         "damit keine falschen Ticker zugeordnet werden. Bitte die Zeile 'Spalten:' oben pruefen.")
    out = []
    for _, r in df.iterrows():
        if c_a and r[c_a].strip().lower() not in ("aktien", "equity"):
            continue
        tk = r[c_t].strip()
        if not tk or tk == "-":
            continue
        g = lambda c: r[c].strip() if c else ""
        out.append({"tk": local_symbol(tk), "n": g(c_n), "sec": g(c_s) or "Sonstige",
                    "cands": cands(g(c_e), g(c_l), g(c_i), g(c_c).upper()), "ok": False})
    for h in out[:3]:
        print("   Beispiel:", h["tk"], h["n"], h["cands"])
    return out

def nasdaq_api():
    r = requests.get("https://api.nasdaq.com/api/quote/list-type/nasdaq100", headers={**UA, "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    rows = r.json()["data"]["data"]["rows"]
    return [(x["symbol"], x.get("companyName", x["symbol"]), "Sonstige") for x in rows]

def src_sp():
    return wiki(URL_SP, 400)

def src_ndx():
    try:
        return wiki(URL_NDX, 90)
    except Exception as e:
        print("NASDAQ 100 Wikipedia:", e, "-> versuche Nasdaq-API")
    return nasdaq_api()

URLS_DOW = ["https://stockanalysis.com/etf/dia/holdings/", "https://www.slickcharts.com/symbol/DIA/holdings"]

def dow_from_etf():
    """Bestandsliste des Dow-ETFs DIA (State Street) - enthaelt genau die 30 Index-Werte (+ Kasse)."""
    last = "keine Adresse"
    for u in URLS_DOW:
        try:
            r = requests.get(u, headers=BROWSER, timeout=30)
            r.raise_for_status()
            for t in pd.read_html(io.StringIO(r.text)):
                cols = [str(c) for c in t.columns]
                t.columns = cols
                sc, nc = pick(cols, "symbol"), pick(cols, "name", "holding")
                if not sc:
                    continue
                items = []
                for _, row in t.iterrows():
                    sym = str(row[sc]).strip().upper()
                    if re.fullmatch(r"[A-Z]{1,5}", sym) and sym != "USD":
                        items.append((sym, str(row[nc]).strip() if nc else sym, "Sonstige"))
                if 29 <= len(items) <= 31:
                    return items
            last = u + " -> keine Tabelle mit 30 Werten"
        except Exception as e:
            last = f"{u} -> {type(e).__name__}: {str(e)[:60]}"
    raise ValueError(last)

def src_dow():
    try:
        items = dow_from_etf()
        diff = set(t for t, _, _ in items) ^ set(DOW)
        if diff:
            print("   HINWEIS Dow: Reserveliste im Skript weicht von der aktuellen ETF-Liste ab:", sorted(diff))
        print("   Dow Jones aus der DIA-Bestandsliste")
        return items
    except Exception as e:
        print("Dow ETF-Liste:", e, "-> versuche Wikipedia")
    try:
        return wiki(URL_DOW, 28)
    except Exception as e:
        print("Dow Wikipedia:", e, "-> eingebaute Reserveliste (Stand 14.11.2026)")
    return [(t, t, "Sonstige") for t in DOW]

def src_dax():
    return wiki(URL_DAX, 35)

AUTO = {"S&P 500": (src_sp, "us"), "NASDAQ 100": (src_ndx, "us"), "Dow Jones": (src_dow, "us"),
        "DAX": (src_dax, "de"), "Russell 2000": (src_russell, "raw")}

def collect():
    info, pending = {}, []  # info: ticker -> {"n","sec","ix"}
    def add(index, items, mode):
        for tk, n, sec in items:
            tk = tk.strip().split()[0] if tk.strip() else ""
            if not tk:
                continue
            if mode == "us":
                tk = tk.replace(".", "-")
            elif mode == "de" and "." not in tk:
                tk += ".DE"
            tk = tk.upper()
            sec = SEC.get(sec.strip(), sec.strip()) or "Sonstige"
            d = info.setdefault(tk, {"n": n, "sec": sec, "ix": []})
            if index not in d["ix"]:
                d["ix"].append(index)
    for index in ORDER:
        if index in ("Krypto", "STOXX 600"):
            continue
        path = FILES[index]
        try:
            if os.path.exists(path):
                add(index, custom(path), "raw")
                print(index, "ok (aus", path + ")")
            elif index in AUTO:
                fn, mode = AUTO[index]
                add(index, fn(), mode)
                print(index, "ok")
            else:
                print(index, "uebersprungen (keine", path + ")")
        except Exception as e:
            print("FEHLER", index, e)
    try:
        if os.path.exists(FILES["STOXX 600"]):
            add("STOXX 600", custom(FILES["STOXX 600"]), "raw")
            print("STOXX 600 ok (aus", FILES["STOXX 600"] + ")")
        else:
            pending = src_stoxx()
            print("STOXX 600:", len(pending), "Positionen gelesen (Ticker werden gleich zugeordnet)")
    except Exception as e:
        print("FEHLER STOXX 600", e)
    add("Krypto", [(c + "-USD", c, "Krypto") for c in KRYPTO], "raw")
    return info, pending

def exclusions():
    ex = set(EXCLUDE)
    path = "listen/ausschluss.csv"
    if os.path.exists(path):
        try:
            for ix, tk in custom(path):
                ex.add((ix.strip(), tk.strip().upper()))
        except Exception as e:
            print("FEHLER ausschluss.csv:", e)
    return ex

STOP = {"AG", "SA", "SE", "NV", "PLC", "SPA", "ASA", "AB", "OYJ", "GROUP", "GRP", "HLDG", "HLDGS", "HOLDING", "HOLDINGS", "THE",
        "CO", "CORP", "CORPORATION", "LTD", "SAB", "AS", "INC", "KGAA", "PREF", "REG", "ORD", "CLASS", "SDR", "ADR"}

def norm_tokens(name):
    t = re.sub(r"[^A-Z0-9 ]", " ", name.upper().replace("&", " AND "))
    return {w for w in t.split() if w not in STOP and len(w) > 1}

def parse_release(html):
    """Liest eine STOXX-Mitteilung (Additions/Deletions). Rueckgabe: (Stichtag, [Ereignisse])"""
    text = re.sub(r"<[^>]+>", " ", html)
    m = re.search(r"[Ee]ffective as of the opening of European markets on ([A-Z][a-z]+ \d{1,2}, \d{4})", text)
    if not m:
        return None, []
    eff = datetime.datetime.strptime(m.group(1), "%B %d, %Y").date()
    events = []
    for t in pd.read_html(io.StringIO(html)):
        cols = {str(c).strip().lower(): c for c in t.columns}
        if "additions" in cols and "deletions" in cols:
            for kind, col in (("add", cols["additions"]), ("del", cols["deletions"])):
                for cell in t[col].dropna().astype(str):
                    g = re.match(r"^(.*?)\s*\((\w\w),\s*(.*),\s*([^,]+)\)\s*$", cell.strip())
                    if g:
                        events.append({"kind": kind, "date": eff, "name": g.group(1).strip(),
                                       "root": re.sub(r"[^a-z0-9]", "", g.group(4).split(".")[0].lower())})
            break
    return eff, events

BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.9"}

def stoxx_events():
    """Holt die offiziellen STOXX-Mitteilungen der letzten Quartale (stoxx.com bzw. iss-stoxx.com) und gibt alle Aufnahmen/Streichungen zurueck."""
    today = datetime.date.today()
    events, seen, stats, err = [], set(), {}, None
    urls = []
    for year in (today.year - 1, today.year):
        for ab in ("mar", "jun", "sep", "dec"):
            for d in range(1, 6):
                for dd in dict.fromkeys((f"{d:02d}", str(d))):
                    urls.append(f"https://stoxx.com/stoxx-europe-600-index-composition-changes-{ab}-{dd}-{year}/")
    urls += [f"https://www.iss-stoxx.com/press-releases/stoxx-europe-600-index-composition-changes{x}/" for x in ("", "-2", "-3", "-4", "-5", "-6", "-7", "-8")]
    def count(k):
        stats[k] = stats.get(k, 0) + 1
    for url in urls:
        try:
            r = requests.get(url, headers=BROWSER, timeout=30)
            count(r.status_code)
            if stats.get(403, 0) >= 6 and not seen:
                break  # vermutlich gesperrt, nicht weiter probieren
            if r.status_code != 200:
                continue
            if "Additions" not in r.text:
                count("200 ohne Tabelle")
                continue
            eff, ev = parse_release(r.text)
        except Exception as e:
            count("Fehler")
            err = err or f"{type(e).__name__}: {str(e)[:90]}"
            continue
        if not eff:
            count("ohne Datum")
            continue
        if eff not in seen and eff <= today:
            seen.add(eff)
            events += ev
            print(f"   STOXX-Mitteilung: gueltig ab {eff}, {len(ev)} Meldungen ({url[:60]}...)")
    print("   STOXX-Seiten abgefragt:", stats, ("| erster Fehler: " + err) if err else "")
    return events

def ev_match(ev, h):
    te, th = norm_tokens(ev["name"]), norm_tokens(h["n"])
    if not te or not te <= th:
        return False
    return len(te) > 1 or len(next(iter(te))) >= 4 or te == th or re.sub(r"[^a-z0-9]", "", h["tk"].lower()) == ev["root"]

def reconcile_stoxx(pending, events=None):
    """Gleicht die iShares-Liste mit den offiziellen STOXX-Mitteilungen ab: gestrichene Aktien fliegen raus, fehlende Aufnahmen werden gemeldet."""
    try:
        events = stoxx_events() if events is None else events
    except Exception as e:
        print("Abgleich mit STOXX nicht moeglich:", e)
        return pending
    if not events:
        print("Abgleich mit STOXX: keine Mitteilungen abrufbar - es gilt nur die iShares-Liste")
        return pending
    events = sorted(events, key=lambda e: e["date"])
    keep = []
    for h in pending:
        last = None
        for ev in events:
            if ev_match(ev, h):
                last = ev
        if last and last["kind"] == "del":
            print(f"STOXX-Abgleich: {h['n']} ({h['tk']}) laut STOXX zum {last['date']} gestrichen -> entfernt")
            continue
        keep.append(h)
    latest = {}
    for ev in events:
        latest[frozenset(norm_tokens(ev["name"]))] = ev
    for ev in latest.values():
        if ev["kind"] == "add" and not any(ev_match(ev, h) for h in keep):
            print(f"STOXX-Abgleich: WARNUNG - {ev['name']} (Aufnahme zum {ev['date']}) fehlt in der iShares-Liste")
    return keep

def download(chunk):
    for _ in range(3):
        try:
            df = yf.download(chunk, period="2y", interval="1d", auto_adjust=False, progress=False, threads=True)["Close"]
            if isinstance(df, pd.Series):
                df = df.to_frame(chunk[0])
            return df
        except Exception as e:
            print("Retry:", e)
            time.sleep(5)
    return None

def bulk(symbols):
    frames = [f for f in (download(symbols[i:i + 100]) for i in range(0, len(symbols), 100)) if f is not None]
    time.sleep(1)
    return pd.concat(frames, axis=1) if frames else None

def takeover_flags(ret, d):
    w = ret.loc[:d].tail(120)
    arr = w.to_numpy(dtype=float)
    out = {}
    filled = np.where(np.isnan(arr), -1e9, arr)
    for j in np.where(filled.max(axis=0) >= 10)[0]:
        col = filled[:, j]
        k = int(np.argmax(col))
        after = arr[k + 1:, j][-20:]
        after = after[~np.isnan(after)]
        if len(after) >= 5 and np.std(after) < 0.4:
            out[w.columns[j]] = [round(float(col[k]), 1), w.index[k].strftime("%Y-%m-%d"), round(float(np.std(after)), 2)]
    return out

def main():
    info, pending = collect()
    tickers = list(info)
    print(len(tickers), "Ticker (ohne STOXX-Zuordnung)")
    if pending:
        pending = reconcile_stoxx(pending)
    frames = [bulk(tickers)] if tickers else []
    # STOXX 600: Boersen-Endung durch Ausprobieren finden
    for rank in range(max([len(h["cands"]) for h in pending] or [0])):
        todo = [h for h in pending if not h["ok"] and rank < len(h["cands"])]
        if not todo:
            break
        syms = {}
        for h in todo:
            syms.setdefault(h["tk"] + h["cands"][rank], []).append(h)
        df = bulk(list(syms))
        if df is None:
            continue
        keep = []
        for s, hs in syms.items():
            if s in df.columns and df[s].notna().sum() >= 60:
                keep.append(s)
                d = info.setdefault(s, {"n": hs[0]["n"], "sec": SEC.get(hs[0]["sec"], hs[0]["sec"]), "ix": []})
                if "STOXX 600" not in d["ix"]:
                    d["ix"].append("STOXX 600")
                for h in hs:
                    h["ok"] = True
        frames.append(df[keep])
        print(f"STOXX 600 Durchgang {rank + 1}: {len(keep)} Ticker zugeordnet")
    for ix, tk in exclusions():
        for sym in list(info):
            if (sym == tk or sym.split(".")[0] == tk) and ix in info[sym]["ix"]:
                info[sym]["ix"].remove(ix)
                print(f"Ausgeschlossen: {sym} aus {ix}")
                if not info[sym]["ix"]:
                    del info[sym]
    miss = [h["n"] for h in pending if not h["ok"]]
    if pending:
        from collections import Counter
        used = Counter(k[k.rfind("."):] if "." in k else "(keine)" for k, v in info.items() if "STOXX 600" in v["ix"])
        print("STOXX 600 nach Boerse:", dict(used))
    if pending:
        print(f"STOXX 600: {len(pending) - len(miss)} von {len(pending)} zugeordnet. Nicht gefunden (Auszug):", miss[:25])
    px = pd.concat([f for f in frames if f is not None], axis=1)
    px = px.loc[:, ~px.columns.duplicated()]
    px.index = pd.to_datetime(px.index).tz_localize(None)
    now = datetime.datetime.utcnow()
    if now.weekday() < 5 and now.hour * 60 + now.minute < 21 * 60 + 15:
        px = px[px.index < pd.Timestamp(now.date())]
    px = px[px.notna().sum(axis=1) >= 300]
    days = list(px.index[-TAGE:])
    ret = px.pct_change(fill_method=None) * 100
    os.makedirs(OUT, exist_ok=True)
    for old in os.listdir(OUT):
        os.remove(os.path.join(OUT, old))
    names = []
    for d in days:
        sub = px[px.index <= d]
        weekly = sub.resample("W-FRI").last().tail(26)
        sma = weekly.mean()
        ok = (weekly.notna().sum() == 26) & sub.tail(5).notna().any()
        last26 = sub.tail(26)
        sma26 = last26.mean()
        ok26 = last26.notna().sum() >= 20
        filled = sub.ffill()
        close = filled.iloc[-1]
        perf = {k: ((close / filled.iloc[-1 - n] - 1) * 100 if len(filled) > n else None) for k, n in (("d1", 1), ("w1", 5), ("m1", 21))}
        flags = takeover_flags(ret, d)
        rows = []
        for tk in px.columns:
            if tk not in info or not ok.get(tk, False) or not pd.notna(close[tk]):
                continue
            row = {"tk": tk, "n": info[tk]["n"], "sec": info[tk]["sec"], "ix": info[tk]["ix"],
                   "cl": round(float(close[tk]), 2), "sma": round(float(sma[tk]), 2)}
            if ok26.get(tk, False) and pd.notna(sma26[tk]):
                row["s26"] = round(float(sma26[tk]), 2)
            for k, ser in perf.items():
                if ser is not None and pd.notna(ser[tk]):
                    row[k] = round(float(ser[tk]), 2)
            if tk in flags:
                row["ue"] = flags[tk]
            rows.append(row)
        if len(rows) < 300:
            print("Zu wenige Aktien am", d.date())
            continue
        name = d.strftime("%Y-%m-%d")
        with open(f"{OUT}/{name}.json", "w", encoding="utf-8") as f:
            json.dump({"updated": "Handelsschluss " + d.strftime("%d.%m.%Y"), "rows": rows}, f, ensure_ascii=False, separators=(",", ":"))
        names.append(name)
    if not names:
        raise SystemExit("Keine Daten erzeugt")
    with open(f"{OUT}/index.json", "w", encoding="utf-8") as f:
        json.dump({"dates": names[::-1]}, f)
    print(len(names), "Stichtage, neuester:", names[-1])

if __name__ == "__main__":
    main()
