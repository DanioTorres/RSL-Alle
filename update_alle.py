import io, json, os, time, datetime
import numpy as np
import pandas as pd, requests, yfinance as yf

TAGE = 20  # abrufbare Stichtage
OUT = "data_alle"
UA = {"User-Agent": "Mozilla/5.0 rsl-dashboard"}
SEC = {"Health Care": "Healthcare", "Information Technology": "Technology", "Communication": "Communication Services",
       "Finanzwesen": "Financials", "Gesundheitsversorgung": "Healthcare", "IT": "Technology",
       "Nichtzyklische Konsumgüter": "Consumer Staples", "Zyklische Konsumgüter": "Consumer Discretionary",
       "Energie": "Energy", "Materialien": "Materials", "Versorger": "Utilities", "Kommunikation": "Communication Services",
       "Industrie": "Industrials", "Immobilien": "Real Estate"}
URL_SP = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
URL_NDX = "https://en.wikipedia.org/wiki/Nasdaq-100"
URL_DOW = "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average"
URL_DAX = "https://en.wikipedia.org/wiki/DAX"
# Eingebaute Reserveliste (Stand 2025) - nur falls Wikipedia nicht lesbar ist und keine listen/dow.csv existiert
DOW = "AAPL AMGN AMZN AXP BA CAT CRM CSCO CVX DIS GS HD HON IBM JNJ JPM KO MCD MMM MRK MSFT NKE NVDA PG SHW TRV UNH V VZ WMT".split()
KRYPTO = "BTC ETH BNB SOL XRP ADA DOGE AVAX TRX LINK DOT LTC BCH XLM ATOM ETC".split()
ORDER = ["S&P 500", "NASDAQ 100", "Dow Jones", "DAX", "STOXX 600", "Russell 2000", "SSE Comp.", "Krypto"]
FILES = {"S&P 500": "listen/sp500.csv", "NASDAQ 100": "listen/nasdaq100.csv", "Dow Jones": "listen/dow.csv", "DAX": "listen/dax.csv",
         "STOXX 600": "listen/stoxx600.csv", "Russell 2000": "listen/russell2000.csv", "SSE Comp.": "listen/sse.csv"}

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

