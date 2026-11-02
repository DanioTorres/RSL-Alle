import io, json, os, time, datetime
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
# Eingebaute Reserveliste (Stand 2025) - nur falls Wikipedia nicht lesbar ist und keine listen/dow.csv existiert
DOW = "AAPL AMGN AMZN AXP BA CAT CRM CSCO CVX DIS GS HD HON IBM JNJ JPM KO MCD MMM MRK MSFT NKE NVDA PG SHW TRV UNH V VZ WMT".split()
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

def cands(tk, isin, cur):
    c = CUR.get(cur, []) + COUNTRY.get(isin[:2], []) + FALL
    seen, res = set(), []
    for s in c:
        if s not in seen:
            seen.add(s)
            res.append(s)
    return res[:MAXPASS]

def local_symbol(tk):
    t = tk.strip().upper().rstrip(".")
    return t.replace(" ", "-").replace(".", "-")

def src_stoxx():
    df = ishares_csv(URLS_STOXX, 400)
    c_t, c_n, c_s = pick(df.columns, "ticker"), pick(df.columns, "name"), pick(df.columns, "sektor", "sector")
    c_a, c_i = pick(df.columns, "anlageklasse", "asset class"), pick(df.columns, "isin")
    c_c = pick(df.columns, "marktw", "market curr")
    out = []
    for _, r in df.iterrows():
        if c_a and r[c_a].strip().lower() not in ("aktien", "equity"):
            continue
        tk = r[c_t].strip()
        if not tk or tk == "-":
            continue
        isin = r[c_i].strip() if c_i else ""
        cur = r[c_c].strip().upper() if c_c else ""
        out.append({"tk": local_symbol(tk), "n": r[c_n].strip(), "sec": r[c_s].strip() or "Sonstige",
                    "cands": cands(tk, isin, cur), "ok": False})
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

def src_dow():
    try:
        return wiki(URL_DOW, 28)
    except Exception as e:
        print("Dow Wikipedia:", e, "-> eingebaute Liste (Stand 2025)")
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
    frames = [bulk(tickers)] if tickers else []
    # STOXX 600: Boersen-Endung durch Ausprobieren finden
    for rank in range(MAXPASS):
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
    miss = [h["n"] for h in pending if not h["ok"]]
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