URL_IWM = "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/latest-holdings.csv"
URLS_STOXX = [
    "https://www.ishares.com/de/privatanleger/de/produkte/251931/ishares-stoxx-europe-600-ucits-etf-de-fund/latest-holdings.csv",
    "https://www.ishares.com/de/privatanleger/de/produkte/251931/ishares-stoxx-europe-600-ucits-etf-de-fund/1478358465952.ajax?fileType=csv&fileName=EXSA_holdings&dataType=fund",
    "https://www.ishares.com/de/privatanleger/de/produkte/251931/ishares-stoxx-europe-600-ucits-etf-de-fund/1478358465952.ajax?filetype=csv&filename=exsa_holdings&datatype=fund",
]
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept": "text/csv,*/*"}
EXCH = [("xetra", ".DE"), ("frankfurt", ".DE"), ("paris", ".PA"), ("amsterdam", ".AS"), ("brussels", ".BR"), ("lisbon", ".LS"),
        ("madrid", ".MC"), ("bolsa", ".MC"), ("milan", ".MI"), ("borsa italiana", ".MI"), ("swiss", ".SW"), ("six", ".SW"),
        ("london", ".L"), ("stockholm", ".ST"), ("copenhagen", ".CO"), ("helsinki", ".HE"), ("oslo", ".OL"), ("vienna", ".VI"),
        ("wien", ".VI"), ("dublin", ".IR"), ("irish", ".IR"), ("warsaw", ".WA"), ("athens", ".AT")]
CTRY = {"GB": ".L", "CH": ".SW", "DE": ".DE", "FR": ".PA", "NL": ".AS", "ES": ".MC", "IT": ".MI", "SE": ".ST", "DK": ".CO",
        "FI": ".HE", "NO": ".OL", "BE": ".BR", "PT": ".LS", "AT": ".VI", "IE": ".IR", "PL": ".WA", "GR": ".AT", "LU": ".PA",
        "JE": ".L", "GG": ".L"}

def get_csv(url):
    r = requests.get(url, headers=BROWSER, timeout=60)
    r.raise_for_status()
    text = r.content.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    for i, l in enumerate(lines):
        low = l.lower().replace('"', "")
        if low.startswith(("ticker,", "emittententicker", "issuer ticker", "ticker;")):
            return pd.read_csv(io.StringIO("\n".join(lines[i:])), sep=None, engine="python", dtype=str).fillna("")
    raise ValueError("keine Kopfzeile gefunden")

def src_russell():
    df = get_csv(URL_IWM)
    cols = list(df.columns)
    ac, sc, nm = pick(cols, "asset class"), pick(cols, "sector"), pick(cols, "name")
    out = []
    for _, r in df.iterrows():
        if ac and r[ac].strip().lower() != "equity":
            continue
        tk = r[cols[0]].strip().replace(" ", "-")
        if tk and tk != "-":
            out.append((tk, r[nm] if nm else tk, r[sc] if sc else "Sonstige"))
    if len(out) < 1500:
        raise ValueError("nur %d Zeilen" % len(out))
    return out

def yahoo_ticker(t, exch, isin):
    t = t.strip().upper().replace(" ", "-")
    if t.endswith("/"):
        t = t[:-1]
    t = t.replace("/", "-")
    low = (exch or "").lower()
    for key, suf in EXCH:
        if key in low:
            return t + suf
    return t + CTRY.get((isin or "")[:2].upper(), "")

def src_stoxx():
    last = None
    for url in URLS_STOXX:
        try:
            df = get_csv(url)
            cols = list(df.columns)
            ac, sc, nm = pick(cols, "asset class", "anlageklasse"), pick(cols, "sector", "sektor"), pick(cols, "name")
            ex, isn = pick(cols, "exchange", "börse", "borse"), pick(cols, "isin")
            out = []
            for _, r in df.iterrows():
                if ac and r[ac].strip().lower() not in ("equity", "aktien"):
                    continue
                isin = r[isn].strip() if isn else ""
                tk = r[cols[0]].strip()
                if not tk or tk == "-":
                    continue
                out.append((yahoo_ticker(tk, r[ex] if ex else "", isin), r[nm] if nm else tk, r[sc] if sc else "Sonstige", isin))
            if len(out) >= 300:
                print("STOXX 600: %d Zeilen von %s" % (len(out), url[:90]))
                return out
            last = "nur %d Zeilen" % len(out)
        except Exception as e:
            last = e
            print("STOXX 600 URL fehlgeschlagen:", str(e)[:100])
    raise ValueError(last)

def src_dax():
    return wiki(URL_DAX, 35)

AUTO = {"S&P 500": (src_sp, "us"), "NASDAQ 100": (src_ndx, "us"), "Dow Jones": (src_dow, "us"), "DAX": (src_dax, "de"), "Russell 2000": (src_russell, "raw"), "STOXX 600": (src_stoxx, "raw")}

def collect():
    info = {}  # ticker -> {"n","sec","ix"}
    def add(index, items, mode):
        for item in items:
            tk, n, sec = item[:3]
            tk = tk.strip().split()[0] if tk.strip() else ""
            if not tk:
                continue
            if mode == "us":
                tk = tk.replace(".", "-")
            elif mode == "de" and "." not in tk:
                tk += ".DE"
            tk = tk.upper()
            d = info.setdefault(tk, {"n": n, "sec": SEC.get(sec, sec) or "Sonstige", "ix": []})
            if len(item) > 3 and item[3]:
                d["isin"] = item[3]
            if index not in d["ix"]:
                d["ix"].append(index)
    for index in ORDER:
        if index == "Krypto":
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
    add("Krypto", [(c + "-USD", c, "Krypto") for c in KRYPTO], "raw")
    return info

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

def resolve_isin(isin):
    try:
        r = requests.get("https://query2.finance.yahoo.com/v1/finance/search", params={"q": isin, "quotesCount": 6, "newsCount": 0},
                         headers=BROWSER, timeout=20)
        qs = [q for q in r.json().get("quotes", []) if q.get("quoteType") == "EQUITY" and q.get("symbol")]
        return qs[0]["symbol"] if qs else None
    except Exception:
        return None

def repair_missing(px, info):
    miss = [tk for tk, d in info.items() if d.get("isin") and (tk not in px.columns or px[tk].notna().sum() < 100)]
    print(len(miss), "Ticker mit ISIN ohne Kurse - suche Yahoo-Symbol ueber ISIN")
    mapping = {}
    for tk in miss[:250]:
        sym = resolve_isin(info[tk]["isin"])
        if sym and sym != tk and sym not in info:
            mapping[sym] = tk
        time.sleep(0.25)
    if mapping:
        syms = list(mapping)
        new = [f for f in (download(syms[i:i + 100]) for i in range(0, len(syms), 100)) if f is not None]
        if new:
            add = pd.concat(new, axis=1)
            add = add.loc[:, ~add.columns.duplicated()].rename(columns=mapping)
            add.index = pd.to_datetime(add.index).tz_localize(None)
            px = pd.concat([px.drop(columns=[c for c in add.columns if c in px.columns]), add], axis=1)
            print(len(mapping), "per ISIN gefunden")
    left = [tk for tk in miss if tk not in px.columns or px[tk].notna().sum() < 100]
    print("weiterhin ohne Kurse:", len(left), left[:20])
    return px

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
    info = collect()
    tickers = list(info)
    print(len(tickers), "Ticker")
    frames = [f for f in (download(tickers[i:i + 100]) for i in range(0, len(tickers), 100)) if f is not None]
    px = pd.concat(frames, axis=1)
    px = px.loc[:, ~px.columns.duplicated()]
    px.index = pd.to_datetime(px.index).tz_localize(None)
    px = repair_missing(px, info)
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
        if d == days[-1]:
            from collections import Counter
            cnt = Counter(i for r in rows for i in r["ix"])
            print("Aktien je Index:", dict(cnt))
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
